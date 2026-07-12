"""
Windows Chrome 前台窗口激活工具

功能：
1. 通过临时页面标题精确定位 Playwright 当前页面所属的 Chrome 顶层窗口
2. 使用 Win32 前台窗口 API 激活目标窗口，并验证系统输入确实会发送给该窗口
3. 支持已知窗口句柄的快速再次校验，供物理鼠标操作前使用
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes
from typing import Any, List, Optional, Tuple


_CHROME_WINDOW_CLASS = "Chrome_WidgetWin_1"
_GA_ROOT = 2
_ASFW_ANY = -1
_SW_RESTORE = 9
_SW_MAXIMIZE = 3
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_HWND_TOP = 0
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_SHOWWINDOW = 0x0040
_VK_MENU = 0x12
_KEYEVENTF_KEYUP = 0x0002

if sys.platform == "win32":
    _USER32 = ctypes.WinDLL("user32", use_last_error=True)
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    _USER32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _USER32.EnumWindows.restype = wintypes.BOOL
    _USER32.IsWindow.argtypes = [wintypes.HWND]
    _USER32.IsWindow.restype = wintypes.BOOL
    _USER32.IsWindowVisible.argtypes = [wintypes.HWND]
    _USER32.IsWindowVisible.restype = wintypes.BOOL
    _USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _USER32.GetWindowTextLengthW.restype = ctypes.c_int
    _USER32.GetWindowTextW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    _USER32.GetWindowTextW.restype = ctypes.c_int
    _USER32.GetClassNameW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    _USER32.GetClassNameW.restype = ctypes.c_int
    _USER32.GetForegroundWindow.restype = wintypes.HWND
    _USER32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _USER32.GetAncestor.restype = wintypes.HWND
    _USER32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _USER32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _USER32.AttachThreadInput.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.BOOL,
    ]
    _USER32.AttachThreadInput.restype = wintypes.BOOL
    _USER32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _USER32.BringWindowToTop.argtypes = [wintypes.HWND]
    _USER32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _USER32.SetActiveWindow.argtypes = [wintypes.HWND]
    _USER32.SetFocus.argtypes = [wintypes.HWND]
    _USER32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    _USER32.AllowSetForegroundWindow.restype = wintypes.BOOL
    _USER32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    try:
        _USER32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    except AttributeError:
        pass
    _KERNEL32.GetCurrentThreadId.restype = wintypes.DWORD
else:
    _USER32 = None
    _KERNEL32 = None
    _WNDENUMPROC = None


def _as_hwnd(value: int) -> wintypes.HWND:
    """把整数窗口句柄转换为 ctypes HWND。"""
    return wintypes.HWND(value)


def _handle_value(value: Any) -> int:
    """把 ctypes HWND 或整数统一转换为整数。"""
    return int(ctypes.cast(value, ctypes.c_void_p).value or 0)


def _find_chrome_window(title_marker: str) -> Optional[int]:
    """按唯一页面标题查找可见 Chrome 顶层窗口。"""
    if not _USER32 or not _WNDENUMPROC:
        return None

    matches: List[int] = []

    @_WNDENUMPROC
    def _enum_window(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> bool:
        if not _USER32.IsWindowVisible(hwnd):
            return True
        title_length = _USER32.GetWindowTextLengthW(hwnd)
        if title_length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        _USER32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
        if title_marker not in title_buffer.value:
            return True
        class_buffer = ctypes.create_unicode_buffer(256)
        _USER32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
        if class_buffer.value == _CHROME_WINDOW_CLASS:
            matches.append(_handle_value(hwnd))
            return False
        return True

    _USER32.EnumWindows(_enum_window, 0)
    return matches[0] if matches else None


def _root_window(hwnd: Any) -> int:
    """返回窗口的顶层根句柄。"""
    if not _USER32 or not hwnd:
        return 0
    root = _USER32.GetAncestor(hwnd, _GA_ROOT)
    return _handle_value(root or hwnd)


def is_foreground_window(hwnd: int) -> bool:
    """判断目标窗口是否为 Windows 当前真实前台窗口。"""
    if not _USER32 or not hwnd or not _USER32.IsWindow(_as_hwnd(hwnd)):
        return False
    foreground = _USER32.GetForegroundWindow()
    return bool(foreground) and _root_window(foreground) == _root_window(_as_hwnd(hwnd))


def _request_foreground(hwnd: int, send_alt: bool) -> None:
    """使用线程输入队列和置顶切换请求 Windows 激活目标窗口。"""
    if not _USER32 or not _KERNEL32:
        return

    target = _as_hwnd(hwnd)
    foreground = _USER32.GetForegroundWindow()
    current_thread = int(_KERNEL32.GetCurrentThreadId())
    target_pid = wintypes.DWORD(0)
    target_thread = int(_USER32.GetWindowThreadProcessId(target, ctypes.byref(target_pid)))
    foreground_thread = (
        int(_USER32.GetWindowThreadProcessId(foreground, None))
        if foreground
        else 0
    )

    attached: List[Tuple[int, int]] = []
    pairs = (
        (current_thread, foreground_thread),
        (current_thread, target_thread),
        (foreground_thread, target_thread),
    )
    for first, second in pairs:
        if not first or not second or first == second or (first, second) in attached:
            continue
        if _USER32.AttachThreadInput(first, second, True):
            attached.append((first, second))

    try:
        try:
            _USER32.AllowSetForegroundWindow(_ASFW_ANY)
            if target_pid.value:
                _USER32.AllowSetForegroundWindow(target_pid.value)
        except Exception:
            pass
        _USER32.ShowWindow(target, _SW_RESTORE)
        _USER32.ShowWindow(target, _SW_MAXIMIZE)
        flags = _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW
        _USER32.SetWindowPos(target, _as_hwnd(_HWND_TOPMOST), 0, 0, 0, 0, flags)
        _USER32.SetWindowPos(target, _as_hwnd(_HWND_NOTOPMOST), 0, 0, 0, 0, flags)
        _USER32.SetWindowPos(target, _as_hwnd(_HWND_TOP), 0, 0, 0, 0, flags)
        _USER32.BringWindowToTop(target)
        if send_alt:
            _USER32.keybd_event(_VK_MENU, 0, 0, 0)
        try:
            _USER32.SetForegroundWindow(target)
            if hasattr(_USER32, "SwitchToThisWindow"):
                _USER32.SwitchToThisWindow(target, True)
        finally:
            if send_alt:
                _USER32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
        _USER32.SetActiveWindow(target)
        _USER32.SetFocus(target)
    finally:
        for first, second in reversed(attached):
            _USER32.AttachThreadInput(first, second, False)


def activate_window(hwnd: int) -> Tuple[bool, str]:
    """激活已知窗口句柄，并返回可用于日志的校验结果。"""
    if sys.platform != "win32" or not _USER32:
        return False, "not_windows"
    if not hwnd or not _USER32.IsWindow(_as_hwnd(hwnd)):
        return False, f"invalid_hwnd={hwnd}"

    for send_alt in (False, True):
        _request_foreground(hwnd, send_alt)
        deadline = time.monotonic() + 0.4
        while time.monotonic() < deadline:
            if is_foreground_window(hwnd):
                return True, f"hwnd={hwnd}, foreground={hwnd}"
            time.sleep(0.04)

    foreground = _handle_value(_USER32.GetForegroundWindow())
    return False, f"hwnd={hwnd}, foreground={foreground}"


def activate_page_window(
    page: Any,
    timeout_seconds: float = 2.0,
) -> Tuple[bool, Optional[int], str]:
    """精确定位并激活 Playwright 页面所属的 Chrome 顶层窗口。"""
    if sys.platform != "win32":
        return False, None, "not_windows"

    marker = (
        f"realmouse-{os.getpid()}-{threading.get_native_id()}-{time.time_ns()}"
    )
    original_title = ""
    try:
        original_title = page.title()
        page.bring_to_front()
        page.evaluate("marker => { document.title = marker; }", marker)
        deadline = time.monotonic() + max(0.2, timeout_seconds)
        hwnd = None
        while time.monotonic() < deadline:
            hwnd = _find_chrome_window(marker)
            if hwnd:
                break
            time.sleep(0.05)
        if not hwnd:
            return False, None, "chrome_window_not_found"
        success, detail = activate_window(hwnd)
        return success, hwnd, detail
    except Exception as exc:
        return False, None, f"activation_error={type(exc).__name__}: {exc}"
    finally:
        try:
            page.evaluate("title => { document.title = title; }", original_title)
        except Exception:
            pass
