"""Portable regression tests for shared parsing and comparison behavior.

The real experimental CSV files are intentionally kept outside the repository.
These small in-memory cases protect the core input and metric contracts without
copying participant data into source control.
"""

from io import BytesIO
import unittest

import pandas as pd

from services.common import (
    parse_datetime_or_duration,
    parse_datetime_series,
    read_uploaded_csv,
    read_uploaded_csv_columns,
    resolve_log_file,
)
from services.hr_compare_service import evaluate_hr_pair
from services.ppg_service import (
    load_ppg_hr_csv,
    load_ppg_raw_csv,
)


class UploadedCsvReadTests(unittest.TestCase):
    def test_csv_reader_restores_stream_after_success(self):
        stream = BytesIO(b"time,value\n2026-10-14,12\n")

        result = read_uploaded_csv(stream, usecols=["value"])

        self.assertEqual(result["value"].tolist(), [12])
        self.assertEqual(stream.tell(), 0)

    def test_csv_reader_restores_stream_after_parse_error(self):
        stream = BytesIO(b"")

        with self.assertRaises(pd.errors.EmptyDataError):
            read_uploaded_csv(stream)

        self.assertEqual(stream.tell(), 0)

    def test_header_reader_returns_columns_and_restores_stream(self):
        stream = BytesIO(b"RecvJST,HR_BPM\n")

        columns = read_uploaded_csv_columns(stream)

        self.assertEqual(columns, {"RecvJST", "HR_BPM"})
        self.assertEqual(stream.tell(), 0)


class DateParsingTests(unittest.TestCase):
    def test_excel_formula_wrapped_datetime_is_parsed(self):
        values = parse_datetime_series(
            pd.Series(['="2026-10-14 12:00:00.000"'])
        )

        self.assertEqual(values.iloc[0], pd.Timestamp("2026-10-14 12:00:00"))

    def test_excel_serial_datetime_uses_excel_epoch(self):
        parsed = parse_datetime_or_duration("46200.5")

        self.assertEqual(parsed, pd.Timestamp("1899-12-30") + pd.Timedelta(days=46200.5))


class UploadedFileResolutionTests(unittest.TestCase):
    def test_single_log_file_is_resolved(self):
        uploaded_files = {"subject_activity_log.csv": BytesIO(b"")}

        self.assertEqual(resolve_log_file(uploaded_files), "subject_activity_log.csv")

    def test_multiple_log_files_are_rejected(self):
        uploaded_files = {
            "first_log.csv": BytesIO(b""),
            "second_log.csv": BytesIO(b""),
        }

        with self.assertRaisesRegex(ValueError, "ログファイルが複数"):
            resolve_log_file(uploaded_files)


class PpgCsvLoaderTests(unittest.TestCase):
    def test_hr_loader_sorts_deduplicates_and_resets_stream(self):
        csv_data = (
            "RecvJST,HR_BPM\n"
            '="2026-10-14 12:00:02.000",72\n'
            '="2026-10-14 12:00:01.000",70\n'
            '="2026-10-14 12:00:01.000",71\n'
            "not-a-time,80\n"
        ).encode("utf-8")
        uploaded_file = BytesIO(csv_data)

        result = load_ppg_hr_csv(uploaded_file)

        self.assertEqual(uploaded_file.tell(), 0)
        self.assertEqual(result.index.tolist(), [
            pd.Timestamp("2026-10-14 12:00:01"),
            pd.Timestamp("2026-10-14 12:00:02"),
        ])
        self.assertEqual(result["HR"].tolist(), [70, 72])

    def test_raw_loader_rebuilds_time_from_sensor_elapsed(self):
        csv_data = (
            "RecvJST,IR_Value,RED_Value,Accel_X_mg,Accel_Y_mg,Accel_Z_mg,SensorElapsed_ms\n"
            "2026-10-14 12:00:00.000,100,200,1,2,3,500\n"
            "2026-10-14 12:00:00.100,101,201,1,2,3,600\n"
            "2026-10-14 12:00:00.200,102,202,1,2,3,invalid\n"
            "2026-10-14 12:00:00.300,103,203,1,2,3,800\n"
        ).encode("utf-8")

        result = load_ppg_raw_csv(BytesIO(csv_data))

        self.assertEqual(result["IR_Value"].tolist(), [100, 101, 103])
        self.assertEqual(result["RecvJST"].tolist(), [
            pd.Timestamp("2026-10-14 12:00:00.000"),
            pd.Timestamp("2026-10-14 12:00:00.100"),
            pd.Timestamp("2026-10-14 12:00:00.300"),
        ])


class HeartRateComparisonTests(unittest.TestCase):
    def test_pair_metrics_interpolate_reference_to_device_timestamps(self):
        start = pd.Timestamp("2026-10-14 12:00:00")
        true = pd.DataFrame(
            {"HR": [60.0, 64.0, 68.0]},
            index=pd.DatetimeIndex([
                start,
                start + pd.Timedelta(seconds=2),
                start + pd.Timedelta(seconds=4),
            ]),
        )
        device = pd.DataFrame(
            {"HR": [62.0, 64.0, 66.0, 68.0, 70.0]},
            index=pd.date_range(start, periods=5, freq="1s"),
        )

        result = evaluate_hr_pair(true, device, start, start + pd.Timedelta(seconds=4))

        self.assertIsNone(result["error"])
        self.assertEqual(result["raw_count"], 5)
        self.assertAlmostEqual(result["raw_mae"], 2.0)
        self.assertAlmostEqual(result["raw_rmse"], 2.0)
        self.assertEqual(result["resampled_count"], 1)
        self.assertAlmostEqual(result["resampled_mae"], 2.0)
        self.assertAlmostEqual(result["resampled_rmse"], 2.0)


if __name__ == "__main__":
    unittest.main()
