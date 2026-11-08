#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Select a working graphics backend and apply Mesa/Freedreno compatibility."""
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile

GRAPHICS_POLICY = 'vulkan-first-freedreno-v2'
DRI_DIRS = (
    '/usr/lib/aarch64-linux-gnu/dri',
    '/usr/local/lib/aarch64-linux-gnu/dri',
    '/usr/lib/dri',
    '/usr/lib64/dri',
    '/vendor/lib64/dri',
    '/system/lib64/dri',
)
ICD_DIRS = (
    '/usr/share/vulkan/icd.d',
    '/usr/local/share/vulkan/icd.d',
    '/etc/vulkan/icd.d',
    '/vendor/etc/vulkan/icd.d',
)
FREEDRENO_ENV_KEYS = (
    'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE', 'LD_LIBRARY_PATH',
    'DRI_PRIME', 'MESA_LOADER_DRIVER_OVERRIDE', 'GALLIUM_DRIVER',
    'MESA_VK_DEVICE_SELECT', 'VK_ICD_FILENAMES', 'VK_DRIVER_FILES',
    'XDG_RUNTIME_DIR', 'MESA_SHADER_CACHE_DIR',
    'VK_LOADER_DRIVERS_SELECT', 'LIBGL_DRIVERS_PATH', 'FD_MESA_DEBUG',
    'TU_DEBUG', 'MESA_GL_VERSION_OVERRIDE', 'MESA_GLSL_VERSION_OVERRIDE',
)

PROBE = '''import bpy, gpu
bpy.ops.wm.read_factory_settings(use_empty=False)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = 8
scene.render.resolution_y = 8
scene.render.resolution_percentage = 100
bpy.ops.render.render()
renderer = gpu.platform.renderer_get()
assert gpu.platform.device_type_get() != "SOFTWARE", renderer
assert not any(x in renderer.lower() for x in ("llvmpipe", "softpipe", "lavapipe")), renderer
assert gpu.platform.backend_type_get() == "EXPECTED_BACKEND"
print("BLENDER_HARDWARE_PROBE_OK", flush=True)
'''


def truthy(value):
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def find_first(patterns, directories):
    for pattern in patterns:
        for directory in map(Path, directories):
            if not directory.is_dir():
                continue
            matches = sorted(directory.glob(pattern))
            if matches:
                return matches[0]
    return None


def prepare_proot_environment(environment, cache_dir):
    """Fix runtime/display paths that commonly disappear inside proot/chroot."""
    if not truthy(environment.get('BLENDER_PROOT_COMPAT', '1')):
        return {'enabled': False, 'reason': 'disabled by BLENDER_PROOT_COMPAT'}
    changes = {}

    runtime_dir = environment.get('XDG_RUNTIME_DIR')
    runtime_path = Path(runtime_dir) if runtime_dir else None
    runtime_usable = bool(runtime_path and runtime_path.is_dir() and
                          os.access(runtime_path, os.W_OK | os.X_OK))
    if not runtime_usable:
        fallback = Path(tempfile.gettempdir()) / f"runtime-{os.getuid()}"
        try:
            fallback.mkdir(parents=True, exist_ok=True, mode=0o700)
            environment['XDG_RUNTIME_DIR'] = str(fallback)
            runtime_path = fallback
            changes['XDG_RUNTIME_DIR'] = str(fallback)
        except OSError:
            runtime_path = None

    # A stale Wayland display from the host often survives into proot while its
    # socket does not. Remove it so Blender can use X11 instead of failing.
    wayland_display = environment.get('WAYLAND_DISPLAY')
    wayland_socket = None
    if wayland_display:
        wayland_socket = Path(wayland_display)
        if not wayland_socket.is_absolute() and runtime_path is not None:
            wayland_socket = runtime_path / wayland_display
        if not wayland_socket.exists():
            environment.pop('WAYLAND_DISPLAY', None)
            changes['WAYLAND_DISPLAY'] = 'removed (socket missing)'
            wayland_socket = None
            if environment.get('DISPLAY'):
                environment.setdefault('XDG_SESSION_TYPE', 'x11')
                changes['XDG_SESSION_TYPE'] = environment['XDG_SESSION_TYPE']

    shader_cache = cache_dir / 'mesa-shader-cache'
    if not environment.get('MESA_SHADER_CACHE_DIR'):
        try:
            shader_cache.mkdir(parents=True, exist_ok=True, mode=0o700)
            environment['MESA_SHADER_CACHE_DIR'] = str(shader_cache)
            changes['MESA_SHADER_CACHE_DIR'] = str(shader_cache)
        except OSError:
            pass

    report = {
        'enabled': True,
        'runtime_dir': str(runtime_path) if runtime_path else None,
        'wayland_socket': str(wayland_socket) if wayland_socket else None,
        'display': environment.get('DISPLAY'),
        'changes': changes,
    }
    try:
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (cache_dir / 'proot.json').write_text(json.dumps(report, indent=2) + '\n')
    except OSError:
        pass
    return report


def configure_freedreno(environment, cache_dir, device_paths=None):
    """Apply Freedreno/Turnip environment when an Adreno render node is present.

    Mesa names the native Freedreno Gallium DRI module msm_dri.so on mainline
    Linux; some trees use freedreno_dri.so or kgsl_dri.so. Turnip is exposed by
    the freedreno Vulkan ICD. Containers do not always select either driver
    automatically, so set the loader hints only when the user has not chosen a
    different driver explicitly.
    """
    if not truthy(environment.get('BLENDER_FREEDRENO_COMPAT', '1')):
        return {'enabled': False, 'reason': 'disabled by BLENDER_FREEDRENO_COMPAT'}

    if device_paths is None:
        drm_dir = Path('/dev/dri')
        render_nodes = sorted(drm_dir.glob('renderD*')) if drm_dir.is_dir() else []
        kgsl = Path('/dev/kgsl-3d0')
        if kgsl.exists():
            render_nodes.append(kgsl)
    else:
        render_nodes = [Path(path) for path in device_paths if Path(path).exists()]
    dri_module = find_first(('msm_dri.so', 'freedreno_dri.so', 'kgsl_dri.so'), DRI_DIRS)
    icd_file = find_first(
        ('freedreno_icd.aarch64.json', 'turnip_icd.aarch64.json',
         'freedreno_icd.json', 'turnip_icd.json', '*freedreno*icd*.json',
         '*turnip*icd*.json'),
        ICD_DIRS,
    )

    applied = {}
    if render_nodes and dri_module is not None:
        if not environment.get('MESA_LOADER_DRIVER_OVERRIDE') and not environment.get('GALLIUM_DRIVER'):
            override = dri_module.name.removesuffix('_dri.so')
            environment['MESA_LOADER_DRIVER_OVERRIDE'] = override
            applied['MESA_LOADER_DRIVER_OVERRIDE'] = override

    if (render_nodes and icd_file is not None and
            not environment.get('VK_DRIVER_FILES') and not environment.get('VK_ICD_FILENAMES')):
        environment['VK_DRIVER_FILES'] = str(icd_file)
        # Older Vulkan loaders only understand VK_ICD_FILENAMES.
        environment['VK_ICD_FILENAMES'] = str(icd_file)
        applied['VK_DRIVER_FILES'] = str(icd_file)
        applied['VK_ICD_FILENAMES'] = str(icd_file)

    report = {
        'enabled': True,
        'render_nodes': [str(path) for path in render_nodes],
        'dri_module': str(dri_module) if dri_module else None,
        'vulkan_icd': str(icd_file) if icd_file else None,
        'applied': applied,
    }
    try:
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (cache_dir / 'freedreno.json').write_text(json.dumps(report, indent=2) + '\n')
    except OSError:
        pass
    return report


def fingerprint(program, environment):
    """Invalidate the cache after application, driver, device or session changes."""
    paths = [program, program.parent / 'BUILD-INFO.json', Path(__file__).resolve()]
    for directory in ['/dev/dri', '/dev/kgsl-3d0', *DRI_DIRS, *ICD_DIRS]:
        location = Path(directory)
        paths.append(location)
        if location.is_dir():
            paths.extend(sorted(location.iterdir()))
    for name in ['libEGL_mesa.so.0', 'libGLX_mesa.so.0', 'libvulkan.so.1']:
        paths.append(Path('/usr/lib/aarch64-linux-gnu') / name)
    records = []
    for path in paths:
        try:
            stat = path.stat()
            records.append((str(path), stat.st_size, stat.st_mtime_ns, stat.st_ino,
                            stat.st_mode, stat.st_uid, stat.st_gid))
        except OSError:
            records.append((str(path), None))
    data = [GRAPHICS_POLICY, platform.release(), os.getuid(), os.getgroups(), records,
            {key: environment.get(key) for key in FREEDRENO_ENV_KEYS}]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def hardware_works(program, backend, environment, log_path):
    command = [str(program), '--gpu-backend', backend, '-noaudio', '--background',
               '--factory-startup', '--python-exit-code', '1', '--python-expr',
               PROBE.replace('EXPECTED_BACKEND', backend.upper())]
    process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = process.communicate()
    try:
        log_path.write_bytes(output)
    except OSError:
        pass
    return process.returncode == 0 and b'BLENDER_HARDWARE_PROBE_OK' in output


def select_graphics(program, environment, cache_dir):
    key = fingerprint(program, environment)
    cache = cache_dir / 'graphics.json'
    try:
        entry = json.loads(cache.read_text())
        if entry.get('fingerprint') == key and entry.get('backend') in ['opengl', 'vulkan']:
            if entry.get('mode') in ['hardware', 'software']:
                return entry['mode'], entry['backend']
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        pass
    mode, backend = 'software', 'opengl'
    for candidate in ['vulkan', 'opengl']:
        if hardware_works(program, candidate, environment, cache_dir / f'probe-{candidate}.log'):
            mode, backend = 'hardware', candidate
            break
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=cache_dir, delete=False) as file:
            json.dump(dict(fingerprint=key, mode=mode, backend=backend), file)
            temporary = Path(file.name)
        os.replace(temporary, cache)
    except OSError:
        if 'temporary' in locals():
            temporary.unlink(missing_ok=True)
    return mode, backend


def launch(program, arguments, environment, cache_dir):
    mode = environment.get('BLENDER_GRAPHICS_MODE', 'auto').lower()
    if mode not in ['auto', 'hardware', 'software']:
        raise SystemExit('BLENDER_GRAPHICS_MODE must be auto, hardware or software.')
    backend_args = []
    information_only = any(x in arguments for x in ['--help', '-h', '/?', '--version', '-v'])
    explicit_backend = any(x == '--gpu-backend' or x.startswith('--gpu-backend=') for x in arguments)
    background = any(x in arguments for x in ['--background', '-b'])
    inherited_software = truthy(environment.get('LIBGL_ALWAYS_SOFTWARE'))
    software_requested = mode == 'software' or inherited_software or (mode == 'auto' and background)

    if not information_only:
        prepare_proot_environment(environment, cache_dir)
        if software_requested:
            environment['LIBGL_ALWAYS_SOFTWARE'] = '1'
        else:
            environment.pop('LIBGL_ALWAYS_SOFTWARE', None)
            configure_freedreno(environment, cache_dir)

    if information_only or (mode == 'auto' and explicit_backend):
        return [str(program), *arguments], environment

    if mode == 'hardware':
        environment.pop('LIBGL_ALWAYS_SOFTWARE', None)
    elif mode == 'software':
        environment['LIBGL_ALWAYS_SOFTWARE'] = '1'
        if not explicit_backend:
            backend_args = ['--gpu-backend', 'opengl']
    elif inherited_software:
        backend_args = ['--gpu-backend', 'opengl']
    elif background:
        # CPU-only batch jobs need no hardware probe. Scripts that initialize a
        # viewport or Workbench can still use software OpenGL in the same process.
        environment['LIBGL_ALWAYS_SOFTWARE'] = '1'
        backend_args = ['--gpu-backend', 'opengl']
    else:
        probe_environment = dict(environment)
        probe_environment.pop('LIBGL_ALWAYS_SOFTWARE', None)
        selected, backend = select_graphics(program, probe_environment, cache_dir)
        if selected == 'software':
            environment['LIBGL_ALWAYS_SOFTWARE'] = '1'
        else:
            environment.pop('LIBGL_ALWAYS_SOFTWARE', None)
        backend_args = ['--gpu-backend', backend]
    return [str(program), *backend_args, *arguments], environment


def main():
    program = Path(__file__).resolve().parent / 'blender'
    cache_dir = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'blender-linux-arm64'
    command, environment = launch(program, sys.argv[1:], dict(os.environ), cache_dir)
    os.execve(program, command, environment)


if __name__ == '__main__':
    main()
