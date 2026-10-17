"""時刻解釈とログ区間作成の境界条件を検証する．"""
from io import BytesIO
import unittest

import pandas as pd

from services.common import config as common_config
from services.common import load_log_tasks, load_preview_log_range
from services.settings import config as shared_config


class LogTaskBoundaryTests(unittest.TestCase):
    def _log(self, rows):
        text = "Task_Name,Timestamp\n" + "\n".join(
            f"{name},{timestamp}" for name, timestamp in rows
        ) + "\n"
        return {"activity_log.csv": BytesIO(text.encode("utf-8"))}

    def test_log_tasks_sort_rows_and_pair_each_boundary_with_the_next(self):
        files = self._log([
            ("朗読", "2026-10-14 12:10:00"),
            ("Start", "2026-10-14 12:00:00"),
            ("回復", "2026-10-14 12:20:00"),
        ])

        tasks = load_log_tasks(
            files, True, 5, None, None, pd.Timestamp("2026-10-14")
        )

        self.assertEqual([task["Task_Name"] for task in tasks], ["Start", "朗読"])
        self.assertEqual(tasks[0]["Start_Time"], pd.Timestamp("2026-10-14 12:00:00"))
        self.assertEqual(tasks[0]["End_Time"], pd.Timestamp("2026-10-14 12:10:00"))
        self.assertEqual(tasks[1]["Start_Time"], pd.Timestamp("2026-10-14 12:10:00"))
        self.assertEqual(tasks[1]["End_Time"], pd.Timestamp("2026-10-14 12:20:00"))

    def test_log_with_fewer_than_two_boundaries_is_rejected(self):
        files = self._log([("Start", "2026-10-14 12:00:00")])

        with self.assertRaisesRegex(ValueError, "タスク境界が 2 つ未満"):
            load_log_tasks(
                files, True, 5, None, None, pd.Timestamp("2026-10-14")
            )

    def test_duplicate_log_timestamps_are_rejected_for_analysis(self):
        files = self._log([
            ("Start", "2026-10-14 12:00:00"),
            ("Task", "2026-10-14 12:00:00"),
        ])

        with self.assertRaisesRegex(ValueError, "同じ時刻の記録"):
            load_log_tasks(
                files, True, 5, None, None, pd.Timestamp("2026-10-14")
            )

    def test_unparseable_log_timestamp_is_reported(self):
        files = self._log([
            ("Start", "2026-10-14 12:00:00"),
            ("Task", "not-a-time"),
        ])

        with self.assertRaisesRegex(ValueError, "未知の時刻書式"):
            load_log_tasks(
                files, True, 5, None, None, pd.Timestamp("2026-10-14")
            )

    def test_no_log_interval_split_keeps_a_short_final_interval(self):
        start = pd.Timestamp("2026-10-14 12:00:00")
        tasks = load_log_tasks(
            {}, False, 5, start, start + pd.Timedelta(minutes=12), None
        )

        self.assertEqual([task["Task_Name"] for task in tasks], ["区間1", "区間2", "区間3"])
        self.assertEqual(
            [(task["End_Time"] - task["Start_Time"]).total_seconds() for task in tasks],
            [300, 300, 120],
        )


class PreviewLogRangeBoundaryTests(unittest.TestCase):
    def _log(self, rows):
        text = "Task_Name,Timestamp\n" + "\n".join(
            f"{name},{timestamp}" for name, timestamp in rows
        ) + "\n"
        return {"activity_log.csv": BytesIO(text.encode("utf-8"))}

    def test_preview_uses_start_to_end_and_anchors_time_only_rows(self):
        base_day = pd.Timestamp("2026-10-14")
        files = self._log([
            ("Before", "08:59:00"),
            ("Start", "09:00:00"),
            ("作業", "09:05:00"),
            ("End", "09:10:00"),
            ("After", "09:15:00"),
        ])

        result = load_preview_log_range(files, base_day=base_day)

        self.assertEqual(result["start"], base_day + pd.Timedelta(hours=9))
        self.assertEqual(result["end"], base_day + pd.Timedelta(hours=9, minutes=10))
        self.assertEqual([task["name"] for task in result["tasks"]], ["Start", "作業"])
        self.assertEqual(
            [task["start"] for task in result["tasks"]],
            ["2026-10-14T09:00:00", "2026-10-14T09:05:00"],
        )

    def test_preview_ignores_invalid_timestamp_rows_between_valid_boundaries(self):
        files = self._log([
            ("Start", "2026-10-14 09:00:00"),
            ("invalid row", "not-a-time"),
            ("End", "2026-10-14 09:10:00"),
        ])

        result = load_preview_log_range(files)

        self.assertEqual([task["name"] for task in result["tasks"]], ["Start"])
        self.assertEqual(len(result["axis_ticks"]), 2)

    def test_preview_rejects_duplicate_valid_timestamps(self):
        files = self._log([
            ("Start", "2026-10-14 09:00:00"),
            ("作業", "2026-10-14 09:00:00"),
            ("End", "2026-10-14 09:10:00"),
        ])

        with self.assertRaisesRegex(ValueError, "同じ時刻の記録"):
            load_preview_log_range(files)

    def test_preview_requires_an_end_after_start(self):
        files = self._log([
            ("Start", "2026-10-14 09:00:00"),
            ("作業", "2026-10-14 09:05:00"),
        ])

        with self.assertRaisesRegex(ValueError, "Startより後のEnd"):
            load_preview_log_range(files)


class SharedSettingsTests(unittest.TestCase):
    def test_common_uses_the_single_shared_config_object(self):
        self.assertIs(common_config, shared_config)


if __name__ == "__main__":
    unittest.main()
