# -*- mode: python ; coding: utf-8 -*-
"""AICM-NT4K DV监控界面 PyInstaller 打包配置。

产物: dist/AICM-NT4K DV监控界面/AICM-NT4K DV监控界面.exe (+ _internal/ 资源目录)
与旧 CAN 工具同形态: zlgcan.dll、VC 运行库、dev_info.json 均随包分发。
"""
import os
import sys


def _find_conda_dll(*names: str) -> list[str]:
    """anaconda 的原生 DLL 在 Library\\bin 而非 DLLs，PyInstaller 钩子
    找不到（sqlite3.dll、_ctypes 依赖的 ffi.dll），显式找出来随包分发。
    扫描顺序: Library\\bin, DLLs, python 同目录。"""
    exe_dir = os.path.dirname(sys.executable)
    search_dirs = (
        os.path.join(exe_dir, "Library", "bin"),
        os.path.join(exe_dir, "DLLs"),
        exe_dir,
    )
    found = []
    for name in names:
        for d in search_dirs:
            p = os.path.join(d, name)
            if os.path.exists(p):
                found.append(p)
                break
        else:
            print(f"WARNING: {name} not found next to the running python; "
                  f"frozen app may fail to import its dependent module.")
    return found


_EXTRA_DLLS = _find_conda_dll(
    "sqlite3.dll", "ffi.dll",
    "libexpat.dll", "libcrypto-3-x64.dll", "libssl-3-x64.dll",
    "liblzma.dll", "LIBBZ2.dll",
)

datas = [
    ("config", "config"),
    ("dbc", "dbc"),
    ("can_driver/dev_info.json", "can_driver"),
    # 周立功官方 kerneldlls（zlgcan.dll 运行时按自身目录查找该文件夹），
    # 必须整体随包分发才能打开 USBCANFD/UCANFD 设备
    ("can_driver/kerneldlls", "can_driver/kerneldlls"),
]

binaries = [
    ("can_driver/zlgcan.dll", "can_driver"),
    # 智嵌物联 ZQWL 适配器专用的 ZCAN 兼容库（USB-CDC/串口），与其 MSVC 依赖同目录
    ("can_driver/zlgcan_zqwl.dll", "can_driver"),
    # PEAK PCAN-Basic API DLL（用户需将 PCANBasic.dll 放入 can_driver/）
    ("can_driver/PCANBasic.dll", "can_driver"),
    # 官方 zlgcan.dll 及其 kerneldlls 依赖 VS2013 运行库（ZPSCANFD.dll 另需 VS2015 的 140 系列）
    ("can_driver/msvcr120.dll", "can_driver"),
    ("can_driver/msvcp120.dll", "can_driver"),
    ("can_driver/MSVCP140.dll", "can_driver"),
    ("can_driver/VCRUNTIME140.dll", "can_driver"),
    ("can_driver/VCRUNTIME140_1.dll", "can_driver"),
]
for dll in _EXTRA_DLLS:
    binaries.append((dll, "."))

hiddenimports = []

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 应用只用 PyQt5/pyqtgraph/numpy；以下为 anaconda 附带、本应用未用的重型包
        "tkinter", "matplotlib", "PIL", "pytest",
        "scipy", "h5py", "zmq", "lxml", "yaml",
        "pandas", "sympy", "sklearn", "IPython", "jedi", "parso",
        "sphinx", "sphinxcontrib", "docutils", "jinja2", "babel",
        "black", "jupyter", "nbformat", "jsonschema",
        "numba", "llvmlite", "win32com", "pythoncom",
        "cryptography", "bcrypt", "nacl", "paramiko", "pywt",
        "pygments", "bottleneck",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AICM-NT4K DV监控界面",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="packaging/hia_logo.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AICM-NT4K DV监控界面",
)
