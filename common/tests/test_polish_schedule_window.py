"""擦亮任务执行范围的回归测试。"""
from __future__ import annotations

from datetime import datetime
import unittest

from common.scheduled_task_time import is_within_daily_time_range, validate_daily_time_range


class PolishScheduleWindowTest(unittest.TestCase):
    def test_time_range_includes_start_and_end_minutes(self):
        self.assertTrue(is_within_daily_time_range(datetime(2026, 8, 27, 11, 0), "11:00", "23:59"))
        self.assertTrue(is_within_daily_time_range(datetime(2026, 8, 27, 23, 59, 59), "11:00", "23:59"))
        self.assertFalse(is_within_daily_time_range(datetime(2026, 8, 27, 10, 59, 59), "11:00", "23:59"))
        self.assertFalse(is_within_daily_time_range(datetime(2026, 8, 28, 0, 0), "11:00", "23:59"))

    def test_time_range_requires_valid_same_day_hhmm_values(self):
        self.assertEqual(validate_daily_time_range("00:00", "23:59"), ("00:00", "23:59"))
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            validate_daily_time_range("9:00", "23:59")
        with self.assertRaisesRegex(ValueError, "开始时间"):
            validate_daily_time_range("23:59", "11:00")


if __name__ == "__main__":
    unittest.main()
