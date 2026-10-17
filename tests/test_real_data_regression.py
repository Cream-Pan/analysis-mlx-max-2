"""実測 CSV を使う，任意実行のローカル回帰テスト．"""
from io import BytesIO, StringIO
from pathlib import Path
import unittest
import unicodedata
from zipfile import ZipFile

import pandas as pd

from services.mlx_service import process_mlx_common
from services.ppg_acc_service import perform_ppg_acc_analysis
from services.ppg_service import process_ppg_to_hr, perform_ppg_hr_comparison


REAL_DATA_DIR = Path(__file__).parent / "real_data"
ARCHIVES = {
    "mlx_ayane": "mlx_ayane.zip",
    "mlx_shion": "mlx_shion.zip",
    "ppg_hr_ayane": "ppg_hr_ayane.zip",
    "ppg_hr_shion": "ppg_hr_shion.zip",
    "ppg_acc_ayane": "ppg_acc_ayane.zip",
    "ppg_acc_shion": "ppg_acc_shion.zip",
    "ppg_compare_day1": "ppg_compare_day1.zip",
    "ppg_compare_day2": "ppg_compare_day2.zip",
}
HAS_ALL_DATA = all((REAL_DATA_DIR / name).is_file() for name in ARCHIVES.values())


def _read_entry(case, filename):
    archive = REAL_DATA_DIR / ARCHIVES[case]
    with ZipFile(archive) as data_zip:
        return data_zip.read(filename)


def _files(case, names):
    return {name: BytesIO(_read_entry(case, name)) for name in names}


def _assert_mlx_matches(test, result, expected):
    test.assertEqual(result["status"], "success", result.get("message"))
    rows = result["data"]
    test.assertEqual(len(rows), len(expected))
    for row, ref in zip(rows, expected):
        normalize = lambda value: unicodedata.normalize("NFKC", "".join(value.split()))
        test.assertEqual(normalize(row["task"]), normalize(ref[0]))
        test.assertEqual(row["count"], ref[1])
        for key, value, digits in zip(
            ("mae", "rmse", "mean_body_temp", "mean_object_c", "mean_ambient_c"),
            ref[2:],
            (4, 4, 3, 3, 3),
        ):
            if value is None:
                test.assertIsNone(row[key], f"{row['task']} / {key}")
            else:
                test.assertEqual(round(row[key], digits), value, f"{row['task']} / {key}")


def _assert_csv_matches(test, actual_text, expected_bytes, tolerance=1e-12):
    actual = pd.read_csv(StringIO(actual_text))
    expected = pd.read_csv(BytesIO(expected_bytes))
    test.assertEqual(actual.columns.tolist(), expected.columns.tolist())
    test.assertEqual(actual.shape, expected.shape)
    pd.testing.assert_frame_equal(
        actual,
        expected,
        check_dtype=False,
        check_exact=False,
        rtol=tolerance,
        atol=tolerance,
    )


def _assert_comparison_matches(test, result, expected):
    test.assertEqual(result["status"], "success", result.get("message"))
    rows = result["data"]
    test.assertEqual(len(rows), len(expected))
    metric_keys = (
        "raw_mae", "raw_rmse", "raw_count",
        "resampled_mae", "resampled_rmse", "resampled_count",
    )
    for row, ref in zip(rows, expected):
        test.assertEqual(row["task"], ref[0])
        metrics = row["comparisons"][0]
        for key, value in zip(metric_keys, ref[1:]):
            if value is None:
                test.assertIsNone(metrics[key], f"{row['task']} / {key}")
            elif key.endswith("count"):
                test.assertEqual(metrics[key], value, f"{row['task']} / {key}")
            else:
                test.assertEqual(round(metrics[key], 4), value, f"{row['task']} / {key}")


@unittest.skipUnless(HAS_ALL_DATA, "tests/real_data のローカル実測 ZIP が未配置")
class RealDataRegressionTests(unittest.TestCase):
    def test_mlx_ayane_matches_reference_image(self):
        names = [
            "body_temperature.csv", "MLX_R_mini_2026-07-21-19-50.csv",
            "Ayane_experiment1_log.csv",
        ]
        result = process_mlx_common(_files("mlx_ayane", names), "normal", True, 5)
        _assert_mlx_matches(self, result, [
            ("Start", 0, None, None, None, None, None),
            ("順応(5分)", 10, 0.0328, 0.0376, 36.356, 36.377, 36.054),
            ("安静(5分)", 10, 0.0545, 0.0579, 36.408, 36.464, 36.149),
            ("朗読(1分)", 2, 0.0517, 0.0534, 36.430, 36.484, 36.182),
            ("トレッドミルへ移動・準備(2分)", 4, 0.0526, 0.0546, 36.435, 36.488, 36.195),
            ("トレッドミル歩行4km/h(5分)", 10, 0.0384, 0.0423, 36.380, 36.423, 36.155),
            ("トレッドミル早歩き5.5km/h(5分)", 10, 0.0587, 0.0648, 36.243, 36.302, 36.052),
            ("椅子へ移動・準備(30秒)", 1, 0.0451, 0.0451, 36.230, 36.312, 36.038),
            ("回復状態の測定(5分)", 10, 0.0855, 0.0869, 36.264, 36.349, 36.080),
        ])

    def test_mlx_shion_matches_reference_image(self):
        names = [
            "body_temperature.csv", "MLX_R_mini_2026-07-21-21-08.csv",
            "shion_experiment1_log.csv",
        ]
        result = process_mlx_common(_files("mlx_shion", names), "normal", True, 5)
        _assert_mlx_matches(self, result, [
            ("Start", 0, None, None, None, None, None),
            ("順応(5分)", 10, 0.1466, 0.1588, 36.938, 36.784, 35.817),
            ("安静(5分)", 10, 0.0893, 0.0921, 36.971, 36.880, 35.974),
            ("朗読(1分)", 2, 0.0860, 0.0875, 36.995, 36.912, 36.044),
            ("トレッドミルへ移動・準備(2分)", 4, 0.0898, 0.0903, 37.007, 36.910, 36.098),
            ("トレッドミル歩行4km/h(5分)", 10, 0.1383, 0.1391, 37.014, 36.880, 36.045),
            ("トレッドミル早歩き5.5km/h(5分)", 10, 0.1044, 0.1064, 36.974, 36.863, 35.814),
            ("椅子へ移動・準備(30秒)", 1, 0.0995, 0.0995, 36.960, 36.873, 35.718),
            ("回復状態の測定(5分)", 10, 0.1176, 0.1193, 37.004, 36.888, 35.826),
        ])

    def test_ppg_to_hr_ayane_matches_saved_output(self):
        raw = "MAX_R_mini_2026-07-21-19-50.csv"
        result = process_ppg_to_hr(_files("ppg_hr_ayane", [raw]), True, 5)
        self.assertEqual(result["status"], "success", result.get("message"))
        self.assertEqual(result["download"]["filename"], raw[:-4] + "_HR.csv")
        _assert_csv_matches(
            self, result["download"]["csv_text"],
            _read_entry("ppg_hr_ayane", raw[:-4] + "_HR.csv"), tolerance=0,
        )

    def test_ppg_to_hr_shion_matches_saved_output(self):
        raw = "MAX_R_mini_2026-07-21-21-08.csv"
        result = process_ppg_to_hr(_files("ppg_hr_shion", [raw]), True, 5)
        self.assertEqual(result["status"], "success", result.get("message"))
        self.assertEqual(result["download"]["filename"], raw[:-4] + "_HR.csv")
        _assert_csv_matches(
            self, result["download"]["csv_text"],
            _read_entry("ppg_hr_shion", raw[:-4] + "_HR.csv"), tolerance=0,
        )

    def _test_ppg_acc(self, person, raw_fin, raw_ear, log):
        input_names = [raw_fin, raw_ear, log]
        result = perform_ppg_acc_analysis(_files(f"ppg_acc_{person}", input_names), True, 5)
        self.assertEqual(result["status"], "success", result.get("message"))
        _assert_csv_matches(
            self, result["summary_download"]["csv_text"],
            _read_entry(f"ppg_acc_{person}", "PPG_ACC_Task_Summary.csv"),
        )
        _assert_csv_matches(
            self, result["detail_download"]["csv_text"],
            _read_entry(f"ppg_acc_{person}", "PPG_ACC_Window_Detail.csv"),
        )

    def test_ppg_acc_ayane_matches_saved_outputs(self):
        self._test_ppg_acc(
            "ayane", "MAX_fin_2026-07-21-19-50.csv",
            "MAX_R_mini_2026-07-21-19-50.csv", "Ayane_experiment1_log.csv",
        )

    def test_ppg_acc_shion_matches_saved_outputs(self):
        self._test_ppg_acc(
            "shion", "MAX_fin_2026-07-21-21-08.csv",
            "MAX_R_mini_2026-07-21-21-08.csv", "shion_experiment1_log.csv",
        )

    def _test_ppg_comparison(self, day, log, left, right, expected):
        names = [left, right, log]
        result = perform_ppg_hr_comparison(_files(f"ppg_compare_{day}", names), True, 5)
        _assert_comparison_matches(self, result, expected)

    def test_ppg_comparison_day1_matches_reference_image(self):
        self._test_ppg_comparison("day1", "2026-10-14_activity1_log.csv",
            "MAX_L_2026-10-14-17-10_HR.csv", "MAX_R_2026-10-14-17-10_HR.csv", [
                ("Start", None, None, 0, None, None, 0),
                ("休憩", 0.0247, 0.0248, 170, 0.0247, 0.0247, 1),
                ("作業", 1.3597, 2.5031, 191201, 0.5477, 0.7160, 32),
                ("軽食", 2.0100, 3.0924, 80287, 1.0897, 1.3154, 14),
                ("休憩", 2.8529, 3.9554, 57252, 0.9274, 1.0829, 10),
                ("ランドマークテスト", 1.2310, 2.6379, 51268, 0.6261, 0.7375, 9),
                ("休憩(外移動あり)", 2.4863, 4.7555, 177158, 1.2711, 2.1144, 30),
                ("授業", 1.7427, 3.0272, 438263, 0.7531, 1.0906, 74),
            ])

    def test_ppg_comparison_day2_matches_reference_image(self):
        self._test_ppg_comparison("day2", "2026-10-16_activity1_log.csv",
            "MAX_L3_2026-10-16-17-37_HR.csv", "MAX_R3_2026-10-16-17-37_HR.csv", [
                ("Start", 0.3183, 1.0825, 61437, 0.2730, 0.4137, 11),
                ("食事", 0.2012, 0.8664, 48207, 0.1718, 0.2909, 9),
                ("休憩(卓球観戦)", 0.1205, 0.5719, 75566, 0.0797, 0.1945, 13),
                ("作業", 0.3008, 0.9202, 355331, 0.1531, 0.2991, 60),
                ("大判焼き", 1.0778, 1.7132, 88207, 0.4207, 0.5059, 15),
                ("作業", 1.7723, 2.8735, 205158, 0.5390, 0.6921, 35),
            ])


if __name__ == "__main__":
    unittest.main()
