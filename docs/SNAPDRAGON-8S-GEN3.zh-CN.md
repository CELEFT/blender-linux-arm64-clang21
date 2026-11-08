# Blender ARM64（骁龙 8s Gen 3）构建与交接指南

本文对应仓库中的实际脚本和 CI，而不是一份脱离代码的构想。目标是在 ARM64 Linux 容器（proot/chroot）中运行 Blender 5.2+/5.3，使用 CPU Cycles 渲染，并通过 Vulkan（Mesa/Turnip）或 OpenGL 显示视口。

## 1. 目标与边界

| 项目 | 决策 |
| --- | --- |
| 目标设备 | 骁龙 8s Gen 3：Cortex-X4 + Cortex-A720 + Cortex-A520 |
| 运行环境 | Android 上的 proot/chroot Linux 容器 |
| Blender | 5.2.x 稳定版起；5.3.x 出现稳定 tag 后可直接使用 |
| CI | GitHub Actions，`ubuntu-26.04-arm` |
| 编译器 | Clang 21 + LLD 21 |
| 优化 | `-mcpu=cortex-x4+nosve+nosve2 -O3 -flto=thin` |
| 图形 | CPU Cycles + Vulkan/OpenGL 视口 |
| GPU 计算 | CUDA/OptiX/HIP/HIPRT/oneAPI 全部关闭 |
| 依赖 | 默认使用 Blender 官方 ARM64 预编译库；源码下载器可用于审计或后续 `make deps` |

> 关键安全约束：Cortex-X4 硬件支持 SVE2，但 Android 内核和容器经常不通过 `HWCAP` 暴露 SVE。若二进制中执行 SVE 指令，进程会直接 `Illegal instruction`。因此本项目在编译期强制剥离 SVE/SVE2，且 `build-blender.sh` 会拒绝不含 `+nosve+nosve2` 的 CPU flag 覆盖。

## 2. 为什么选择 Clang 21 而不是 GCC

- Clang 对 ARMv9.2/Cortex-X4 的调度模型更新，能识别 `-mcpu=cortex-x4`。
- Clang 的 `-mcpu=cortex-x4+nosve+nosve2` 是可验证的单条目标策略，探针编译通过后才进入正式构建。
- 使用 LLD 和 ThinLTO，链接阶段保持单并发，降低 ARM64 容器 OOM 概率。
- GCC 15/16 在部分 SVE 路径上存在回归；即使不用 SVE，统一工具链也更利于复现 CI。

编译脚本的最终核心选项：

```text
-mcpu=cortex-x4+nosve+nosve2
-O3
-flto=thin
-fuse-ld=lld
```

CMake 配置还强制启用：

```text
-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON
-DWITH_VULKAN_BACKEND=ON
-DWITH_OPENGL_BACKEND=ON
-DWITH_CYCLES_DEVICE_CPU=ON
-DWITH_CYCLES_DEVICE_CUDA=OFF
-DWITH_CYCLES_DEVICE_OPTIX=OFF
-DWITH_CYCLES_DEVICE_HIP=OFF
-DWITH_CYCLES_DEVICE_HIPRT=OFF
-DWITH_CYCLES_DEVICE_ONEAPI=OFF
```

## 3. 依赖策略

默认路径使用 Blender 官方 `lib-linux_arm64` 预编译库。这样做不是“偷懒”：ARM64 上 OIDN、Embree、libffi、oneTBB、flex 等依赖经常因为编译器、C 标准或补丁问题失败，而官方库与稳定版 Blender 的 ABI/版本对齐，能显著提高主程序首次可运行的概率。

脚本仍然保留以下能力：

1. `prepare-source.py` 同时记录 Blender 源 commit、ARM64 库 commit 和实际下载端点。
2. Blender 主 Git 源失败时自动尝试 GitHub 镜像；可用 `BLENDER_SOURCE_URL`、`BLENDER_LIBRARY_URL` 指定国内或私有镜像。
3. `fetch-dependency-source.py --all` 可按 manifest 下载并校验所有依赖源码。下载器使用正常 User-Agent，不再伪造 Mozilla UA；支持 `BLENDER_DEPENDENCY_MIRROR_PREFIXES`（逗号分隔）添加同路径布局的镜像前缀，失败会尝试上游 URI 并重试。
4. 如果 Embree/OIDN 是唯一失败点，使用最小依赖配置：

```sh
BLENDER_MINIMAL_FEATURES=1 ./build-blender.sh
```

这等价于关闭 `WITH_CYCLES_EMBREE` 和 `WITH_OPENIMAGEDENOISE`。`verify-build.py` 会从 `logs/build-info.json` 读取实际特性，不会把被关闭的功能误判为构建失败。

如果后续改用 `make deps`，请把它当成独立的依赖构建阶段，并用同一套 Clang/CPU flag 构建；不要假设官方预编译库和源码依赖可以无记录地混用。产物中必须保留 `dependency-sources.tsv` 和 `BUILD-INFO.json`。

## 4. GitHub Actions 架构

工作流文件：`.github/workflows/manual-build.yml`。

手动触发时可配置：

- `blender_version`：留空自动选最新稳定版；也可固定 `5.2.3`，5.3 稳定后填入对应版本。
- `dependency_ref`：仅在自动匹配 ARM64 库失败时覆盖。
- `runner`：默认 `ubuntu-26.04-arm`，可在该 label 不可用时切到其他 ARM64 runner。
- `build_jobs`：默认 4；低内存机器改 2。
- `mesa_ppa`：默认尝试 `ppa:kisak/kisak-mesa`；留空则用 Ubuntu 源。
- `minimal_features`：关闭 Embree/OIDN 的兜底开关。
- `download_dependency_sources`：把全部固定版本依赖源码下载到 `dependency-sources/`。
- `publish_release`：默认关闭；只上传 artifact，人工检查后再发布 Release 更安全。

关键阶段拆分：

1. 安装 Clang 21/LLD 21、构建依赖、Vulkan/Mesa 和 Xvfb。
2. 恢复 `source/` 与 `dependency-sources/` 缓存。
3. `prepare-source.sh` 解析并锁定 source/dependency commit，随后立即 `actions/cache/save@v4`，条件为 `if: always()`。即使后面的依赖下载或编译失败，已下载的源码/LFS 对象仍能复用。
4. 可选执行 `fetch-dependency-source.py --all`，同样位于缓存保存之前。
5. `build-blender.sh` 配置、编译、安装，并对 `compile_commands.json` 做全量 CPU/LTO flag 校验。
6. Xvfb 下验证 CPU Cycles、软件 OpenGL、GUI 启动。
7. Vulkan 探针是非阻断诊断：GitHub 宿主 runner 通常没有 Turnip 兼容 GPU，失败只产生 warning；真机是否可用必须单独验收。
8. 打包 `.deb`、源码包、`BUILD-INFO.json`、`SHA256SUMS`，安装 `.deb` 后再验一次。
9. 只有 `publish_release=true` 才创建 GitHub Release。

缓存策略的注意点：

- cache key 包含 Blender 版本、dependency ref 和脚本哈希，避免不同目标复用错误依赖。
- 全量缓存 `source/` 才有意义；只缓存 Git 元数据而丢掉工作树，会让下一次 `prepare-source.py` 看到大量“删除”的文件并拒绝继续。
- 缓存保存放在下载/解析阶段之后、主编译之前，符合“下载崩了也保住源码包”的目标。
- LFS 对象和官方预编译库会占用较大空间；若仓库 cache 接近上限，优先清理旧 run 的 cache，而不是删除 `.git/lfs` 后再让每次 CI 重下。

## 5. 本地构建与验证命令

在原生 ARM64 Linux 上：

```sh
git clone https://github.com/CELEFT/blender-linux-arm64-clang21.git
cd blender-linux-arm64-clang21
./prepare-source.sh
BLENDER_BUILD_JOBS=2 ./build-blender.sh
```

固定版本：

```sh
BLENDER_VERSION=5.2.3 ./prepare-source.sh
```

验证：

```sh
project_dir="$PWD"
source ./build-settings.sh

xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --background --factory-startup \
  --python-exit-code 1 --python verify-build.py

xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --factory-startup \
  --python-exit-code 1 --python verify-ui.py
```

Vulkan 检查：

```sh
vulkaninfo --summary

xvfb-run -a -s '-screen 0 1280x720x24' \
  "$install_dir/blender" --gpu-backend vulkan -noaudio \
  --factory-startup --python-exit-code 1 --python verify-vulkan.py
```

## 6. 手机真机避坑清单

### SVE 与 HWCAP

不要在手机上使用 `-march=native` 或 `-mcpu=native` 重新构建。proot 暴露的 CPU 信息本来就可能与宿主机不一致；即使 native 探测“成功”，产物也可能包含当前 Android 内核未暴露的 SVE 指令。CI 和本地都必须硬编码 `-mcpu=cortex-x4+nosve+nosve2`。

`verify-build.py` 会打印 `HWCAP` 中的 SVE 位，用于现场记录；真正防止 SVE 代码生成的是编译期 flag，而不是运行期检查。

### Vulkan / Turnip

Blender `.deb` 不打包 Mesa。请确认容器能看到设备提供的 Vulkan ICD：

```sh
vulkaninfo --summary
blender --gpu-backend vulkan
```

若 Vulkan 视口崩溃：

```sh
BLENDER_GRAPHICS_MODE=software blender
```

或在 Blender 偏好设置中切回 OpenGL。视口后端和 Cycles CPU 渲染是两条路径；Vulkan 崩溃不代表 CPU Cycles 不可用。

### 散热与功耗墙

骁龙 8s Gen 3 持续 CPU 渲染会快速升温。没有半导体散热背夹时，短时间测试可以，长时间 Cycles 渲染会撞温度墙并出现性能断崖。CI 构建与真机渲染要分开评估，不要用短时跑分代表持续性能。

### OOM

- 手机端最终 ThinLTO 链接使用 `BLENDER_LINK_JOBS=1`；不要为了快把链接并发调高。
- 手机/容器构建或者大场景渲染建议 `BLENDER_BUILD_JOBS=2`，并配置 swap。
- 关闭后台应用，避免 Android LMK 杀掉链接进程。
- CI 日志出现 OOM 时，先降低 `build_jobs`，再考虑关闭 Embree/OIDN。

### 容器与包管理

- `.deb` 按 Ubuntu 26.04 ARM64 构建；在 Debian 或其他容器中应重新构建并单独测试。
- 安装包会与发行版 `blender` 冲突，因为二者都提供 `/usr/bin/blender`。
- Vulkan 驱动/Mesa 版本、kernel、容器挂载变化后，Auto 图形缓存会失效；必要时删除 `~/.cache/blender-linux-arm64/graphics.json`。

## 7. 产物与验收标准

一次可交接的构建至少应包含：

- `blender-linux-arm64_*.deb`
- `blender-<version>-source.tar.xz`
- `BUILD-INFO.json`：source commit、dependency commit、compiler、CPU flag、LTO、Vulkan/Embree/OIDN 状态、Mesa 版本。
- `SHA256SUMS`
- CI 日志中的 `BUILD_VERIFIED`、`CPU_FLAGS_VERIFIED`、`UI_VERIFIED`
- 真机上的 `vulkaninfo --summary`、Vulkan/OpenGL 分别启动结果和一个小场景 Cycles CPU 渲染结果

只有 CI 通过，不等于手机端已经通过。交接时请把“CI 已验证”和“真机已验证”分开记录。
