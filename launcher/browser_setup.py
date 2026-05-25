"""
Playwright Chromium 浏览器自动检测与安装模块

功能：
1. 检测 Playwright Python 包是否已安装，未安装则自动 pip install
2. 检测 Playwright Chromium 浏览器是否已安装
3. 若未安装，调用内嵌的 Python 运行时自动下载安装
4. 提供安装进度回调，供 GUI 显示安装状态
"""
import os
import sys
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from loguru import logger


def _get_bundled_browser_dir() -> Optional[Path]:
    from launcher.frozen_detect import is_frozen, get_project_root
    if not is_frozen():
        return None
    candidate = get_project_root() / "ms-playwright"
    if candidate.exists():
        return candidate
    return None


def get_playwright_browser_dir() -> Optional[Path]:
    """
    获取 Playwright 浏览器目录。

    优先级：
    1. 打包目录下的 ms-playwright
    2. 环境变量 PLAYWRIGHT_BROWSERS_PATH
    3. Windows: %LOCALAPPDATA%\ms-playwright
    4. Linux/Mac: ~/.cache/ms-playwright
    """
    bundled_dir = _get_bundled_browser_dir()
    if bundled_dir:
        return bundled_dir

    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        candidate = Path(local_app) / "ms-playwright"
        if candidate.exists():
            return candidate

    candidate = Path.home() / ".cache" / "ms-playwright"
    if candidate.exists():
        return candidate

    return None


def ensure_playwright_browser_path() -> Optional[Path]:
    """设置 PLAYWRIGHT_BROWSERS_PATH 环境变量并返回浏览器目录。"""
    browser_dir = get_playwright_browser_dir()
    if browser_dir:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
        logger.info(f"Playwright 浏览器目录: {browser_dir}")
    return browser_dir


def get_chromium_executable_path() -> Optional[str]:
    """定位 Chromium 可执行文件路径。"""
    browser_dir = get_playwright_browser_dir()
    if browser_dir and browser_dir.exists():
        try:
            chromium_dirs = [d for d in browser_dir.iterdir() if d.is_dir() and "chromium" in d.name.lower()]
            for cdir in chromium_dirs:
                candidates = [
                    cdir / "chrome-win64" / "chrome.exe",
                    cdir / "chrome-win" / "chrome.exe",
                    cdir / "chrome-linux" / "chrome",
                    cdir / "chrome-linux64" / "chrome",
                    cdir / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
                ]
                for candidate in candidates:
                    if candidate.exists():
                        return str(candidate)
        except Exception as e:
            logger.warning(f"定位 Chromium 可执行文件失败: {e}")

    for candidate in (
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/chromium"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def is_playwright_package_installed() -> bool:
    """
    检测 Playwright Python 包是否已安装
    
    Returns:
        True 已安装，False 未安装
    """
    try:
        import playwright.async_api
        logger.info("Playwright Python 包已安装")
        return True
    except ImportError:
        logger.info("Playwright Python 包未安装")
        return False


def install_playwright_package(
    progress_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    使用 pip 安装 Playwright Python 包
    
    Args:
        progress_callback: 进度回调
        
    Returns:
        True 安装成功，False 安装失败
    """
    def _notify(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)
    
    try:
        _notify("正在安装 Playwright Python 包...")
        
        python_exe = _get_python_exe()
        cmd = [python_exe, "-m", "pip", "install", "playwright", "-q"]
        
        logger.info(f"执行安装命令: {' '.join(cmd)}")
        
        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        
        result = subprocess.run(cmd, **popen_kwargs)
        
        if result.returncode == 0:
            _notify("Playwright Python 包安装成功")
            return True
        else:
            _notify(f"Playwright Python 包安装失败: {result.stdout}")
            return False
            
    except Exception as e:
        _notify(f"安装 Playwright 包异常: {e}")
        return False


def _get_python_exe() -> str:
    """
    获取当前环境的 Python 解释器路径

    打包(Nuitka standalone)模式下使用同目录的 python.exe，
    开发模式使用当前解释器。

    Returns:
        Python 解释器路径
    """
    from launcher.frozen_detect import is_frozen
    if is_frozen():
        exe_dir = Path(sys.executable).parent
        for name in ("python.exe", "pythonw.exe", "python3.exe", "python"):
            candidate = exe_dir / name
            if candidate.exists():
                logger.info(f"打包模式使用内嵌 Python 解释器: {candidate}")
                return str(candidate)
        logger.warning("打包模式未找到同目录 Python 解释器，回退到当前 EXE")
        return sys.executable
    return sys.executable


def _find_driver_cmd_in_frozen_dir() -> Optional[list]:
    """
    打包模式下手动在 dist 目录中搜索 Playwright driver

    Nuitka standalone 会把 playwright/driver/ 下的 node.exe 和 cli.js
    一起打包到 dist 目录。当 Python 层面的 import 因兼容问题失败时，
    仍然可以通过直接调用这些文件来安装 Chromium。

    Returns:
        找到时返回 [node_exe, cli_js, "install", "chromium"]，否则返回 None
    """
    from launcher.frozen_detect import get_project_root
    root = get_project_root()

    # Playwright driver 在 Nuitka dist 中可能的位置
    search_bases = [
        root / "playwright" / "driver",
        root / "playwright" / "driver" / "package",
    ]

    node_exe = None
    cli_js = None

    # 查找 node 可执行文件
    for base in search_bases:
        for name in ("node.exe", "node"):
            candidate = base / name
            if candidate.exists():
                node_exe = str(candidate)
                break
        if node_exe:
            break

    # 查找 cli.js
    for base in search_bases:
        candidate = base / "package" / "cli.js"
        if candidate.exists():
            cli_js = str(candidate)
            break
        candidate = base / "cli.js"
        if candidate.exists():
            cli_js = str(candidate)
            break

    if node_exe and cli_js:
        logger.info(f"打包模式手动定位 driver: node={node_exe}, cli={cli_js}")
        return [node_exe, cli_js, "install", "chromium"]

    logger.warning(
        f"打包模式未找到 Playwright driver 文件 "
        f"(node_exe={node_exe}, cli_js={cli_js})"
    )
    return None


def is_chromium_installed() -> bool:
    """
    检测 Playwright Chromium 浏览器是否已安装

    打包(frozen)模式下只通过文件系统检查，不依赖 playwright 包导入；
    开发模式下先检查 playwright 包再走 registry 检查。

    Returns:
        True 已安装，False 未安装
    """
    from launcher.frozen_detect import is_frozen

    ensure_playwright_browser_path()

    # ---------- 打包模式：直接查找 chromium 可执行文件 ----------
    if is_frozen():
        chromium_path = get_chromium_executable_path()
        if chromium_path:
            logger.info(f"打包模式: Chromium 浏览器已安装: {chromium_path}")
            return True
        logger.info("打包模式: 未检测到 Chromium 浏览器")
        return False

    # ---------- 开发模式：先检查 playwright 包 ----------
    if not is_playwright_package_installed():
        logger.info("Playwright 包未安装，无法检测 Chromium")
        return False

    try:
        from playwright._impl._driver import compute_driver_executable
        driver_exe, _ = compute_driver_executable()
        if not os.path.exists(driver_exe):
            logger.info(f"Playwright driver 不存在: {driver_exe}")
            return False
    except Exception as e:
        logger.warning(f"检测 Playwright driver 失败: {e}")

    chromium_path = get_chromium_executable_path()
    if chromium_path:
        logger.info(f"Chromium 浏览器已安装: {chromium_path}")
        return True

    # 尝试用 playwright 自身 registry 检查
    try:
        from playwright._impl._browsers import get_playwright_browsers
        browsers = get_playwright_browsers()
        for b in browsers:
            if b.get("name") == "chromium" and b.get("installed"):
                logger.info("Chromium 浏览器已安装")
                return True
    except Exception as e:
        logger.warning(f"检测 Chromium registry 失败: {e}")

    logger.info("Chromium 浏览器未安装")
    return False


def install_chromium(
    progress_callback: Optional[Callable[[str], None]] = None,
    done_callback: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    在子线程中安装 Playwright Chromium 浏览器

    通过子进程调用 playwright install chromium，
    实时读取输出传递给 progress_callback 展示进度。

    Args:
        progress_callback: 进度回调 fn(message: str)，在子线程中调用
        done_callback: 完成回调 fn(success: bool, message: str)，在子线程中调用
    """
    def _notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    def _done(success: bool, msg: str):
        if done_callback:
            done_callback(success, msg)

    def _run():
        try:
            _notify("正在准备浏览器环境...")

            ensure_playwright_browser_path()

            # 使用 Playwright 内置的 driver（node.exe + cli.js）直接执行安装
            # 这样可以避免 Nuitka 打包后 python -m 的 self-execution 检测问题
            cmd = None
            try:
                from playwright._impl._driver import compute_driver_executable
                driver_exe, driver_cli = compute_driver_executable()
                cmd = [driver_exe, driver_cli, "install", "chromium"]
            except Exception as drv_err:
                logger.warning(f"通过 playwright API 获取 driver 失败: {drv_err}")

            # 回退1: 打包模式下手动在 dist 目录搜索 driver
            if cmd is None:
                from launcher.frozen_detect import is_frozen
                if is_frozen():
                    cmd = _find_driver_cmd_in_frozen_dir()

            # 回退2: 用独立 python.exe -m playwright
            if cmd is None:
                python_exe = _get_python_exe()
                cmd = [python_exe, "-m", "playwright", "install", "chromium"]

            logger.info(f"执行安装命令: {' '.join(cmd)}")
            _notify("正在修复 Chromium 浏览器环境（如需下载，约200MB，请耐心等待）...")

            # 打包为exe后无控制台，需显式设置stdin和creationflags防止句柄无效
            popen_kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(cmd, **popen_kwargs)

            # 实时读取输出
            last_line = ""
            for line in iter(process.stdout.readline, ""):
                line = line.strip()
                if not line:
                    continue
                last_line = line
                logger.info(f"[playwright install] {line}")

                # 解析下载进度
                if "%" in line:
                    _notify(f"下载中: {line}")
                elif "downloading" in line.lower() or "Downloading" in line:
                    _notify(f"下载中: {line}")
                elif "installing" in line.lower() or "Installing" in line:
                    _notify(f"安装中: {line}")
                else:
                    _notify(line)

            process.wait()
            exit_code = process.returncode

            if exit_code == 0:
                logger.info("Chromium 浏览器安装命令执行成功，进行二次校验...")
                _notify("正在校验浏览器安装...")
                
                # 二次复核：确认浏览器真的可用
                if is_chromium_installed():
                    logger.info("Chromium 浏览器安装成功并通过校验")
                    _notify("Chromium 浏览器安装完成！")
                    _done(True, "浏览器安装成功")
                else:
                    error_msg = "安装命令执行成功，但浏览器校验失败，可能安装不完整"
                    logger.error(error_msg)
                    _notify(error_msg)
                    _done(False, error_msg)
            else:
                error_msg = f"安装失败（退出码: {exit_code}）: {last_line}"
                logger.error(error_msg)
                _notify(f"安装失败: {last_line}")
                _done(False, error_msg)

        except FileNotFoundError:
            msg = "找不到 Python 解释器，无法安装浏览器"
            logger.error(msg)
            _notify(msg)
            _done(False, msg)
        except Exception as e:
            msg = f"安装浏览器时发生异常: {e}"
            logger.error(msg)
            _notify(str(e))
            _done(False, msg)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def check_and_install_chromium(
    progress_callback: Optional[Callable[[str], None]] = None,
    done_callback: Optional[Callable[[bool, str], None]] = None,
) -> Optional[threading.Thread]:
    """
    检测 Playwright 包和 Chromium 浏览器是否已安装，若未安装则自动下载

    流程：
    1. 检测 Playwright Python 包是否安装，未安装则 pip install
    2. 检测 Chromium 浏览器是否安装，未安装则下载

    Args:
        progress_callback: 进度回调
        done_callback: 完成回调 fn(success, message)
    Returns:
        如果需要安装返回安装线程，已安装返回 None
    """
    # 1. 检测 Playwright Python 包
    from launcher.frozen_detect import is_frozen
    if not is_playwright_package_installed():
        if is_frozen():
            # 打包模式下 playwright 应已内嵌于 Nuitka 产物
            # 导入失败可能是 Nuitka 动态导入兼容性问题，跳过 pip 安装
            # 直接进入浏览器检测与安装流程
            logger.warning(
                "打包模式下 Playwright 包导入失败，跳过 pip 安装，"
                "直接检测浏览器"
            )
            if progress_callback:
                progress_callback("检测到打包环境，跳过包安装，直接检查浏览器...")
        else:
            logger.info("Playwright Python 包未安装，开始自动安装...")
            if progress_callback:
                progress_callback("正在安装 Playwright Python 包...")

            if not install_playwright_package(progress_callback):
                if done_callback:
                    done_callback(False, "Playwright Python 包安装失败")
                return None

    # 2. 检测 Chromium 浏览器
    if is_chromium_installed():
        if done_callback:
            done_callback(True, "浏览器已就绪")
        return None

    logger.info("Chromium 未就绪，开始尝试修复...")
    return install_chromium(progress_callback, done_callback)
