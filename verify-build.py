"""Verify a slim Blender Linux ARM64 build in background mode."""
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
features = build_info.get("features", {})


def expected(option):
    return bool(features.get(option, False))


expected_version = os.environ.get("BLENDER_VERSION") or build_info.get("version")
if expected_version:
    assert bpy.app.version == tuple(map(int, expected_version.split("."))), bpy.app.version_string
assert platform.machine() == "aarch64", platform.machine()

# Record whether this execution environment hides SVE. The compile policy, not
# this runtime check, is what keeps SVE/SVE2 instructions out of the binary.
try:
    hwcap = ctypes.CDLL(None).getauxval(16)
    print(f"HWCap {hwcap:#x} SVE={bool(hwcap & (1 << 22))}", flush=True)
except (AttributeError, OSError):
    print("HWCap unavailable", flush=True)

device_types = _cycles.get_device_types()
assert not any(device_types), device_types
print("BACKENDS_VERIFIED CPU-only Cycles compute", flush=True)

cycles_feature_map = {
    'with_osl': 'WITH_CYCLES_OSL',
    'with_embree': 'WITH_CYCLES_EMBREE',
    'with_path_guiding': 'WITH_CYCLES_PATH_GUIDING',
    'with_openimagedenoise': 'WITH_OPENIMAGEDENOISE',
}
for attribute, option in cycles_feature_map.items():
    actual = getattr(_cycles, attribute, None)
    required = expected(option)
    assert bool(actual) == required, (attribute, actual, required)
print("CYCLES_FEATURES_VERIFIED " + " ".join(
    f"{name}={expected(option)}" for name, option in cycles_feature_map.items()), flush=True)

build_option_map = {
    'cycles': 'WITH_CYCLES',
    'cycles_osl': 'WITH_CYCLES_OSL',
    'codec_ffmpeg': 'WITH_CODEC_FFMPEG',
    'freestyle': 'WITH_FREESTYLE',
    'openvdb': 'WITH_OPENVDB',
    'alembic': 'WITH_ALEMBIC',
    'usd': 'WITH_USD',
    'fluid': 'WITH_MOD_FLUID',
    'xr_openxr': 'WITH_XR_OPENXR',
    'international': 'WITH_INTERNATIONAL',
    'libmv': 'WITH_LIBMV',
}
for attribute, option in build_option_map.items():
    actual = getattr(bpy.app.build_options, attribute)
    required = expected(option)
    assert bool(actual) == required, (attribute, actual, required)
print("SLIM_FEATURES_VERIFIED " + " ".join(
    f"{name}={expected(option)}" for name, option in build_option_map.items()), flush=True)

if build_info.get("vulkan_backend"):
    # Blender has no stable build_options.vulkan field. verify-vulkan.py checks
    # the live backend separately when a Vulkan ICD is available.
    print("VULKAN_BACKEND_BUILT expected; live backend probe is separate", flush=True)

(project_dir / "logs").mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 4
scene.cycles.use_denoising = expected('WITH_OPENIMAGEDENOISE')
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
      "SVE", build_info.get("sve", "unknown"), "slim", build_info.get("slim_profile", False),
      flush=True)
