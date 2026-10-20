# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller：macOS → .app；Windows → 单文件 .exe。

PySide6 不整体收集：PyInstaller 的 hook 会按实际导入（QtCore/QtGui/QtWidgets）
带上对应 DLL 与插件，避免把 Qt3D/WebEngine 等无关模块打进安装包。
"""

import platform

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("bin", "bin")],
    hiddenimports=[],
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
    upx=False,
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
        upx=False,
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
        upx=False,
        upx_exclude=[],
        name="VideoCombining",
    )
