"""
滑块验证历史记录管理器

管理成功记录的保存和加载，支持轨迹参数优化
复刻原始 utils/xianyu_slider_stealth.py 中的历史记录管理逻辑
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from loguru import logger


class HistoryManager:
    """滑块验证历史记录管理器"""

    def __init__(self, user_id: str = "default", enable_learning: bool = True):
        """
        初始化历史记录管理器
        
        Args:
            user_id: 用户ID
            enable_learning: 是否启用学习功能
        """
        self.user_id = user_id
        self.pure_user_id = self._extract_pure_user_id(user_id)
        self.enable_learning = enable_learning
        self.success_history_file = f"logs/trajectory_history/{self.pure_user_id}_success.json"

    def _extract_pure_user_id(self, user_id: str) -> str:
        """提取纯用户ID"""
        if '_' in user_id:
            parts = user_id.split('_')
            if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) >= 10:
                return '_'.join(parts[:-1])
        return user_id

    def load_success_history(self) -> List[Dict[str, Any]]:
        """加载历史成功数据"""
        try:
            if not os.path.exists(self.success_history_file):
                return []

            with open(self.success_history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                logger.info(f"【{self.pure_user_id}】加载历史成功数据: {len(history)}条记录")
                return history
        except Exception as e:
            logger.warning(f"【{self.pure_user_id}】加载历史数据失败: {e}")
            return []

    def save_success_record(self, trajectory_data: Dict[str, Any]):
        """保存成功记录
        
        Args:
            trajectory_data: 轨迹数据
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.success_history_file), exist_ok=True)

            # 加载现有历史
            history = self.load_success_history()

            # 添加新记录 - 只保存必要参数
            record = {
                "timestamp": time.time(),
                "user_id": self.pure_user_id,
                "distance": trajectory_data.get("distance", 0),
                "total_steps": trajectory_data.get("total_steps", 0),
                "base_delay": trajectory_data.get("base_delay", 0),
                "jitter_x_range": trajectory_data.get("jitter_x_range", [0, 0]),
                "jitter_y_range": trajectory_data.get("jitter_y_range", [0, 0]),
                "slow_factor": trajectory_data.get("slow_factor", 0),
                "acceleration_phase": trajectory_data.get("acceleration_phase", 0),
                "fast_phase": trajectory_data.get("fast_phase", 0),
                "slow_start_ratio": trajectory_data.get("slow_start_ratio", 0),
                "trajectory_point_count": len(trajectory_data.get("trajectory_points", [])),
                "final_left_px": trajectory_data.get("final_left_px", 0),
                "completion_used": trajectory_data.get("completion_used", False),
                "completion_steps": trajectory_data.get("completion_steps", 0),
                "success": True
            }

            history.append(record)

            # 只保留最近100条成功记录
            if len(history) > 100:
                history = history[-100:]

            # 保存到文件
            with open(self.success_history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            logger.info(
                f"【{self.pure_user_id}】保存成功记录: 距离{record['distance']}px, "
                f"步数{record['total_steps']}, 轨迹点{record['trajectory_point_count']}个"
            )

        except Exception as e:
            logger.error(f"【{self.pure_user_id}】保存成功记录失败: {e}")

    def optimize_trajectory_params(self) -> Dict[str, Any]:
        """基于历史成功数据优化轨迹参数
        
        Returns:
            优化后的轨迹参数
        """
        # 默认参数
        default_params = {
            "total_steps_range": [5, 8],
            "base_delay_range": [0.0002, 0.0005],
            "jitter_x_range": [0, 1],
            "jitter_y_range": [0, 1],
            "slow_factor_range": [10, 15],
            "acceleration_phase": 1.0,
            "fast_phase": 1.0,
            "slow_start_ratio_base": 2.0,
            "completion_usage_rate": 0.05,
            "avg_completion_steps": 1.0,
            "trajectory_length_stats": [],
            "learning_enabled": False
        }

        try:
            if not self.enable_learning:
                return default_params

            history = self.load_success_history()
            if len(history) < 3:  # 至少需要3条成功记录
                logger.info(f"【{self.pure_user_id}】历史成功数据不足({len(history)}条)，使用默认参数")
                return default_params

            # 计算成功记录的平均值
            total_steps_list = [record["total_steps"] for record in history]
            base_delay_list = [record["base_delay"] for record in history]
            slow_factor_list = [record["slow_factor"] for record in history]
            acceleration_phase_list = [record["acceleration_phase"] for record in history]
            fast_phase_list = [record["fast_phase"] for record in history]
            slow_start_ratio_list = [record["slow_start_ratio"] for record in history]

            # 计算补全使用率
            completion_used_count = sum(1 for record in history if record.get("completion_used", False))
            completion_usage_rate = completion_used_count / len(history)

            # 计算平均补全步数
            completion_steps_list = [
                record.get("completion_steps", 0) 
                for record in history 
                if record.get("completion_used", False)
            ]
            avg_completion_steps = sum(completion_steps_list) / len(completion_steps_list) if completion_steps_list else 0

            # 分析轨迹长度分布
            trajectory_lengths = [len(record.get("trajectory_points", [])) for record in history]
            trajectory_length_stats = []
            if trajectory_lengths:
                trajectory_length_stats = [
                    min(trajectory_lengths), 
                    max(trajectory_lengths), 
                    sum(trajectory_lengths) / len(trajectory_lengths)
                ]

            def safe_avg(values):
                return sum(values) / len(values) if values else 0

            def safe_std(values):
                if len(values) < 2:
                    return 0
                avg = safe_avg(values)
                variance = sum((x - avg) ** 2 for x in values) / len(values)
                return variance ** 0.5

            # 优化参数
            steps_min = max(110, int(safe_avg(total_steps_list) - safe_std(total_steps_list) * 0.8))
            steps_max = min(130, int(safe_avg(total_steps_list) + safe_std(total_steps_list) * 0.8))
            if steps_min >= steps_max:
                steps_min = 115
                steps_max = 125

            delay_min = max(0.020, safe_avg(base_delay_list) - safe_std(base_delay_list) * 0.6)
            delay_max = min(0.030, safe_avg(base_delay_list) + safe_std(base_delay_list) * 0.6)
            if delay_min >= delay_max:
                delay_min = 0.022
                delay_max = 0.027

            slow_min = max(5, int(safe_avg(slow_factor_list) - safe_std(slow_factor_list)))
            slow_max = min(20, int(safe_avg(slow_factor_list) + safe_std(slow_factor_list)))
            if slow_min >= slow_max:
                slow_min = 8
                slow_max = 15

            optimized_params = {
                "total_steps_range": [steps_min, steps_max],
                "base_delay_range": [delay_min, delay_max],
                "jitter_x_range": [-3, 12],
                "jitter_y_range": [-2, 12],
                "slow_factor_range": [slow_min, slow_max],
                "acceleration_phase": max(0.08, min(0.12, safe_avg(acceleration_phase_list))),
                "fast_phase": max(0.7, min(0.8, safe_avg(fast_phase_list))),
                "slow_start_ratio_base": max(0.98, min(1.02, safe_avg(slow_start_ratio_list))),
                "completion_usage_rate": completion_usage_rate,
                "avg_completion_steps": avg_completion_steps,
                "trajectory_length_stats": trajectory_length_stats,
                "learning_enabled": True
            }

            logger.info(
                f"【{self.pure_user_id}】基于{len(history)}条成功记录优化轨迹参数: "
                f"步数{optimized_params['total_steps_range']}, 延迟{optimized_params['base_delay_range']}"
            )

            return optimized_params

        except Exception as e:
            logger.error(f"【{self.pure_user_id}】优化轨迹参数失败: {e}")
            return default_params

    def analyze_failure(
        self, 
        attempt: int, 
        slide_distance: float, 
        trajectory_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析失败原因
        
        Args:
            attempt: 尝试次数
            slide_distance: 滑动距离
            trajectory_data: 轨迹数据
            
        Returns:
            失败分析信息
        """
        return {
            'attempt': attempt,
            'slide_distance': slide_distance,
            'total_steps': trajectory_data.get('total_steps', 0),
            'final_left_px': trajectory_data.get('final_left_px', 0),
            'timestamp': time.time()
        }

