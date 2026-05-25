"""
编译模式检测工具

功能：
1. 统一检测是否运行在编译模式（Nuitka/PyInstaller/cx_Freeze等）
2. 获取项目根目录（编译模式下为exe所在目录，开发模式下为launcher的父目录）

Nuitka 使用 __compiled__ 变量，PyInstaller 使用 sys.frozen
"""
import sys
from pathlib import Path


def is_frozen() -> bool:
    """
    检测当前是否运行在编译/打包模式
    
    支持：
    - Nuitka: 检测 __compiled__ 变量
    - PyInstaller/cx_Freeze: 检测 sys.frozen 属性
    
    Returns:
        True 表示运行在编译模式，False 表示开发模式
    """
    # Nuitka 编译后会在模块中注入 __compiled__ 变量
    # 需要检查 builtins 或者通过 __name__ 检测
    try:
        # Nuitka standalone 模式检测
        import __main__
        if hasattr(__main__, "__compiled__"):
            return True
    except Exception:
        pass
    
    # Nuitka 也可以通过检测 sys.executable 是否指向 .exe 且不是 python.exe
    if sys.platform == "win32":
        exe_name = Path(sys.executable).name.lower()
        # 如果 exe 名称不是 python 相关的，说明是编译后的程序
        if exe_name not in ("python.exe", "pythonw.exe", "python3.exe", "python"):
            # 进一步确认不是在虚拟环境中
            if not exe_name.startswith("python"):
                return True
    
    # PyInstaller / cx_Freeze 检测
    if getattr(sys, "frozen", False):
        return True
    
    return False


def get_project_root() -> Path:
    """
    获取项目根目录
    
    编译模式下为exe所在目录，开发模式下为launcher的父目录
    
    Returns:
        项目根目录Path对象
    """
    if is_frozen():
        return Path(sys.executable).parent
    # 开发模式：launcher 目录的父目录
    return Path(__file__).parent.parent
