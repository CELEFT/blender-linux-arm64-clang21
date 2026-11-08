"""Check that this Blender process initialized the Vulkan GPU backend."""
import bpy
import gpu


def verify_vulkan():
    backend = gpu.platform.backend_type_get()
    renderer = gpu.platform.renderer_get()
    print("VULKAN_BACKEND", backend, renderer, flush=True)
    ok = backend == "VULKAN"
    print("VULKAN_VERIFIED" if ok else "VULKAN_VERIFICATION_FAILED", backend, renderer, flush=True)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(verify_vulkan, first_interval=5)
