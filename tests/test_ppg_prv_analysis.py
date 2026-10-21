"""Small synthetic regression tests for task-bounded PPG-derived PRV."""
from io import BytesIO
import unittest

import numpy as np
import pandas as pd

from services.ppg_prv_service import (
    _bilateral_pairs,
    _segment_rows,
    perform_ppg_wave_hrv_analysis,
)
from services.ppg_service import load_ppg_wave_csv


def _wave_file(name, heart_rate_hz=1.2, duration_sec=60, include_acc=True):
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
        self.assertTrue(all(row["mean_ppi_ms"] is None for row in rows_a + rows_b))

    def test_full_minute_reports_prv_and_right_minus_left(self):
        left_name, left = _wave_file("MAX_L3_test.csv", 1.2)
        right_name, right = _wave_file("MAX_R3_test.csv", 1.5)
        result = perform_ppg_wave_hrv_analysis(
            {left_name: left, right_name: right}, False, 1
        )
        self.assertEqual(result["status"], "success", result.get("message"))
        left_row = next(row for row in result["data"] if row["filename"] == left_name and row["window_kind"] == "1分")
        right_row = next(row for row in result["data"] if row["filename"] == right_name and row["window_kind"] == "1分")
        self.assertGreater(left_row["valid_ppi_pct"], 90)
        self.assertIsNotNone(left_row["rmssd_ms"])
        self.assertIsNotNone(left_row["pppi50_pct"])
        self.assertIsNotNone(left_row["right_minus_left"])
        self.assertAlmostEqual(
            left_row["right_minus_left"]["mean_hr_bpm"],
            right_row["mean_hr_bpm"] - left_row["mean_hr_bpm"],
            places=6,
        )

    def test_short_residual_is_spectral_only(self):
        name, upload = _wave_file("short.csv", 1.2, duration_sec=30)
        result = perform_ppg_wave_hrv_analysis({name: upload}, False, 1)
        self.assertEqual(result["status"], "success", result.get("message"))
        row = result["data"][0]
        self.assertEqual(row["window_kind"], "短区間")
        self.assertIsNone(row["mean_ppi_ms"])
        self.assertIsNone(row["rmssd_ms"])
        self.assertIsNone(row["pppi50_pct"])
        self.assertIsNotNone(row["spectral_hr_bpm"])

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
