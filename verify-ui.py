"""Check a factory-default desktop window and initialized graphics backend."""
import bpy
import gpu


def verify_ui():
    windows = list(bpy.context.window_manager.windows)
    has_viewport = any(area.type == "VIEW_3D" for window in windows for area in window.screen.areas)
    renderer = gpu.platform.renderer_get()
    backend = gpu.platform.backend_type_get()
    if has_viewport and renderer and renderer.strip():
        print("UI_VERIFIED", bpy.app.version_string, backend, renderer, flush=True)
    else:
        print("UI_VERIFICATION_FAILED", len(windows), has_viewport, backend, renderer, flush=True)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(verify_ui, first_interval=5)
