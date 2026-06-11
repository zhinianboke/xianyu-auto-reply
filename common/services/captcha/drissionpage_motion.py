"""
DrissionPage 滑块运动逻辑

包含与浏览器页面交互的两块运动逻辑：
1. calculate_slide_distance：根据轨道宽度/页面分辨率动态计算滑动距离；
2. execute_tracks：按轨迹逐步移动鼠标，叠加垂直抖动与 sin 节律速度波动。

从 drissionpage_slider.py 拆出，便于控制单文件行数并独立维护运动细节。
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, List

from loguru import logger


def calculate_slide_distance(page: Any, log_tag: str = "") -> int:
    """动态计算滑动距离，适应不同分辨率。

    Args:
        page: DrissionPage 标签页对象
        log_tag: 日志前缀（账号ID）

    Returns:
        滑动距离（像素），限制在 200~600
    """
    try:
        track_selectors = ["#nc_1__scale_text", ".nc-lang-cnt", "#nc_1_wrapper", ".nc_wrapper"]
        for selector in track_selectors:
            try:
                track_element = page.ele(selector, timeout=2)
                if track_element and track_element.rect and track_element.rect.width > 0:
                    track_width = track_element.rect.width
                    slide_ratio = random.uniform(0.70, 0.90)
                    final_distance = int(track_width * slide_ratio) + random.randint(-20, 20)
                    final_distance = max(200, min(600, final_distance))
                    logger.info(f"【{log_tag}】基于轨道宽度 {track_width}px 计算滑动距离: {final_distance}px")
                    return final_distance
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"【{log_tag}】轨道宽度计算失败: {e}")

    try:
        page_width = page.size[0] if hasattr(page, "size") else 1920
    except Exception:
        page_width = 1920
    if page_width <= 1366:
        return random.randint(250, 320)
    if page_width <= 1920:
        return random.randint(300, 400)
    return random.randint(350, 480)


def execute_tracks(page: Any, tracks: List[int], target_total_time: float, log_tag: str = "") -> None:
    """按轨迹逐步移动鼠标，叠加垂直抖动与 sin 节律速度波动。

    Args:
        page: DrissionPage 标签页对象
        tracks: 绝对位置轨迹列表
        target_total_time: 目标总耗时（秒）
        log_tag: 日志前缀（账号ID）
    """
    if not tracks:
        return

    start_time = time.time()
    slide_direction = random.choice([-1, 1])
    y_drift_trend = random.uniform(-3, 3)
    total = len(tracks)

    for i in range(total):
        progress = i / total
        offset_x = tracks[i] if i == 0 else tracks[i] - tracks[i - 1]
        if abs(offset_x) < 0.1:
            continue

        # 垂直偏移：趋势 + 抖动 + 方向
        trend_offset = y_drift_trend * (progress ** 0.7)
        shake_offset = random.uniform(-1.5, 1.5)
        if abs(offset_x) > 8:
            shake_offset *= random.uniform(1.2, 1.8)
        directional_offset = slide_direction * random.uniform(0.2, 1.0)
        offset_y = max(-8, min(8, trend_offset + shake_offset + directional_offset))

        # 基于剩余时间分配步长
        elapsed = time.time() - start_time
        remaining_time = max(target_total_time - elapsed, 0.1)
        remaining_steps = total - i
        base_time_per_step = remaining_time / remaining_steps if remaining_steps > 0 else 0.01
        distance_factor = max(abs(offset_x) / 15.0, 0.3)
        base_duration = base_time_per_step * distance_factor * 0.7

        # sin 节律 + 阶段速度
        rhythm_factor = 1 + 0.3 * math.sin(i * 0.5) * random.uniform(0.5, 1.5)
        if progress < 0.2:
            phase_multiplier = random.uniform(1.5, 2.5)
        elif progress < 0.7:
            phase_multiplier = random.uniform(0.3, 1.0)
        else:
            phase_multiplier = random.uniform(1.5, 3.0)
        final_duration = base_duration * phase_multiplier * rhythm_factor * random.uniform(0.7, 1.3)
        final_duration = max(0.005, min(0.15, final_duration))

        try:
            page.actions.move(
                offset_x=int(offset_x),
                offset_y=int(offset_y),
                duration=max(0.005, float(final_duration)),
            )
        except Exception as move_e:
            logger.warning(f"【{log_tag}】滑动步骤失败，跳过: {move_e}")
            continue

        step_delay = max(0.001, min(0.05, base_time_per_step * 0.3 * random.uniform(0.5, 1.5)))
        time.sleep(step_delay)
