"""Regression coverage for public Goofish detail-header engagement metrics."""

from __future__ import annotations

import unittest

from app.services.compass.goofish_compass import GoofishCompassService


class DetailHeaderMetricTests(unittest.TestCase):
    def test_prefers_current_detail_summary_pair(self) -> None:
        metrics = GoofishCompassService._extract_detail_header_metrics([
            "¥12.90 原价¥12.90 包邮 121人想要 1150浏览",
            "525人想要",
            "14人想要",
        ])

        self.assertEqual(metrics["want_count"], 121)
        self.assertEqual(metrics["view_count"], 1150)
        self.assertEqual(
            metrics["metric_sources"],
            {
                "want_count": "dom.visible_detail_summary_pair",
                "view_count": "dom.visible_detail_summary_pair",
            },
        )

    def test_supports_summary_pair_with_wan_unit(self) -> None:
        metrics = GoofishCompassService._extract_detail_header_metrics([
            "1.2万人想要 3.4万浏览",
        ])

        self.assertEqual(metrics["want_count"], 12000)
        self.assertEqual(metrics["view_count"], 34000)

    def test_keeps_absent_wanted_metric_missing(self) -> None:
        metrics = GoofishCompassService._extract_detail_header_metrics([
            "25浏览",
        ])

        self.assertNotIn("want_count", metrics)
        self.assertEqual(metrics["view_count"], 25)
        self.assertEqual(
            metrics["metric_capture_status"]["want_count"],
            "not_displayed_in_detail_header",
        )


if __name__ == "__main__":
    unittest.main()
