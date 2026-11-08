#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit-test the Mesa Freedreno/Turnip environment detection in the launcher."""
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

print('FREEDRENO_COMPAT_VERIFIED', flush=True)
