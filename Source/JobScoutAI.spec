# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files
from pathlib import Path
import sys


customtkinter_datas = collect_data_files("customtkinter")
branding_datas = [
    (str(Path("assets") / "jobscout_logo.png"), "assets"),
    (str(Path("assets") / "jobscout_icon.ico"), "assets"),
]
python_basis = Path(sys.base_prefix)
tkinter_datas = [
    (str(python_basis / "Lib" / "tkinter"), "tkinter"),
    (str(python_basis / "tcl" / "tcl8.6"), "_tcl_data"),
    (str(python_basis / "tcl" / "tk8.6"), "_tk_data"),
]
tkinter_binaries = [
    (str(python_basis / "DLLs" / "_tkinter.pyd"), "."),
    (str(python_basis / "DLLs" / "tcl86t.dll"), "."),
    (str(python_basis / "DLLs" / "tk86t.dll"), "."),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=tkinter_binaries,
    datas=customtkinter_datas + tkinter_datas + branding_datas,
    hiddenimports=["tkinter", "_tkinter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_tkinter_runtime.py"],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobScoutAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=str(Path("assets") / "jobscout_icon.ico"),
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JobScoutAI",
)
