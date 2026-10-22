"""Small synthetic regression tests for task-bounded PPG-derived PRV."""
from io import BytesIO
import unittest

import numpy as np
import pandas as pd

from services.ppg_prv_service import (
    _bilateral_pairs,
    _segment_rows,
    _task_summary_rows,
    perform_ppg_wave_hrv_analysis,
)
from services.ppg_service import load_ppg_wave_csv


def _wave_file(name, heart_rate_hz=1.2, duration_sec=60, include_acc=True, hr_bpm=None):
    fs = 100
    time = np.arange(0, duration_sec, 1 / fs)
    start = pd.Timestamp("2026-10-14 12:00:00")
    data = {
        "RecvJST": (start + pd.to_timedelta(time, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f"),
        "IR_Value": np.sin(2 * np.pi * heart_rate_hz * time),
    }
    if include_acc:
        data.update({
            "Accel_X_mg": 20 * np.sin(2 * np.pi * 2.0 * time),
            "Accel_Y_mg": np.zeros(len(time)),
            "Accel_Z_mg": np.zeros(len(time)),
        })
    if hr_bpm is not None:
        data["HR_BPM"] = np.full(len(time), hr_bpm, dtype=float)
    frame = pd.DataFrame(data)
    return name, BytesIO(frame.to_csv(index=False).encode("utf-8"))


class PpgPrvWindowTests(unittest.TestCase):
    def test_sensor_elapsed_reconstructs_duplicate_receive_timestamps(self):
        csv_data = (
            "RecvJST,IR_Value,SensorElapsed_ms\n"
            "2026-10-14 12:00:00.000,100,5000\n"
            "2026-10-14 12:00:00.000,101,5010\n"
        ).encode("utf-8")
        result = load_ppg_wave_csv(BytesIO(csv_data))
        self.assertEqual(len(result), 2)
        self.assertEqual(
            (result["RecvJST"].iloc[1] - result["RecvJST"].iloc[0]).total_seconds(),
            0.01,
        )

    def test_task_windows_do_not_cross_task_boundaries(self):
        start = pd.Timestamp("2026-10-14 12:00:00")
        time = np.arange(0, 65, 0.01)
        frame = pd.DataFrame({
            "RecvJST": start + pd.to_timedelta(time, unit="s"),
            "IR_Value": np.sin(2 * np.pi * 1.2 * time),
        })
        rows_a = _segment_rows(frame, "A", start, start + pd.Timedelta(seconds=30), "a.csv", None)
        rows_b = _segment_rows(frame, "B", start + pd.Timedelta(seconds=30),
                               start + pd.Timedelta(seconds=65), "a.csv", None)
        self.assertTrue(all(pd.Timestamp(row["end_time"]) <= start + pd.Timedelta(seconds=30)
                            for row in rows_a))
        self.assertTrue(all(pd.Timestamp(row["start_time"]) >= start + pd.Timedelta(seconds=30)
                            for row in rows_b))
        complete = [row for row in rows_a + rows_b if row["window_kind"] == "30秒"]
        residual = [row for row in rows_a + rows_b if row["window_kind"] == "短区間"]
        self.assertTrue(complete)
        self.assertTrue(all(row["mean_ppi_ms"] is not None for row in complete))
        self.assertTrue(all(row["mean_ppi_ms"] is None for row in residual))

    def test_full_minute_reports_prv_and_right_minus_left(self):
        left_name, left = _wave_file("MAX_L3_test.csv", 1.2)
        right_name, right = _wave_file("MAX_R3_test.csv", 1.5)
        result = perform_ppg_wave_hrv_analysis(
            {left_name: left, right_name: right}, False, 1
        )
        self.assertEqual(result["status"], "success", result.get("message"))
        left_rows = [row for row in result["data"] if row["filename"] == left_name and row["window_kind"] == "30秒"]
        right_rows = [row for row in result["data"] if row["filename"] == right_name and row["window_kind"] == "30秒"]
        self.assertEqual(len(left_rows), 2)
        self.assertEqual(len(right_rows), 2)
        left_row, right_row = left_rows[0], right_rows[0]
        self.assertGreater(left_row["valid_ppi_pct"], 90)
        self.assertIsNotNone(left_row["rmssd_ms"])
        self.assertIsNotNone(left_row["sdnn_ms"])
        self.assertIsNotNone(left_row["pppi50_pct"])
        self.assertTrue(70 <= left_row["hr_bpm"] <= 75)
        self.assertIsNotNone(left_row["right_minus_left"])
        self.assertAlmostEqual(
            left_row["right_minus_left"]["mean_hr_bpm"],
            right_row["mean_hr_bpm"] - left_row["mean_hr_bpm"],
            places=6,
        )
        summary = next(row for row in result["task_summary"] if row["filename"] == left_name)
        self.assertEqual(summary["window_count"], 2)
        self.assertEqual(summary["included_window_count"], 2)
        self.assertAlmostEqual(summary["mean_hr_bpm"], 72.0, delta=3.0)

    def test_short_residual_shows_hr_but_not_prv_metrics(self):
        name, upload = _wave_file("short.csv", 1.2, duration_sec=20)
        result = perform_ppg_wave_hrv_analysis({name: upload}, False, 1)
        self.assertEqual(result["status"], "success", result.get("message"))
        row = result["data"][0]
        self.assertEqual(row["window_kind"], "短区間")
        self.assertIsNotNone(row["hr_bpm"])
        self.assertIsNone(row["mean_ppi_ms"])
        self.assertIsNone(row["rmssd_ms"])
        self.assertIsNone(row["sdnn_ms"])
        self.assertIsNone(row["pppi50_pct"])
        self.assertIsNotNone(row["spectral_hr_bpm"])

    def test_hr_named_csv_uses_precomputed_hr_bpm_column(self):
        name, upload = _wave_file("MAX_L_test_HR.csv", hr_bpm=83.5)
        result = perform_ppg_wave_hrv_analysis({name: upload}, False, 1)
        self.assertEqual(result["status"], "success", result.get("message"))
        rows = [item for item in result["data"] if item["window_kind"] == "30秒"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(abs(row["hr_bpm"] - 83.5) < 1e-6 for row in rows))

    def test_hr_named_csv_requires_hr_bpm_column(self):
        name, upload = _wave_file("MAX_R_missing_HR.csv")
        result = perform_ppg_wave_hrv_analysis({name: upload}, False, 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("HR_BPM", result["message"])

    def test_legacy_csv_estimates_hr_from_ir_even_if_hr_column_exists(self):
        name, upload = _wave_file("MAX_L_legacy.csv", heart_rate_hz=1.2, hr_bpm=83.5)
        result = perform_ppg_wave_hrv_analysis({name: upload}, False, 1)
        self.assertEqual(result["status"], "success", result.get("message"))
        row = next(item for item in result["data"] if item["window_kind"] == "30秒")
        self.assertAlmostEqual(row["hr_bpm"], 72.0, delta=3.0)

    def test_task_summary_averages_only_accepted_complete_windows(self):
        base = {
            "filename": "MAX_L_test_HR.csv",
            "task": "作業",
            "task_start_time": "2026-10-14T12:00:00",
            "task_end_time": "2026-10-14T12:02:00",
            "window_kind": "30秒",
        }
        rows = [
            {**base, "quality_status": "採用", "hr_bpm": 70.0, "rmssd_ms": 10.0,
             "sdnn_ms": 20.0, "pppi50_pct": 5.0},
            {**base, "quality_status": "注意付き採用", "hr_bpm": 80.0, "rmssd_ms": 30.0,
             "sdnn_ms": 40.0, "pppi50_pct": 15.0},
            {**base, "quality_status": "除外", "hr_bpm": 100.0, "rmssd_ms": 50.0,
             "sdnn_ms": 60.0, "pppi50_pct": 25.0},
            {**base, "window_kind": "短区間", "quality_status": "短区間", "hr_bpm": 90.0,
             "rmssd_ms": None, "sdnn_ms": None, "pppi50_pct": None},
        ]
        summary = _task_summary_rows(rows)[0]
        self.assertEqual(summary["window_count"], 3)
        self.assertEqual(summary["included_window_count"], 2)
        self.assertEqual(summary["excluded_window_count"], 1)
        self.assertEqual(summary["hr_bpm_count"], 2)
        self.assertAlmostEqual(summary["mean_hr_bpm"], 75.0)
        self.assertAlmostEqual(summary["mean_rmssd_ms"], 20.0)

    def test_accelerometer_columns_remain_optional(self):
        name, upload = _wave_file("legacy_ppg_only.csv", include_acc=False)
        result = perform_ppg_wave_hrv_analysis({name: upload}, False, 1)
        self.assertEqual(result["status"], "success", result.get("message"))
        row = result["data"][0]
        self.assertIsNone(row["accel_rms_g"])
        self.assertIsNone(row["ppg_acc_overlap_pct"])

    def test_bilateral_filename_matching_supports_numbered_sides(self):
        self.assertEqual(
            _bilateral_pairs(["MAX_L3_test.csv", "MAX_R3_test.csv"]),
            [("MAX_L3_test.csv", "MAX_R3_test.csv")],
        )


if __name__ == "__main__":
    unittest.main()
