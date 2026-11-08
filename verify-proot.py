#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit-test proot and Mesa Freedreno/Turnip environment adaptation."""
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('blender_launcher', ROOT / 'blender-launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

with tempfile.TemporaryDirectory(prefix='blender-freedreno-test.') as temporary:
    root = Path(temporary)
    dri_dir = root / 'dri'
    icd_dir = root / 'icd.d'
    cache_dir = root / 'cache'
    dri_dir.mkdir()
    icd_dir.mkdir()
    (dri_dir / 'msm_dri.so').touch()
    icd = icd_dir / 'freedreno_icd.aarch64.json'
    icd.write_text('{}\n')
    render_node = root / 'renderD128'
    render_node.touch()

    launcher.DRI_DIRS = (str(dri_dir),)
    launcher.ICD_DIRS = (str(icd_dir),)

    environment = {}
    report = launcher.configure_freedreno(
        environment, cache_dir, device_paths=[render_node])
    assert environment['MESA_LOADER_DRIVER_OVERRIDE'] == 'msm', environment
    assert environment['VK_DRIVER_FILES'] == str(icd), environment
    assert environment['VK_ICD_FILENAMES'] == str(icd), environment
    assert report['applied']['MESA_LOADER_DRIVER_OVERRIDE'] == 'msm', report
    assert json.loads((cache_dir / 'freedreno.json').read_text())['vulkan_icd'] == str(icd)
    print('FREEDRENO_DETECTION_VERIFIED msm + Turnip ICD', flush=True)

    explicit = {
        'MESA_LOADER_DRIVER_OVERRIDE': 'zink',
        'VK_DRIVER_FILES': '/custom/gpu_icd.json',
    }
    launcher.configure_freedreno(explicit, cache_dir, device_paths=[render_node])
    assert explicit['MESA_LOADER_DRIVER_OVERRIDE'] == 'zink', explicit
    assert explicit['VK_DRIVER_FILES'] == '/custom/gpu_icd.json', explicit
    assert 'VK_ICD_FILENAMES' not in explicit, explicit
    gallium = {'GALLIUM_DRIVER': 'zink'}
    launcher.configure_freedreno(gallium, cache_dir, device_paths=[render_node])
    assert 'MESA_LOADER_DRIVER_OVERRIDE' not in gallium, gallium
    print('FREEDRENO_OVERRIDE_VERIFIED explicit driver choices preserved', flush=True)

    no_device = {}
    launcher.configure_freedreno(no_device, cache_dir, device_paths=[])
    assert 'MESA_LOADER_DRIVER_OVERRIDE' not in no_device, no_device
    assert 'VK_DRIVER_FILES' not in no_device, no_device
    print('FREEDRENO_NO_DEVICE_VERIFIED no forced driver without hardware node', flush=True)

    probe_env = {}
    command, launched_env = launcher.launch(
        root / 'blender', ['--background', '-b', 'scene.blend', '--render-frame', '1'],
        probe_env, cache_dir)
    assert launched_env['LIBGL_ALWAYS_SOFTWARE'] == '1', launched_env
    assert command[-3:] == ['scene.blend', '--render-frame', '1'], command
    print('BACKGROUND_SOFTWARE_POLICY_VERIFIED no hardware probe in CPU batch mode', flush=True)

    # Proot adaptation: create a usable runtime dir, discard a stale Wayland
    # socket, keep X11 available, and set a writable Mesa shader cache.
    proot_env = {'HOME': str(root), 'WAYLAND_DISPLAY': 'wayland-9', 'DISPLAY': ':99'}
    report = launcher.prepare_proot_environment(proot_env, cache_dir)
    assert Path(proot_env['XDG_RUNTIME_DIR']).is_dir(), proot_env
    assert proot_env['XDG_RUNTIME_DIR'] == report['runtime_dir'], report
    assert Path(proot_env['MESA_SHADER_CACHE_DIR']).is_dir(), proot_env
    assert 'WAYLAND_DISPLAY' not in proot_env, proot_env
    assert proot_env['XDG_SESSION_TYPE'] == 'x11', proot_env
    assert json.loads((cache_dir / 'proot.json').read_text())['display'] == ':99'
    print('PROOT_ENVIRONMENT_VERIFIED stale Wayland removed; runtime/cache created', flush=True)

    explicit_runtime = root / 'runtime'
    explicit_runtime.mkdir()
    wayland_socket = explicit_runtime / 'wayland-0'
    wayland_socket.touch()
    preserved = {'XDG_RUNTIME_DIR': str(explicit_runtime), 'WAYLAND_DISPLAY': 'wayland-0'}
    launcher.prepare_proot_environment(preserved, cache_dir)
    assert preserved['XDG_RUNTIME_DIR'] == str(explicit_runtime), preserved
    assert preserved['WAYLAND_DISPLAY'] == 'wayland-0', preserved
    print('PROOT_DISPLAY_PRESERVE_VERIFIED usable Wayland socket kept', flush=True)

    disabled = {'BLENDER_PROOT_COMPAT': '0'}
    launcher.prepare_proot_environment(disabled, cache_dir)
    assert 'XDG_RUNTIME_DIR' not in disabled, disabled
    assert 'MESA_SHADER_CACHE_DIR' not in disabled, disabled
    print('PROOT_DISABLE_VERIFIED BLENDER_PROOT_COMPAT=0 respected', flush=True)

print('PROOT_FREEDRENO_COMPAT_VERIFIED', flush=True)
