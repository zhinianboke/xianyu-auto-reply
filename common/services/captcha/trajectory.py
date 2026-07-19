"""
滑块轨迹生成器

基于真人通过样本的时序分布生成滑动轨迹，用于驱动 Playwright 模拟鼠标
移动通过 NoCaptcha (NC) 滑块。

核心设计：
- 普通滑块越过轨道终点：参考真人模式优选样本的光标位移
- 20 个时间分位控制点：复刻真人模式优选样本的速度进度
- 目标内部时长 380~550ms：保持自然拖动，不追求快速完成
- 连续 Y 轴弧线：避免逐点独立随机抖动形成锯齿
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

        # 参数来自 human_trails 中真人通过样本的有效拖动段。Playwright 仍通过
        # CDP 派发事件，但轨迹密度、总时长和速度变化不再与真人样本明显冲突。
        self.trajectory_params = {
            # 真人模式业务优选样本按时间八等分后的 X 进度与 Y 偏移。
            "preferred_x_progress": [
                0.0258, 0.0698, 0.1344, 0.1757, 0.2326,
                0.2584, 0.3101, 0.3643, 0.4160, 0.4910,
                0.5504, 0.6486, 0.7623, 0.8372, 0.9302,
                0.9767, 0.9871, 0.9897, 0.9948, 1.0,
            ],
            "preferred_y_offsets": [
                2.0, 3.0, 5.0, 5.0, 7.0,
                8.0, 10.0, 11.0, 12.0, 14.0,
                16.0, 19.0, 19.0, 19.0, 15.0,
                13.0, 13.0, 13.0, 13.0, 13.0,
            ],
            "duration_range": [0.40, 0.48],
            "overshoot_ratio_range": [0.45, 0.55],
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
        """生成参考真人通过样本的 Playwright 滑动轨迹。

        关键设计：
        - 普通滑块的光标越过轨道终点 45%~55%，滑块本体由页面限制在终点
        - 使用 20 个时间分位控制点，复刻真人模式优选样本的速度进度
        - 总时长随距离变化，并限制在 380~550ms
        - 速度先升后降，末端自然收速并精确落点
        - Y 轴使用连续弧线，只叠加很小的相关扰动

        Args:
            distance: 目标滑动距离（像素）

        Returns:
            轨迹点列表 [(x_offset, y_offset, delay_seconds), ...]；
            普通滑块最后一点会越过 distance；小距离刮刮乐恰好等于 distance。
        """
        params = self.trajectory_params
        duration_min, duration_max = params["duration_range"]
        total_duration = random.uniform(duration_min, duration_max)
        # 真人模式业务优选样本在 258px 有效轨道上实际移动约 387px，光标
        # 会在滑块本体到达终点后继续越过框体。小距离通常是刮刮乐，不越界。
        cursor_distance = distance
        if distance >= 180.0:
            overshoot_min, overshoot_max = params["overshoot_ratio_range"]
            cursor_distance += distance * random.uniform(overshoot_min, overshoot_max)

        # 严格复刻真人模式优选样本的时间分位形态，并只加轻微扰动避免轨迹完全固定。
        progress_points = params["preferred_x_progress"]
        total_steps = len(progress_points)
        x_points: List[float] = []
        previous_progress = 0.0
        for index, base_progress in enumerate(progress_points):
            if index == total_steps - 1:
                progress = 1.0
            else:
                # 为后续控制点预留最小前进空间，避免末端多个点被固定上限
                # 压成相同 X 坐标，形成只纵向抖动的停滞段。
                min_progress_step = 0.002
                remaining_points = total_steps - index - 1
                max_progress = 1.0 - remaining_points * min_progress_step
                progress = max(
                    previous_progress + min_progress_step,
                    base_progress + random.uniform(-0.008, 0.008),
                )
                progress = min(progress, max_progress)
            previous_progress = progress
            x_points.append(cursor_distance * progress)

        y_scale = random.uniform(0.88, 1.12)
        y_points = [
            base_y * y_scale + random.uniform(-0.35, 0.35)
            for base_y in params["preferred_y_offsets"]
        ]
        delay_weights = [random.uniform(0.9, 1.1) for _ in range(total_steps)]
        delay_weight_total = sum(delay_weights)
        delays = [total_duration * weight / delay_weight_total for weight in delay_weights]

        trajectory = list(zip(x_points, y_points, delays))

        # 强制最后一步精确落在光标目标，避免浮点累积误差。
        if trajectory:
            last_x, last_y, last_d = trajectory[-1]
            trajectory[-1] = (cursor_distance, last_y, last_d)

        logger.info(
            f"【{self.pure_user_id}】真人样本化 Playwright 轨迹：{total_steps}点、"
            f"总时长≈{sum(delays) * 1000:.0f}ms、轨道{distance:.1f}px、"
            f"光标位移{cursor_distance:.1f}px"
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
                "cursor_distance": trajectory[-1][0],
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
