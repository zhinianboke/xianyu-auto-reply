"""
重试策略成功率统计管理器

记录和分析不同滑块验证策略的成功率
复刻原始 utils/xianyu_slider_stealth.py 中 RetryStrategyStats 的逻辑
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

from loguru import logger


class RetryStrategyStats:
    """重试策略成功率统计管理器（单例模式）"""

    _instance: Optional["RetryStrategyStats"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.stats_lock = threading.Lock()
        self.strategy_stats: Dict[str, Dict[str, int]] = {
            'attempt_1_default': {'total': 0, 'success': 0, 'fail': 0},
            'attempt_2_cautious': {'total': 0, 'success': 0, 'fail': 0},
            'attempt_3_fast': {'total': 0, 'success': 0, 'fail': 0},
            'attempt_3_slow': {'total': 0, 'success': 0, 'fail': 0},
        }
        self.stats_file = 'logs/trajectory_history/strategy_stats.json'
        self._load_stats()
        self._initialized = True
        logger.info("策略统计管理器初始化完成")

    def _load_stats(self):
        """从文件加载统计数据"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    loaded_stats = json.load(f)
                    self.strategy_stats.update(loaded_stats)
                logger.info(f"已加载历史策略统计数据: {self.stats_file}")
        except Exception as e:
            logger.warning(f"加载策略统计数据失败: {e}")

    def _save_stats(self):
        """保存统计数据到文件"""
        try:
            os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.strategy_stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存策略统计数据失败: {e}")

    def record_attempt(self, attempt: int, strategy_type: str, success: bool):
        """记录一次尝试结果
        
        Args:
            attempt: 尝试次数 (1, 2, 3)
            strategy_type: 策略类型 ('default', 'cautious', 'fast', 'slow')
            success: 是否成功
        """
        with self.stats_lock:
            key = f'attempt_{attempt}_{strategy_type}'
            if key not in self.strategy_stats:
                self.strategy_stats[key] = {'total': 0, 'success': 0, 'fail': 0}

            self.strategy_stats[key]['total'] += 1
            if success:
                self.strategy_stats[key]['success'] += 1
            else:
                self.strategy_stats[key]['fail'] += 1

            # 每次记录后保存
            self._save_stats()

    def get_stats_summary(self) -> Dict[str, Dict[str, Any]]:
        """获取统计摘要"""
        with self.stats_lock:
            summary = {}
            for key, stats in self.strategy_stats.items():
                if stats['total'] > 0:
                    success_rate = (stats['success'] / stats['total']) * 100
                    summary[key] = {
                        'total': stats['total'],
                        'success': stats['success'],
                        'fail': stats['fail'],
                        'success_rate': f"{success_rate:.2f}%"
                    }
            return summary

    def log_summary(self):
        """输出统计摘要到日志"""
        summary = self.get_stats_summary()
        if summary:
            logger.info("=" * 60)
            logger.info("📊 重试策略成功率统计")
            logger.info("=" * 60)
            for key, stats in summary.items():
                logger.info(
                    f"{key:25s} | 总计:{stats['total']:4d} | "
                    f"成功:{stats['success']:4d} | 失败:{stats['fail']:4d} | "
                    f"成功率:{stats['success_rate']}"
                )
            logger.info("=" * 60)


# 全局策略统计实例
strategy_stats = RetryStrategyStats()

