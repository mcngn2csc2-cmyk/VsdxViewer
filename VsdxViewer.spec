# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for VsdxViewer (PySide6 + QtWebEngine).

Build:
  Windows:  build.bat
  Linux/Mac: ./build.sh
  Manual:   pyinstaller VsdxViewer.spec
"""

import sys
import os
from pathlib import Path
import PySide6

PYSIDE6_DIR = Path(PySide6.__file__).parent

# ── Collect PySide6 binaries/data needed by QtWebEngine ──────────────────────
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = []
binaries = []

# WebEngine resources (translations, pak files, icudtl.dat …)
for subdir in ("resources", "translations"):
    candidate = PYSIDE6_DIR / "Qt" / subdir
    if not candidate.exists():
        candidate = PYSIDE6_DIR / subdir          # flat layout on some builds
    if candidate.exists():
        datas.append((str(candidate), f"PySide6/Qt/{subdir}"))

# QtWebEngineProcess helper executable
for name in ("QtWebEngineProcess", "QtWebEngineProcess.exe"):
    for search in [
        PYSIDE6_DIR / "Qt" / "libexec",
        PYSIDE6_DIR / "Qt" / "bin",
        PYSIDE6_DIR,
    ]:
        proc = search / name
        if proc.exists():
            binaries.append((str(proc), str(proc.parent.relative_to(PYSIDE6_DIR.parent))))
            break

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # PySide6 submodules that PyInstaller may miss
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
        "PySide6.QtSvg",
        "PySide6.QtNetwork",
        "PySide6.QtPrintSupport",
        "PySide6.QtPositioning",
        # App modules
        "converter",
        "pdf_converter",
        "preview_extractor",
        "worker",
        "thumbnail_panel",
        "web_viewer",
        # Visio COM (pywin32)
        "win32com",
        "win32com.client",
        "win32com.server",
        "pywintypes",
        "win32api",
        # PyMuPDF
        "fitz",
        "fitz.utils",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # trim unused heavy Qt modules
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtSerialPort",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "tkinter",
        "matplotlib",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── onedir: fastest startup, single folder to distribute ─────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VsdxViewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no black console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",      # uncomment and add icon.ico to enable
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VsdxViewer",
)
