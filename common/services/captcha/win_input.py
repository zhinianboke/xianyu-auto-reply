"""
Windows 真实鼠标输入注入（SendInput）+ 高精度定时器

用途：
    真实鼠标滑块引擎回放真人轨迹时，用本模块的 SendInput 注入替代 pyautogui.moveTo。

为什么需要：
    pyautogui.moveTo 走 SetCursorPos（光标 warp），操作系统只按帧率对光标位置采样一次，
    浏览器 PointerEvent.getCoalescedEvents() 每帧只能拿到约 1 个子事件；而真人硬件鼠标一帧内
    会上报多个高频子事件（每帧 2~8 个），阿里风控正是通过这个"合并前子事件密度"识别合成输入。
    SendInput 走真正的输入事件栈：一帧内背靠背连发多个移动会被 Chrome 合并，
    getCoalescedEvents 即可返回多个子事件，逼近真人硬件密度。

注意：SendInput 注入到当前 Windows 前台窗口，调用前必须确保目标 Chrome 是前台窗口。
      本模块仅提供输入原语，前台归属由调用方（windows_foreground）保证。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

_ULONG_PTR = wintypes.WPARAM


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]

    _anonymous_ = ("i",)
    _fields_ = [("type", wintypes.DWORD), ("i", _I)]


_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004

# GetSystemMetrics 索引：虚拟桌面（覆盖所有显示器）左上角与尺寸
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79


def virtual_screen() -> tuple:
    """返回虚拟桌面 (left, top, width, height)（物理像素，覆盖多屏）。"""
    g = ctypes.windll.user32.GetSystemMetrics
    return (
        g(_SM_XVIRTUALSCREEN),
        g(_SM_YVIRTUALSCREEN),
        g(_SM_CXVIRTUALSCREEN),
        g(_SM_CYVIRTUALSCREEN),
    )


_VX, _VY, _VCX, _VCY = virtual_screen()


def send_move_abs(x: int, y: int) -> None:
    """通过 SendInput 以绝对屏幕物理像素坐标移动光标（真实输入事件，可被 Chrome 合并成 coalesced）。

    Args:
        x, y: 目标点的屏幕物理像素坐标
    """
    # 归一化到 0..65535 的虚拟桌面绝对坐标（多屏安全）
    nx = int((x - _VX) * 65535 / max(1, _VCX - 1))
    ny = int((y - _VY) * 65535 / max(1, _VCY - 1))
    mi = _MOUSEINPUT(nx, ny, 0,
                     _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK, 0, 0)
    inp = _INPUT(_INPUT_MOUSE)
    inp.mi = mi
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def send_button(down: bool) -> None:
    """通过 SendInput 按下/抬起鼠标左键。

    Args:
        down: True 按下，False 抬起
    """
    flag = _MOUSEEVENTF_LEFTDOWN if down else _MOUSEEVENTF_LEFTUP
    mi = _MOUSEINPUT(0, 0, 0, flag, 0, 0)
    inp = _INPUT(_INPUT_MOUSE)
    inp.mi = mi
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def timer_resolution(on: bool) -> None:
    """开/关 Windows 高精度定时器(1ms)。

    Windows 默认定时器精度约 15.6ms，会让 5ms 级别的 sleep 严重超时、破坏回放节拍。
    回放前 timer_resolution(True)、回放后 timer_resolution(False) 成对调用。
    """
    try:
        if on:
            ctypes.windll.winmm.timeBeginPeriod(1)
        else:
            ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def precise_sleep(target_perf: float) -> None:
    """精密睡眠到 time.perf_counter() == target_perf。

    大段用 sleep 让出 CPU，末端约 1.5ms 自旋等待，兼顾 CPU 占用与定时精度。

    Args:
        target_perf: 目标 perf_counter 时刻（秒）
    """
    while True:
        remain = target_perf - time.perf_counter()
        if remain <= 0:
            return
        if remain > 0.002:
            time.sleep(remain - 0.0015)
