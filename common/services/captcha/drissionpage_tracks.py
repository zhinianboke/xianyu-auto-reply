"""
DrissionPage 滑块轨迹生成（纯函数）

本文件提供 DrissionPage 兜底引擎使用的拟人化滑动轨迹生成逻辑，
与具体浏览器无关，方便独立测试与复用。

移植自参照项目 utils/refresh_util.py 的 get_tracks / ease_out_expo，
保留 sin 节律波动、犹豫修正、超调回调等拟人化特征。
"""
from __future__ import annotations

import random
from typing import List, Optional


def ease_out_expo(t: float) -> float:
    """缓动函数，使滑动轨迹更自然。

    Args:
        t: 进度（0~1）

    Returns:
        缓动后的进度值
    """
    return 1 - pow(2, -10 * t) if t != 1 else 1


def generate_tracks(distance: float, target_points: Optional[int] = None) -> List[int]:
    """生成拟人化的滑动轨迹（绝对位置列表）。

    模拟人类滑动的三阶段（加速 / 匀速 / 减速），叠加手部微颤、犹豫修正、
    超调回调与最终细微调整，并按目标点数进行采样。

    Args:
        distance: 目标滑动距离（像素）
        target_points: 目标轨迹点数，None 时自动控制

    Returns:
        绝对位置轨迹列表（整数像素）
    """
    tracks: List[float] = []
    current = 0.0
    velocity = 0.0

    # 人类滑动特征参数
    max_velocity = random.uniform(80, 150)
    acceleration_phase = distance * random.uniform(0.3, 0.6)
    deceleration_start = distance * random.uniform(0.6, 0.85)

    # 根据目标点数动态调整时间步长
    if target_points:
        base_dt = distance / (target_points * max_velocity * 0.5)
        dt = base_dt * random.uniform(0.8, 1.2)
        dt = max(0.01, min(0.2, dt))
    else:
        dt = random.uniform(0.02, 0.12)

    hesitation_probability = 0.15
    overshoot_chance = 0.3

    tracks.append(0.0)
    step = 0
    hesitation_counter = 0

    while current < distance:
        step += 1

        # 三阶段加速度模型
        if current < acceleration_phase:
            target_accel = random.uniform(15, 35)
            if step % random.randint(3, 8) == 0:
                target_accel *= random.uniform(0.7, 1.4)
        elif current < deceleration_start:
            target_accel = random.uniform(-2, 2)
            if random.random() < 0.2:
                target_accel = random.uniform(-8, 8)
        else:
            remaining_distance = distance - current
            if remaining_distance > 20:
                target_accel = random.uniform(-25, -8)
            else:
                target_accel = random.uniform(-15, -3)

        # 犹豫与调整
        if random.random() < hesitation_probability and current > acceleration_phase:
            hesitation_counter += 1
            if hesitation_counter < 3:
                if random.random() < 0.4:
                    target_accel = random.uniform(-8, -2)
                else:
                    target_accel = random.uniform(-2, 2)
            else:
                hesitation_counter = 0

        # 更新速度（带阻尼）与位置
        velocity = velocity * 0.95 + target_accel * dt
        velocity = max(0.0, min(velocity, max_velocity))

        old_current = current
        current += velocity * dt

        # 手部微颤
        if len(tracks) > 5:
            tremor = random.uniform(-0.3, 0.3) * (velocity / max_velocity)
            current += tremor

        # 人类修正行为
        if random.random() < 0.12 and current > 50:
            correction_type = random.random()
            if correction_type < 0.6:
                current -= random.uniform(1.0, 4.0)
            elif correction_type < 0.8:
                pass
            else:
                current += random.uniform(0.2, 1.0)

        # 防止负向移动与过大跳跃
        if current < old_current:
            current = old_current + random.uniform(0.1, 0.8)
        if current - old_current > 15:
            current = old_current + random.uniform(8, 15)

        tracks.append(round(current, 1))

    # 超调回调
    if random.random() < overshoot_chance:
        overshoot = random.uniform(2, 8)
        tracks.append(round(distance + overshoot, 1))
        correction_steps = random.randint(2, 5)
        for i in range(correction_steps):
            correction = overshoot * (1 - (i + 1) / correction_steps)
            noise = random.uniform(-0.3, 0.3)
            tracks.append(round(distance + correction + noise, 1))

    # 最终细微调整
    final_adjustments = random.randint(1, 3)
    target_final = distance + random.uniform(-1, 2)
    for _ in range(final_adjustments):
        target_final += random.uniform(-0.5, 0.5)
        tracks.append(round(target_final, 1))

    cleaned = _clean_tracks(tracks)
    cleaned = _resample_tracks(cleaned, target_points)
    return [int(x) for x in cleaned]


def _clean_tracks(tracks: List[float]) -> List[float]:
    """清理冗余点并修正大幅回退。"""
    cleaned = [tracks[0]]
    last_pos = tracks[0]
    for i in range(1, len(tracks)):
        current_pos = tracks[i]
        if abs(current_pos - last_pos) < 1.5:
            continue
        if current_pos >= last_pos or (last_pos - current_pos) < 3:
            cleaned.append(current_pos)
            last_pos = current_pos
        else:
            corrected_pos = last_pos + random.uniform(0.1, 1.0)
            cleaned.append(corrected_pos)
            last_pos = corrected_pos
    return cleaned


def _resample_tracks(cleaned: List[float], target_points: Optional[int]) -> List[float]:
    """根据目标点数对轨迹进行采样/插值。"""
    if target_points and len(cleaned) != target_points and len(cleaned) > 1:
        if len(cleaned) > target_points:
            # 下采样
            step = len(cleaned) / target_points
            optimized = [cleaned[0]]
            for i in range(1, target_points - 1):
                idx = min(int(i * step), len(cleaned) - 1)
                optimized.append(cleaned[idx])
            optimized.append(cleaned[-1])
            return optimized
        # 上采样（插值）
        while len(cleaned) < target_points and len(cleaned) > 1:
            new_tracks = [cleaned[0]]
            for i in range(len(cleaned) - 1):
                new_tracks.append(cleaned[i])
                if len(new_tracks) < target_points:
                    mid_point = (cleaned[i] + cleaned[i + 1]) / 2 + random.uniform(-0.5, 0.5)
                    new_tracks.append(mid_point)
            new_tracks.append(cleaned[-1])
            cleaned = new_tracks
            if len(cleaned) >= target_points:
                cleaned = cleaned[:target_points]
                break
        return cleaned
    if not target_points and len(cleaned) > 200:
        step = max(1, len(cleaned) // 150)
        optimized = [cleaned[i] for i in range(0, len(cleaned), step)]
        if optimized[-1] != cleaned[-1]:
            optimized.append(cleaned[-1])
        return optimized
    return cleaned
