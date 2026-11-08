# Blender Linux ARM64（骁龙 8s Gen 3）精简构建与交接指南

本文对应仓库中的实际脚本和 CI。目标是在 ARM64 Linux 容器（proot/chroot）中运行一个**精简但可用**的 Blender 5.2+/5.3：CPU Cycles 渲染、Vulkan/OpenGL 视口，并自动兼容 Mesa Freedreno（msm DRI）与 Turnip/Freedreno Vulkan。

## 1. 固定策略

| 项目 | 决策 |
| --- | --- |
| 目标设备 | 骁龙 8s Gen 3：Cortex-X4 + Cortex-A720 + Cortex-A520 |
| 运行环境 | Android 上的 proot/chroot Linux 容器 |
| 构建 runner | GitHub `ubuntu-26.04-arm` |
| 编译器 | Clang 21 + LLD 21 |
| 优化 | `-mcpu=cortex-x4+nosve+nosve2 -O3 -flto=thin` |
| 渲染 | CPU Cycles（SVM 路径） |
| 图形 | Vulkan/OpenGL + Mesa Freedreno 自动检测 |
| 依赖 | Blender 官方 ARM64 预编译库 |

> 必须禁用 SVE/SVE2。Cortex-X4 硬件支持 SVE2，但 Android 内核和 proot 经常不暴露对应 HWCAP；执行 SVE 指令会直接 `Illegal instruction`。`build-blender.sh` 会拒绝不含 `+nosve+nosve2` 的 CPU flag 覆盖，并扫描全部 C/C++ 编译命令。

## 2. 精简特性矩阵

保留：

- CPU Cycles 与默认 SVM shading；
- Python + NumPy；
- Vulkan/OpenGL 视口；
- 常用图像/网格导入导出；
- OpenSubdiv、TBB、OpenColorIO 和核心建模功能；
- Adreno/Freedreno OpenGL 与 Turnip Vulkan 自动环境配置。

关闭（减小包体）：

- Cycles OSL、Embree、path guiding、OpenImageDenoise；
- USD、Hydra、MaterialX、Alembic、OpenVDB、NanoVDB；
- Freestyle、流体/海洋模拟、OpenXR；
- FFmpeg、libsndfile、Audaspace、OpenAL、PulseAudio、JACK；
- 国际化、Libmv、Draco/Meshoptimizer、Potrace/Haru；
- CUDA、OptiX、HIP/HIPRT、oneAPI；
- 开发头文件、静态库、Python tests、`__pycache__`、字节码和 locale。

代价：CPU Cycles 不使用 Embree 加速，也没有 OIDN 降噪；完整功能版本需要自行恢复相应 CMake option。

## 3. 为什么编译参数必须硬编码

proot 中的 `/proc/cpuinfo`、HWCAP 和 `-march=native` 结果可能与真实 Android 运行环境不一致。CI 和本地构建都固定：

```text
-mcpu=cortex-x4+nosve+nosve2
-O3
-flto=thin
-fuse-ld=lld
```

构建脚本会在配置前用 Clang 编译一个探针程序；CMake configure 后校验 Slim feature matrix，再检查 `compile_commands.json` 中所有 C/C++ translation unit 都带有 CPU flag 和 ThinLTO，且没有 `native`、`+sve`、`+sve2` 等选项。

## 4. Mesa Freedreno / Turnip 兼容

安装包启动器在检测到图形设备且用户没有显式指定驱动时自动设置：

| 检测目标 | 环境变量 |
| --- | --- |
| `msm_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=msm` |
| `freedreno_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=freedreno` |
| `kgsl_dri.so` | `MESA_LOADER_DRIVER_OVERRIDE=kgsl` |
| `freedreno_icd*.json` / `turnip_icd*.json` | `VK_DRIVER_FILES` + `VK_ICD_FILENAMES` |

设备路径支持 `/dev/dri/renderD*` 和 `/dev/kgsl-3d0`。用户已设置 `MESA_LOADER_DRIVER_OVERRIDE=zink`、`VK_DRIVER_FILES` 等值时不会被覆盖。

关闭自动配置：

```sh
BLENDER_FREEDRENO_COMPAT=0 blender
```

查看本次检测结果：

```sh
cat "${XDG_CACHE_HOME:-$HOME/.cache}/blender-linux-arm64/freedreno.json"
```

真机检查：

```sh
vulkaninfo --summary
ls -l /dev/dri /dev/kgsl-3d0 2>/dev/null
find /usr/lib/aarch64-linux-gnu/dri -maxdepth 1 \
  \( -iname '*msm*' -o -iname '*freedreno*' \)
```

`.deb` 不打包 Mesa/Turnip；容器里必须安装与内核匹配的 Mesa ARM64 驱动，并让 proot/chroot 看见 render node 或 kgsl 设备。

## 5. 工作流结构

`.github/workflows/manual-build.yml` 已重写为单 job、精简阶段：

1. 释放 runner 磁盘空间，设置 build/install 路径。
2. 安装 Clang 21、LLD 21、Mesa DRI/Vulkan、`libdrm-freedreno1` 和 Xvfb。
3. 输出 Mesa/Freedreno DRI、Vulkan ICD 版本和文件列表。
4. 运行 `verify-freedreno.py`，验证自动检测和显式覆盖逻辑。
5. 恢复 `source/` 缓存。
6. 执行 `prepare-source.sh` 解析并锁定 Blender/ARM64 库 commit。
7. 使用 `actions/cache/save@v4` 保存源码和 LFS 缓存，条件为 `if: always()`。
8. 执行 `build-blender.sh`，随后用 `slim-install.py` 删除 tests、静态库、开发文件和字节码。
9. Xvfb 下验证 CPU Cycles、软件 OpenGL 和 slim feature matrix。
10. 非阻断地探测 Vulkan/Freedreno ICD；宿主 runner 没有 Adreno 时不误判构建失败。
11. 打包 `.deb`，安装后再次验证 Auto 图形启动器。
12. 默认只上传 artifact；`publish_release=true` 时才创建 Release。

缓存 key 包含 Blender 版本、dependency ref 和脚本哈希。缓存保存位于下载/解析之后、主编译之前，因此后续编译失败不会让源码重新下载。

## 6. 包体精简

两层处理：

1. `slim-install.py`
   - 删除 Python tests、tkinter/idlelib、config 目录、`__pycache__`、`.pyc`、`.a`、`.la`、`.prl`；
   - 删除 `include`、CMake/pkg-config 文件和手工页；
   - `--no-i18n` 删除 locale 数据（构建已关闭 internationalization）。
2. `package-deb.py`
   - 对所有 ELF 执行 `strip --strip-unneeded`；
   - 使用 xz level 9 构建 `.deb`；
   - 移除 OIDN GPU 插件（若存在）；
   - 系统依赖列表移除已禁用的音频库。

可用 `BLENDER_STRIP_BINARIES=0 ./package-release.sh` 跳过 strip 以保留调试符号。

## 7. 本地构建命令

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

依赖 Git 源支持镜像回退：

```sh
BLENDER_SOURCE_URL=https://mirror.example/blender.git
BLENDER_LIBRARY_URL=https://mirror.example/lib-linux_arm64.git
```

依赖源码下载仍可用：

```sh
python3 fetch-dependency-source.py --all --output dependency-sources
```

下载器使用普通 User-Agent，支持重试、上游 URI 和 `BLENDER_DEPENDENCY_MIRROR_PREFIXES`。

## 8. 验证标记

CPU Cycles/软件 OpenGL：

```sh
project_dir="$PWD"
source ./build-settings.sh
xvfb-run -a -s '-screen 0 1280x720x24' \
  env LIBGL_ALWAYS_SOFTWARE=1 "$install_dir/blender" \
  --gpu-backend opengl -noaudio --background --factory-startup \
  --python-exit-code 1 --python verify-build.py
```

Freedreno 检测逻辑：

```sh
python3 verify-freedreno.py
```

Vulkan：

```sh
vulkaninfo --summary
xvfb-run -a -s '-screen 0 1280x720x24' \
  "$install_dir/blender" --gpu-backend vulkan -noaudio \
  --factory-startup --python-exit-code 1 --python verify-vulkan.py
```

应看到：

- `SLIM_FEATURE_MATRIX_VERIFIED`
- `BUILD_VERIFIED`
- `SLIM_FEATURES_VERIFIED`
- `CPU_FLAGS_VERIFIED`
- `FREEDRENO_COMPAT_VERIFIED`
- `UI_VERIFIED`
- 有可用 Vulkan ICD 时出现 `VULKAN_VERIFIED`

## 9. 真机避坑

- 不要用 `-march=native` 或 `-mcpu=native` 重编；proot 看到的信息不可信。
- 若 Vulkan 崩溃，先用 `--gpu-backend opengl` 或 `BLENDER_GRAPHICS_MODE=software` 判断问题层。
- 若 Freedreno 未自动生效，检查 render node 是否可见、Mesa DRI 是否有 `msm_dri.so`、Vulkan ICD 是否有 `freedreno_icd*.json`。
- 关闭自动检测并手动指定驱动，用于排除 launcher 影响：

```sh
BLENDER_FREEDRENO_COMPAT=0 \
MESA_LOADER_DRIVER_OVERRIDE=msm \
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json \
blender --gpu-backend vulkan
```

- 长时 Cycles 渲染必须散热，否则会撞温度墙。
- OOM 时 `BLENDER_BUILD_JOBS=2`、配置 swap、关闭后台应用。最终 ThinLTO 链接固定单并发。

## 10. 产物与验收

可交接产物：

- `blender-linux-arm64_*.deb`：精简安装包；
- `blender-<version>-source.tar.xz`：Blender 源码、脚本、配置、文档；
- `BUILD-INFO.json`：source/dependency commit、CPU flags、feature matrix、Mesa/Freedreno 文件、install size；
- `SHA256SUMS`；
- CI logs：`mesa-freedreno.log`、`vulkaninfo.log`、`verify.log`、`slim-install.json`、`compile-flags.json`。

CI 通过只代表构建和软件图形链路通过。真机必须单独验证 Vulkan/OpenGL、Freedreno 检测和 Cycles CPU 渲染。
