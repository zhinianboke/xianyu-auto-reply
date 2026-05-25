"""
滑块轨迹生成器

基于物理加速度模型生成"人类化三阶段"的滑动轨迹，用于驱动 Playwright
模拟鼠标移动通过 NoCaptcha (NC) 滑块。

核心设计：
- 不超调：精确停在目标距离，避免 NC 风控因超调升级为 x5step=2 二阶段验证
- 三阶段速度曲线：加速 → 匀速 → 减速，符合人类肌肉记忆
- 步间延迟 10~20ms：避免极快轨迹被识别为机器人
- Y 轴轻抖：±1px，模拟手部小幅抖动
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple

from loguru import logger


class TrajectoryGenerator:
    """滑块轨迹生成器"""

    def __init__(self, user_id: str = "default"):
        """
        初始化轨迹生成器

        Args:
            user_id: 用户ID，用于日志标识
        """
        self.user_id = user_id
        self.pure_user_id = self._extract_pure_user_id(user_id)

        # 人类化轨迹参数 —— 基于实测数据优化
        #
        # 关键发现：
        # 1. 成功轨迹内部时间 avg=16.3ms (7.5-28ms)，
        #    失败轨迹 avg=9.2ms (1.0-20.8ms)，极快轨迹(<5ms)几乎必败。
        # 2. 7步轨迹失败率极高，6步轨迹成功率更高。
        # 3. total_duration_range 下限为0时，random.uniform(0, 0.015) 有时
        #    生成接近0的值，导致步间延迟 ~0.0001s，像机器人。
        #
        # CDP RTT ~80-150ms/步，6步 ≈ 480-900ms，加上内部 sleep ≈ 500-920ms
        self.trajectory_params = {
            # 总步数 5~6；7步失败率过高，排除
            "total_steps_range": [5, 6],
            # 内部 sleep 10~20ms，确保不像机器人
            "total_duration_range": [0.010, 0.020],
            # 阶段比例：加速 35% / 匀速 35% / 减速 30%
            "accel_ratio": 0.35,
            "const_ratio": 0.35,
            "decel_ratio": 0.30,
            # Y 轴抖动范围（px）：缩小到 ±1.0，减少抖动
            "jitter_y_range": [-1.0, 1.0],
            # 匀速阶段偶发微停顿概率：降低到 3%
            "micro_pause_prob": 0.03,
            "micro_pause_factor_range": [1.1, 1.3],
        }

        # 保存最近一次轨迹的元数据，供失败分析使用
        self.current_trajectory_data: Dict[str, Any] = {}

    def _extract_pure_user_id(self, user_id: str) -> str:
        """提取纯用户ID（移除时间戳部分）"""
        if '_' in user_id:
            parts = user_id.split('_')
            if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) >= 10:
                return '_'.join(parts[:-1])
        return user_id

    def _bezier_curve(self, p0: float, p1: float, p2: float, p3: float, t: float) -> float:
        """三次贝塞尔曲线插值，作为扩展能力保留。"""
        return (
            (1 - t) ** 3 * p0
            + 3 * (1 - t) ** 2 * t * p1
            + 3 * (1 - t) * t ** 2 * p2
            + t ** 3 * p3
        )

    def _easing_function(self, t: float, mode: str = 'easeOutQuad') -> float:
        """常见缓动函数，便于将来替换轨迹策略时使用。"""
        if mode == 'easeOutQuad':
            return t * (2 - t)
        elif mode == 'easeInOutCubic':
            return 4 * t ** 3 if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2
        elif mode == 'easeOutBack':
            c1 = 1.70158
            c3 = c1 + 1
            return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)
        else:
            return t

    def generate_physics_trajectory(self, distance: float) -> List[Tuple[float, float, float]]:
        """生成人类化滑动轨迹（不超调、三阶段缓动）

        关键设计：
        - 不超调：精确停在 distance，避免 NC 风控因超调升级为 x5step=2 二阶段验证
        - 三阶段速度曲线：加速 35% / 匀速 35% / 减速 30%
        - 步间延迟 10~20ms：低于此区间像机器人，高于此区间像故意慢动作
        - Y 轴轻抖：±1px，模拟手部小幅抖动
        - 匀速阶段偶发微停顿：约 3% 概率延迟翻 1.1~1.3 倍

        Args:
            distance: 目标滑动距离（像素）

        Returns:
            轨迹点列表 [(x_offset, y_offset, delay_seconds), ...]；
            最后一个点的 x_offset 恰好等于 distance。
        """
        params = self.trajectory_params
        steps_min, steps_max = params["total_steps_range"]
        dur_min, dur_max = params["total_duration_range"]
        accel_ratio = params["accel_ratio"]
        const_ratio = params["const_ratio"]
        decel_ratio = params["decel_ratio"]
        jitter_min, jitter_max = params["jitter_y_range"]
        micro_pause_prob = params["micro_pause_prob"]
        pause_factor_min, pause_factor_max = params["micro_pause_factor_range"]

        total_steps = random.randint(steps_min, steps_max)
        total_duration = random.uniform(dur_min, dur_max)
        # 平均单步延迟
        avg_delay = total_duration / total_steps

        # 三阶段步数：先确保每段至少 2 步，加入随机波动
        accel_ratio_var = accel_ratio + random.uniform(-0.05, 0.05)
        decel_ratio_var = decel_ratio + random.uniform(-0.05, 0.05)
        accel_steps = max(2, int(round(total_steps * accel_ratio_var)))
        decel_steps = max(2, int(round(total_steps * decel_ratio_var)))
        const_steps = max(2, total_steps - accel_steps - decel_steps)
        # 实际总步数（可能因 max(2,…) 微调）
        total_steps = accel_steps + const_steps + decel_steps

        # 三阶段距离分配：加入随机波动
        accel_pct = 0.30 + random.uniform(-0.05, 0.05)
        const_pct = 0.55 + random.uniform(-0.05, 0.05)
        accel_dist = distance * accel_pct
        const_dist = distance * const_pct
        decel_dist = distance - accel_dist - const_dist

        trajectory: List[Tuple[float, float, float]] = []

        # 阶段 1：加速 —— 二次曲线 t^2，起步轻、越来越快
        for i in range(1, accel_steps + 1):
            t = i / accel_steps
            x = accel_dist * (t * t)
            y = random.uniform(jitter_min, jitter_max)
            # 起步段单步延迟略高（人类反应时间），逐步降低
            delay = avg_delay * random.uniform(1.0, 1.3)
            trajectory.append((x, y, delay))

        # 阶段 2：匀速 —— 线性 + 偶发微停顿
        const_base_x = accel_dist
        for i in range(1, const_steps + 1):
            t = i / const_steps
            x = const_base_x + const_dist * t
            y = random.uniform(jitter_min, jitter_max) * 0.6
            delay = avg_delay * random.uniform(0.85, 1.15)
            if random.random() < micro_pause_prob:
                delay *= random.uniform(pause_factor_min, pause_factor_max)
            trajectory.append((x, y, delay))

        # 阶段 3：减速 —— 反二次曲线 1-(1-t)^2，越来越慢、精确停在 distance
        decel_base_x = accel_dist + const_dist
        for i in range(1, decel_steps + 1):
            t = i / decel_steps
            x = decel_base_x + decel_dist * (1 - (1 - t) ** 2)
            y = random.uniform(jitter_min, jitter_max) * 0.4
            # 减速段单步延迟最长，模拟"接近目标时放慢"
            delay = avg_delay * random.uniform(1.1, 1.5)
            trajectory.append((x, y, delay))

        # 强制最后一步精确落在 distance，避免浮点累积误差
        if trajectory:
            last_x, last_y, last_d = trajectory[-1]
            trajectory[-1] = (distance, last_y, last_d)

        logger.info(
            f"【{self.pure_user_id}】🧍 人类化轨迹：{total_steps}步 "
            f"(加速{accel_steps}/匀速{const_steps}/减速{decel_steps})、"
            f"总时长≈{total_duration * 1000:.0f}ms、距离{distance:.1f}px（无超调）"
        )
        return trajectory

    def generate_human_trajectory(self, distance: float) -> List[Tuple[float, float, float]]:
        """对外暴露的统一入口，使用人类化三阶段轨迹。

        Args:
            distance: 滑动距离（像素）

        Returns:
            轨迹点列表
        """
        try:
            trajectory = self.generate_physics_trajectory(distance)

            self.current_trajectory_data = {
                "distance": distance,
                "model": "human_three_phase",
                "total_steps": len(trajectory),
                "trajectory_points": trajectory.copy(),
                "final_left_px": 0,
                "completion_used": False,
                "completion_steps": 0,
            }
            return trajectory
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】生成轨迹时出错: {e}")
            return []

    def generate_standard_trajectory(self, distance: int) -> List[Dict[str, Any]]:
        """生成标准三阶段（加速-匀速-减速）人类轨迹，作为可选备用策略保留。

        Args:
            distance: 滑动距离（像素）

        Returns:
            列表，每个元素为 {x, y, duration}
        """
        trajectory: List[Dict[str, Any]] = []
        current = 0.0

        # 各阶段距离划分
        acceleration_distance = distance * random.uniform(0.3, 0.5)
        constant_distance = distance * random.uniform(0.3, 0.4)

        # 加速阶段
        while current < acceleration_distance:
            move = min(random.uniform(8, 15), acceleration_distance - current)
            current += move
            trajectory.append({
                "x": move,
                "y": random.uniform(-2, 2),
                "duration": random.uniform(0.01, 0.02),
            })

        # 匀速阶段
        while current < acceleration_distance + constant_distance:
            move = min(random.uniform(10, 20), acceleration_distance + constant_distance - current)
            current += move
            trajectory.append({
                "x": move,
                "y": random.uniform(-1, 1),
                "duration": random.uniform(0.008, 0.015),
            })

        # 减速阶段
        while current < distance:
            move = min(random.uniform(2, 8), distance - current)
            current += move
            trajectory.append({
                "x": move,
                "y": random.uniform(-1, 1),
                "duration": random.uniform(0.02, 0.04),
            })

        return trajectory

    def get_trajectory_data(self) -> Dict[str, Any]:
        """获取最近一次轨迹的快照（浅拷贝）。"""
        return self.current_trajectory_data.copy()

    def update_trajectory_data(self, key: str, value: Any) -> None:
        """允许外层在滑动过程中回写关键状态（如最终落点 final_left_px）。"""
        self.current_trajectory_data[key] = value
