"""
Playwright 浏览器工具模块

功能：
1. 检测是否运行在编译/打包模式
2. 获取项目根目录
3. 获取 Playwright 浏览器目录
4. 设置 PLAYWRIGHT_BROWSERS_PATH 环境变量
5. 定位 Chromium 可执行文件路径

此模块从 launcher.browser_setup 和 launcher.frozen_detect 提取，
供 websocket、scheduler 等服务在打包后独立运行时使用。
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


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
    try:
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

    编译模式下为exe所在目录，开发模式下为common的父目录

    Returns:
        项目根目录Path对象
    """
    if is_frozen():
        return Path(sys.executable).parent
    # 开发模式：common/utils 目录的父目录的父目录
    return Path(__file__).parent.parent.parent


def _get_bundled_browser_dir() -> Optional[Path]:
    """
    获取打包目录下的浏览器目录

    Returns:
        打包目录下的 ms-playwright 目录，不存在则返回 None
    """
    if not is_frozen():
        return None
    candidate = get_project_root() / "ms-playwright"
    if candidate.exists():
        return candidate
    return None


def get_playwright_browser_dir() -> Optional[Path]:
    """
    获取 Playwright 浏览器目录

    优先级：
    1. 打包目录下的 ms-playwright
    2. 环境变量 PLAYWRIGHT_BROWSERS_PATH
    3. Windows: %LOCALAPPDATA%\\ms-playwright
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
    """
    设置 PLAYWRIGHT_BROWSERS_PATH 环境变量并返回浏览器目录

    Returns:
        浏览器目录路径，未找到则返回 None
    """
    browser_dir = get_playwright_browser_dir()
    if browser_dir:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
        logger.info(f"Playwright 浏览器目录: {browser_dir}")
    return browser_dir


def _get_chromium_revision(browser_package: str) -> str | None:
    """读取浏览器自动化包要求的 Chromium revision。"""
    try:
        package = importlib.import_module(browser_package)
        package_dir = Path(package.__file__).parent
        browsers_file = package_dir / "driver" / "package" / "browsers.json"
        browsers = json.loads(browsers_file.read_text(encoding="utf-8"))["browsers"]
        for browser in browsers:
            if browser.get("name") == "chromium":
                return str(browser.get("revision") or "").strip() or None
    except Exception as exc:
        logger.warning(f"读取 {browser_package} Chromium revision 失败: {exc}")
    return None


def get_chromium_executable_path(
    browser_package: str = "playwright",
    *,
    strict_revision: bool = False,
) -> Optional[str]:
    """
    定位指定自动化包对应的 Chromium 可执行文件路径

    Args:
        browser_package: ``playwright`` 或 ``patchright``，用于匹配各自要求的 revision。
        strict_revision: 是否只接受该包要求的精确 revision。

    Returns:
        Chromium 可执行文件的完整路径，未找到则返回 None
    """
    browser_dir = get_playwright_browser_dir()
    if browser_dir and browser_dir.exists():
        try:
            chromium_dirs = [
                d for d in browser_dir.iterdir()
                if d.is_dir() and "chromium" in d.name.lower()
            ]
            revision = _get_chromium_revision(browser_package)
            if strict_revision and not revision:
                return None
            if revision:
                preferred_name = f"chromium-{revision}".lower()
                preferred_dirs = [
                    directory
                    for directory in chromium_dirs
                    if directory.name.lower() == preferred_name
                ]
                if preferred_dirs:
                    chromium_dirs = preferred_dirs
                elif strict_revision:
                    return None
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

    # 回退：检查系统安装的 Chromium
    for candidate in (
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/chromium"),
    ):
        if candidate.exists():
            return str(candidate)

    return None
