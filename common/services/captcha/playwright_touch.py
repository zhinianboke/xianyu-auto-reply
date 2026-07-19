"""
Playwright 无头滑块的触摸协议工具。

功能：
1. 统一滑块请求与浏览器页面的 Chrome UA/Client Hints。
2. 通过 CDP 发送带触点物理参数的拖动，不调用系统鼠标或窗口输入。
"""
from __future__ import annotations

import random
import time
from typing import Any, Sequence, Tuple


SLIDER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)
TouchPoint = Tuple[float, float, float]


def configure_slider_user_agent(context: Any, page: Any) -> None:
    """
    配置与 token 请求一致的 Chrome 139 Windows 指纹。

    Args:
        context: Playwright 浏览器上下文。
        page: 当前滑块页面。
    Returns:
        None
    """
    session = context.new_cdp_session(page)
    session.send(
        "Emulation.setUserAgentOverride",
        {
            "userAgent": SLIDER_USER_AGENT,
            "acceptLanguage": "zh-CN,zh;q=0.9,en;q=0.8",
            "platform": "Win32",
            "userAgentMetadata": {
                "brands": [
                    {"brand": "Not;A=Brand", "version": "99"},
                    {"brand": "Google Chrome", "version": "139"},
                    {"brand": "Chromium", "version": "139"},
                ],
                "fullVersionList": [
                    {"brand": "Not;A=Brand", "version": "99.0.0.0"},
                    {"brand": "Google Chrome", "version": "139.0.0.0"},
                    {"brand": "Chromium", "version": "139.0.0.0"},
                ],
                "fullVersion": "139.0.0.0",
                "platform": "Windows",
                "platformVersion": "10.0.0",
                "architecture": "x86",
                "model": "",
                "mobile": False,
                "bitness": "64",
                "wow64": False,
            },
        },
    )


def dispatch_touch_drag(
    page: Any,
    start_x: float,
    start_y: float,
    trajectory: Sequence[TouchPoint],
) -> None:
    """
    通过浏览器协议派发一段触摸拖动，不触碰操作系统鼠标。

    Args:
        page: 当前滑块页面。
        start_x: 滑块按钮中心 X 坐标。
        start_y: 滑块按钮中心 Y 坐标。
        trajectory: 相对起点的 (x, y, delay_seconds) 轨迹。
    Returns:
        None
    """
    if not trajectory:
        raise ValueError("触摸轨迹不能为空")

    session = page.context.new_cdp_session(page)
    radius_x = 4.0
    radius_y = 4.0
    rotation = 0.0
    force = 0.5

    def send(event_type: str, x: float, y: float, active: bool = True) -> None:
        """发送一个带接触面积、方向和压力的触摸事件。"""
        touch_point = {
            "id": 0,
            "x": x,
            "y": y,
            "radiusX": radius_x,
            "radiusY": radius_y,
            "rotationAngle": rotation,
            "force": force,
            "tangentialPressure": 0.0,
        }
        session.send(
            "Input.dispatchTouchEvent",
            {
                "type": event_type,
                "touchPoints": [touch_point] if active else [],
                "modifiers": 0,
                "timestamp": time.time(),
            },
        )

    send("touchStart", start_x, start_y)
    time.sleep(random.uniform(0.06, 0.11))
    for offset_x, offset_y, delay in trajectory:
        send("touchMove", start_x + offset_x, start_y + offset_y)
        time.sleep(delay)
    time.sleep(random.uniform(0.20, 0.30))
    end_x, end_y, _ = trajectory[-1]
    send("touchEnd", start_x + end_x, start_y + end_y, active=False)
