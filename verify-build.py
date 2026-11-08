"""Run with the newly built Blender in background mode."""
import ctypes
import json
import os
from pathlib import Path
import platform

import bpy
import numpy
import _cycles

project_dir = Path(__file__).resolve().parent
info_path = project_dir / "logs" / "build-info.json"
build_info = json.loads(info_path.read_text()) if info_path.is_file() else {}

expected_version = os.environ.get("BLENDER_VERSION") or build_info.get("version")
if expected_version:
    assert bpy.app.version == tuple(map(int, expected_version.split("."))), bpy.app.version_string
assert platform.machine() == "aarch64", platform.machine()

# Report whether the kernel exposes SVE. Android/proot normally reports no SVE,
# which is exactly why the build forces -mcpu=cortex-x4+nosve+nosve2.
try:
    hwcap = ctypes.CDLL(None).getauxval(16)
    print(f"HWCap {hwcap:#x} SVE={bool(hwcap & (1 << 22))}", flush=True)
except (AttributeError, OSError):
    print("HWCap unavailable", flush=True)

device_types = _cycles.get_device_types()
assert not any(device_types), device_types
print("BACKENDS_VERIFIED Snapdragon 8s Gen 3 profile: CPU-only Cycles compute", flush=True)

cycles_features = ["with_osl", "with_path_guiding"]
if build_info.get("embree", True):
    cycles_features.append("with_embree")
if build_info.get("openimagedenoise", True):
    cycles_features.append("with_openimagedenoise")
for feature in cycles_features:
    assert getattr(_cycles, feature), feature
print("CYCLES_FEATURES_VERIFIED " + " ".join(cycles_features), flush=True)

for feature in ("cycles", "cycles_osl", "codec_ffmpeg", "freestyle", "openvdb",
                "alembic", "usd", "fluid", "xr_openxr"):
    assert getattr(bpy.app.build_options, feature), feature
print("RELEASE_FEATURES_VERIFIED Cycles OSL FFmpeg Freestyle OpenVDB Alembic USD fluids OpenXR", flush=True)
if build_info.get("vulkan_backend", True):
    # Blender does not consistently expose a build_options.vulkan attribute.
    # The actual backend is checked separately by verify-vulkan.py on a Vulkan ICD.
    print("VULKAN_BACKEND_BUILT expected; backend probe is a separate CI step", flush=True)

(project_dir / "logs").mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 4
scene.cycles.use_denoising = bool(build_info.get("openimagedenoise", True))
scene.render.resolution_x = 64
scene.render.resolution_y = 64
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(project_dir / "logs" / "smoke-render.png")
bpy.ops.render.render(write_still=True)
assert Path(scene.render.filepath).is_file()
bpy.ops.wm.save_as_mainfile(filepath=str(project_dir / "logs" / "smoke-scene.blend"))
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.filepath = str(project_dir / "logs" / "smoke-workbench.png")
bpy.ops.render.render(write_still=True)
assert Path(scene.render.filepath).is_file()
import gpu
print("GRAPHICS_VERIFIED", gpu.platform.renderer_get(), gpu.platform.version_get())
print("BUILD_VERIFIED", bpy.app.version_string, platform.machine(),
      "NumPy", numpy.__version__, "CPU", build_info.get("cpu_flags", "unknown"),
      "SVE", build_info.get("sve", "unknown"), flush=True)
