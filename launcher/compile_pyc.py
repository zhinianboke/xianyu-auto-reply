"""
源码编译工具

功能：
1. 将指定目录下所有.py文件编译为.pyc字节码文件
2. 编译成功后删除.py源文件（仅处理发布目录中的副本，不影响原始代码）
3. 保留目录结构不变，.pyc文件放在__pycache__同级目录

注意：此脚本只在打包流程中对发布目录中的副本执行，绝不会修改原始项目源码
"""
import compileall
import os
import py_compile
import sys
from pathlib import Path


def compile_directory(target_dir: str) -> bool:
    """
    将目录下所有.py编译为.pyc，然后删除.py源文件
    
    编译后的.pyc文件直接放在.py同级目录（如main.py -> main.pyc），
    而不是放在__pycache__中。这样Python可以直接加载.pyc文件，
    无需.py源文件存在。
    
    Args:
        target_dir: 要编译的目录路径（应为发布目录中的副本）
    Returns:
        True编译成功，False编译失败
    """
    target = Path(target_dir)
    if not target.exists():
        print(f"[WARN] Directory not found: {target_dir}")
        return False
    
    print(f"[INFO] Compiling .py to .pyc in: {target_dir}")
    
    success_count = 0
    fail_count = 0
    
    # 遍历所有.py文件
    for py_file in target.rglob("*.py"):
        try:
            # 编译为.pyc，直接放在.py同级目录（如 main.py -> main.pyc）
            # 这样Python可以直接加载，无需源文件
            pyc_file = py_file.with_suffix(".pyc")
            py_compile.compile(str(py_file), cfile=str(pyc_file), doraise=True)
            # 删除 .py 源文件（仅删除发布目录副本）
            py_file.unlink()
            success_count += 1
        except py_compile.PyCompileError as e:
            print(f"[WARN] Compile failed: {py_file} - {e}")
            fail_count += 1
    
    # 删除所有 __pycache__ 目录（不再需要）
    for pycache in target.rglob("__pycache__"):
        if pycache.is_dir():
            import shutil
            shutil.rmtree(pycache, ignore_errors=True)
    
    print(f"[INFO] Compiled {success_count} files, {fail_count} failures in {target_dir}")
    return fail_count == 0


def main():
    """
    主函数：接收命令行参数指定要编译的目录列表
    
    用法: python compile_pyc.py <dir1> <dir2> ...
    """
    if len(sys.argv) < 2:
        print("Usage: python compile_pyc.py <dir1> [dir2] ...")
        sys.exit(1)
    
    all_ok = True
    for directory in sys.argv[1:]:
        if not compile_directory(directory):
            all_ok = False
    
    if not all_ok:
        print("[WARN] Some files failed to compile")
        sys.exit(1)
    else:
        print("[INFO] All files compiled successfully")


if __name__ == "__main__":
    main()
