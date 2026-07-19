"""
真人鼠标滑块的跨机器坐标校准模块。

功能：
1. 根据浏览器窗口几何建立主视口到物理屏幕的初始映射
2. 使用页面实际收到的 Windows 真实鼠标事件修正坐标误差
3. 根据当前滑块按钮与滑轨尺寸计算实际拖动距离
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from common.services.captcha.win_input import (
    DPI_AWARENESS_STATUS,
    send_move_abs,
    virtual_screen,
)


@dataclass
class ScreenMapper:
    """主视口 CSS 坐标到 Windows 物理屏幕坐标的线性映射。"""

    offset_x: float
    offset_y: float
    dpr: float
    correction_x: float = 0.0
    correction_y: float = 0.0

    def to_screen(self, viewport_x: float, viewport_y: float) -> Tuple[int, int]:
        """将主视口 CSS 坐标转换为校准后的物理屏幕坐标。"""
        x = (self.offset_x + viewport_x) * self.dpr + self.correction_x
        y = (self.offset_y + viewport_y) * self.dpr + self.correction_y
        return int(round(x)), int(round(y))


def build_geometry_mapper(page: Any) -> Tuple[ScreenMapper, Dict[str, float]]:
    """
    根据浏览器窗口几何创建初始坐标映射。

    Args:
        page: Playwright 页面对象
    Returns:
        屏幕映射器和原始窗口几何信息
    """
    geometry = page.evaluate(
        """() => ({
          screenX: window.screenX,
          screenY: window.screenY,
          outerWidth: window.outerWidth,
          outerHeight: window.outerHeight,
          innerWidth: window.innerWidth,
          innerHeight: window.innerHeight,
          devicePixelRatio: window.devicePixelRatio
        })"""
    )
    dpr = float(geometry.get("devicePixelRatio") or 1.0)
    border_x = max(0.0, (geometry["outerWidth"] - geometry["innerWidth"]) / 2.0)
    top_chrome = max(
        0.0,
        (geometry["outerHeight"] - geometry["innerHeight"]) - border_x,
    )
    mapper = ScreenMapper(
        offset_x=float(geometry["screenX"]) + border_x,
        offset_y=float(geometry["screenY"]) + top_chrome,
        dpr=dpr,
    )
    return mapper, geometry


def compute_slider_distance(frame: Any, button: Any, track: Any) -> float:
    """
    根据当前 DOM 尺寸计算滑块按钮中心需要移动的实际距离。

    Args:
        frame: 滑块所在 Playwright Frame
        button: 滑块按钮元素
        track: 滑轨元素
    Returns:
        CSS 像素拖动距离，无法计算时返回 0
    """
    try:
        distance = frame.evaluate(
            """() => {
              const button = document.querySelector('#nc_1_n1z');
              const track = document.querySelector('#nc_1_n1t')
                || document.querySelector('.nc_scale');
              if (!button || !track) return null;
              return track.getBoundingClientRect().width
                - button.getBoundingClientRect().width;
            }"""
        )
        if distance and float(distance) > 0:
            return float(distance)
    except Exception:
        pass
    button_box = button.bounding_box() if button else None
    track_box = track.bounding_box() if track else None
    if button_box and track_box:
        return max(0.0, float(track_box["width"]) - float(button_box["width"]))
    return 0.0


def _clear_events(page: Any, frame: Any) -> None:
    """清空主页面与滑块 frame 的鼠标校准事件。"""
    for target in (page, frame):
        try:
            target.evaluate("() => { window.__cal = []; }")
        except Exception:
            continue


def _read_observation(
    page: Any,
    frame: Any,
    frame_center: Tuple[float, float],
    viewport_center: Tuple[float, float],
) -> Tuple[Tuple[Any, ...], Tuple[float, float], str]:
    """读取最后一条真实鼠标事件及其对应坐标系目标点。"""
    try:
        frame_events = frame.evaluate("() => window.__cal || []") or []
    except Exception:
        frame_events = []
    if frame_events:
        return tuple(frame_events[-1]), frame_center, "slider_frame"
    try:
        page_events = page.evaluate("() => window.__cal || []") or []
    except Exception:
        page_events = []
    if page_events:
        return tuple(page_events[-1]), viewport_center, "main_frame"
    return (), viewport_center, "none"


def calibrate_slider_center(
    page: Any,
    frame: Any,
    button: Any,
    mapper: ScreenMapper,
) -> Tuple[bool, Dict[str, Any]]:
    """
    用真实鼠标移动事件校准滑块中心，并返回诊断数据。

    Args:
        page: Playwright 页面对象
        frame: 滑块所在 Frame
        button: 滑块按钮元素
        mapper: 初始屏幕坐标映射器
    Returns:
        是否在 2 CSS 像素误差内完成校准，以及诊断信息
    """
    box = button.bounding_box()
    if not box:
        return False, {"error": "button_bounding_box_unavailable"}
    viewport_center = (
        float(box["x"]) + float(box["width"]) / 2.0,
        float(box["y"]) + float(box["height"]) / 2.0,
    )
    local_center_value = button.evaluate(
        """element => {
          const rect = element.getBoundingClientRect();
          return [rect.left + rect.width / 2, rect.top + rect.height / 2];
        }"""
    )
    frame_center = (float(local_center_value[0]), float(local_center_value[1]))
    predicted = mapper.to_screen(*viewport_center)
    observation: Tuple[Any, ...] = ()
    target_center = viewport_center
    source = "none"
    candidate_offset = (0, 0)

    # 初始预测通常已很接近；周边探测用于处理跨屏 DPI 导致的较大固定偏差。
    offsets = ((0, 0), (-100, 0), (100, 0), (0, -80), (0, 80))
    for offset_x, offset_y in offsets:
        _clear_events(page, frame)
        candidate = (predicted[0] + offset_x, predicted[1] + offset_y)
        send_move_abs(candidate[0] - 12, candidate[1] - 8)
        time.sleep(0.04)
        send_move_abs(*candidate)
        time.sleep(0.14)
        observation, target_center, source = _read_observation(
            page,
            frame,
            frame_center,
            viewport_center,
        )
        if observation:
            candidate_offset = (offset_x, offset_y)
            break
    if not observation:
        return False, {
            "error": "page_received_no_real_mouse_event",
            "dpi_awareness": DPI_AWARENESS_STATUS,
            "virtual_screen": virtual_screen(),
            "viewport_center": viewport_center,
            "predicted_screen": predicted,
        }

    error_x = target_center[0] - float(observation[0])
    error_y = target_center[1] - float(observation[1])
    mapper.correction_x += candidate_offset[0] + error_x * mapper.dpr
    mapper.correction_y += candidate_offset[1] + error_y * mapper.dpr
    corrected = mapper.to_screen(*viewport_center)

    _clear_events(page, frame)
    send_move_abs(*corrected)
    time.sleep(0.16)
    verified, verified_target, verified_source = _read_observation(
        page,
        frame,
        frame_center,
        viewport_center,
    )
    if not verified:
        verified = observation
        verified_target = target_center
        verified_source = source
    verified_error = (
        verified_target[0] - float(verified[0]),
        verified_target[1] - float(verified[1]),
    )
    diagnostics = {
        "dpi_awareness": DPI_AWARENESS_STATUS,
        "virtual_screen": virtual_screen(),
        "dpr": mapper.dpr,
        "viewport_center": viewport_center,
        "frame_center": frame_center,
        "predicted_screen": predicted,
        "first_source": source,
        "first_observed": tuple(observation[:4]),
        "correction_physical": (mapper.correction_x, mapper.correction_y),
        "corrected_screen": corrected,
        "verified_source": verified_source,
        "verified_observed": tuple(verified[:4]),
        "verified_error_css": verified_error,
    }
    calibrated = abs(verified_error[0]) <= 2.0 and abs(verified_error[1]) <= 2.0
    return calibrated, diagnostics
