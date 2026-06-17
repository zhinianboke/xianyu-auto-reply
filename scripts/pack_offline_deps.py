"""
离线依赖打包脚本 - 在联网机器上运行

功能:
    1. 从所有 pyproject.toml 中提取依赖
    2. 去重合并生成 requirements_all.txt
    3. 使用 pip download 下载所有 wheel 包到 offline_packages 目录
    4. 在输出目录中生成离线安装脚本 install.bat

用法:
    python scripts/pack_offline_deps.py
    或: pack_deps.bat（Windows双击运行）

输出:
    offline_packages/
        ├── *.whl              # 所有依赖的wheel包
        ├── requirements.txt   # 合并后的依赖清单
        └── install.bat        # 离线安装脚本（复制到目标机器运行）
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# 项目根目录
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "offline_packages"

# 所有 pyproject.toml 文件路径（相对于项目根目录）
PYPROJECT_FILES = [
    "backend-web/pyproject.toml",
    "websocket/pyproject.toml",
    "scheduler/pyproject.toml",
    "promotion/backend/pyproject.toml",
]

# 额外需要包含的依赖（编译工具等）
# 说明：部分包（pyautogui/pyscreeze/pytweening）在 PyPI 上只有源码包(.tar.gz)，
#       离线机器安装时需要现场编译，编译隔离环境依赖 setuptools 和 wheel，
#       因此必须把它们一并打进离线包，否则会报 "Could not find ... wheel"。
EXTRA_DEPS = [
    "cython>=3.0.0",
    "setuptools>=68.0",
    "wheel>=0.40.0",
]


def extract_deps_from_toml(toml_path):
    """
    从 pyproject.toml 中提取 dependencies 列表

    Args:
        toml_path: pyproject.toml 文件路径

    Returns:
        依赖字符串列表
    """
    try:
        import tomllib
    except ImportError:
        # Python 3.10 及以下版本
        try:
            import tomli as tomllib
        except ImportError:
            print(f"  [警告] 无法解析 {toml_path}（需要Python 3.11+或安装tomli）")
            return []

    try:
        with open(toml_path, 'rb') as f:
            data = tomllib.load(f)
        deps = data.get('project', {}).get('dependencies', [])
        return deps
    except Exception as e:
        print(f"  [警告] 读取 {toml_path} 失败: {e}")
        return []


def normalize_dep_name(dep_str):
    """
    提取依赖包名（去除版本号和extras），用于去重

    Args:
        dep_str: 如 "fastapi>=0.104.0" 或 "uvicorn[standard]>=0.24.0"

    Returns:
        小写的包名，如 "fastapi" 或 "uvicorn"
    """
    name = dep_str.split('>=')[0].split('<=')[0].split('==')[0].split('!=')[0].split('>')[0].split('<')[0]
    name = name.split('[')[0]  # 去除extras
    return name.strip().lower()


def merge_dependencies():
    """
    从所有 pyproject.toml 提取并合并依赖，去重

    Returns:
        去重后的依赖列表
    """
    all_deps = {}  # {包名小写: 原始依赖字符串}

    for rel_path in PYPROJECT_FILES:
        toml_path = PROJECT_ROOT / rel_path
        if not toml_path.exists():
            print(f"  [跳过] {rel_path} 不存在")
            continue

        deps = extract_deps_from_toml(toml_path)
        print(f"  {rel_path}: {len(deps)} 个依赖")

        for dep in deps:
            name = normalize_dep_name(dep)
            # 保留版本号更高的那个（简单处理：后出现的覆盖前面的）
            if name not in all_deps:
                all_deps[name] = dep

    # 添加额外依赖
    for dep in EXTRA_DEPS:
        name = normalize_dep_name(dep)
        if name not in all_deps:
            all_deps[name] = dep

    return sorted(all_deps.values(), key=lambda x: normalize_dep_name(x))


def write_requirements(deps, output_path):
    """
    将依赖列表写入 requirements.txt

    Args:
        deps: 依赖字符串列表
        output_path: 输出文件路径
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        for dep in deps:
            f.write(dep + '\n')
    print(f"  已写入: {output_path} ({len(deps)} 个依赖)")


def download_packages(requirements_path, output_dir):
    """
    使用 pip wheel 将所有依赖（含仅有源码包的依赖）预编译为 wheel 包

    说明：
        使用 pip wheel 而非 pip download，可在联网机器上把 pyautogui/pyscreeze/
        pytweening 等仅提供源码包(.tar.gz)的依赖直接编译成 .whl，
        从而保证离线机器安装时无需任何编译，避免缺少 wheel/编译工具导致失败。

    Args:
        requirements_path: requirements.txt 路径
        output_dir: 输出（wheel）目标目录
    """
    cmd = [
        sys.executable, '-m', 'pip', 'wheel',
        '-r', str(requirements_path),
        '-w', str(output_dir),
    ]

    print(f"  执行: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd)

    if result.returncode != 0:
        print()
        print("  [错误] 部分依赖编译/下载失败，请检查网络连接和依赖版本")
        return False

    return True


def generate_install_bat(output_dir):
    """
    在输出目录中生成离线安装脚本

    Args:
        output_dir: 输出目录路径
    """
    install_bat = output_dir / "install.bat"
    content = """@echo off
REM ==========================================
REM Offline Dependency Installer
REM Run this script on the offline machine
REM
REM Requirements: Python 3.11+
REM ==========================================

chcp 65001 >nul 2>&1

REM 切换到脚本所在目录（解决路径含空格的问题）
cd /d "%~dp0"

echo ==========================================
echo   Offline Dependency Installer
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found, please install Python 3.11+
    pause
    exit /b 1
)

echo [INFO] Installing dependencies from local packages...
echo.

pip install --no-index --find-links=. -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Install failed. Make sure Python version matches.
) else (
    echo.
    echo [OK] All dependencies installed successfully!
)

echo.
pause
"""
    with open(install_bat, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  已生成: {install_bat}")


def count_packages(output_dir):
    """统计下载的包文件数量和总大小"""
    total_size = 0
    count = 0
    for f in output_dir.iterdir():
        if f.suffix in ('.whl', '.tar.gz', '.zip'):
            total_size += f.stat().st_size
            count += 1
    return count, total_size


def main():
    """主入口"""
    print("=" * 50)
    print("  闲鱼自动回复系统 - 离线依赖打包")
    print("=" * 50)
    print()
    print(f"[信息] 项目目录: {PROJECT_ROOT}")
    print(f"[信息] 输出目录: {OUTPUT_DIR}")
    print(f"[信息] Python: {sys.version}")
    print()

    # ====== 步骤1: 提取并合并依赖 ======
    print("[步骤 1/3] 从 pyproject.toml 提取依赖...")
    deps = merge_dependencies()
    print(f"  合并去重后共 {len(deps)} 个依赖")
    print()

    # ====== 步骤2: 准备输出目录 ======
    print("[步骤 2/3] 准备输出目录...")
    if OUTPUT_DIR.exists():
        print(f"  清理旧目录: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # 写入 requirements.txt
    req_path = OUTPUT_DIR / "requirements.txt"
    write_requirements(deps, req_path)

    # 生成离线安装脚本
    generate_install_bat(OUTPUT_DIR)
    print()

    # ====== 步骤3: 下载wheel包 ======
    print("[步骤 3/3] 下载依赖包（可能需要几分钟）...")
    print()
    ok = download_packages(req_path, OUTPUT_DIR)
    print()

    if not ok:
        print("[警告] 部分依赖下载失败，请检查后重试")
        print()

    # ====== 统计结果 ======
    pkg_count, total_size = count_packages(OUTPUT_DIR)
    size_mb = total_size / 1024 / 1024

    print("=" * 50)
    print("  离线依赖打包完成!")
    print("=" * 50)
    print()
    print(f"  输出目录:   {OUTPUT_DIR}")
    print(f"  依赖包数量: {pkg_count} 个")
    print(f"  总大小:     {size_mb:.1f} MB")
    print()
    print("使用方法:")
    print(f"  1. 将 {OUTPUT_DIR.name} 整个目录复制到目标机器")
    print(f"  2. 在目标机器上双击运行 {OUTPUT_DIR.name}\\install.bat")
    print()
    print("注意事项:")
    print(f"  - 目标机器需要安装相同大版本的 Python（当前: {sys.version.split()[0]}）")
    print(f"  - 目标机器系统需要是 Windows x86_64")
    print(f"  - 如需 Playwright 浏览器，安装后还需运行:")
    print(f"    python -m playwright install chromium")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
