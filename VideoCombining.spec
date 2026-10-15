# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller：macOS → .app；Windows → 单文件 .exe。"""

import platform

from PyInstaller.utils.hooks import collect_all

block_cipher = None

pyside_datas, pyside_binaries, pyside_hidden = collect_all("PySide6")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=pyside_binaries,
    datas=[("bin", "bin")] + pyside_datas,
    hiddenimports=pyside_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_exe_kw = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if platform.system() == "Windows":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="VideoCombining",
        exclude_binaries=False,
        **_exe_kw,
    )
elif platform.system() == "Darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="VideoCombining",
        **_exe_kw,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="VideoCombining",
    )
    app = BUNDLE(
        coll,
        name="VideoCombining.app",
        icon=None,
        bundle_identifier="com.videocombining.app",
        info_plist={
            "CFBundleName": "VideoCombining",
            "CFBundleDisplayName": "视频拼接",
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="VideoCombining",
        **_exe_kw,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="VideoCombining",
    )
