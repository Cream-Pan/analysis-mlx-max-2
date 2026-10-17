"""Mode-specific input contract checks shared with config.json."""
from io import BytesIO
import unittest
from pathlib import Path
from zipfile import ZipFile

from services.common import config, validate_required_files


def _csv(text):
    return BytesIO(text.encode("utf-8"))


RAW_HEADER = (
    "RecvJST,IR_Value,RED_Value,Accel_X_mg,Accel_Y_mg,"
    "Accel_Z_mg,SensorElapsed_ms\n"
)
LOG_HEADER = "Task_Name,Timestamp\n"


class ModeInputSchemaTests(unittest.TestCase):
    def test_every_analysis_mode_has_a_spec(self):
        expected_modes = {
            "show_files", "mlx_evaluation", "max_evaluation",
            "mlx_reevaluation", "ppg_to_hr", "ppg_analysis",
            "ppg_hr_analysis", "ppg_acc_analysis",
        }
        self.assertEqual(set(config["input_specs"]), expected_modes)

    def test_max_fixed_files_require_configured_columns(self):
        files = {
            "ecg.csv": _csv("Timestamp,HeartRate_BPM\n"),
            "PPG_BPM.csv": _csv("RecvJST,HR_BPM\n"),
            "PPG_fin_BPM.csv": _csv("RecvJST,HR_BPM\n"),
        }
        self.assertEqual(validate_required_files(files, "max_evaluation", False), (True, None))

        files["ecg.csv"] = _csv("Timestamp,Other\n")
        ok, message = validate_required_files(files, "max_evaluation", False)
        self.assertFalse(ok)
        self.assertIn("HeartRate_BPM", message)

    def test_ppg_analysis_requires_two_matching_hr_files_and_columns(self):
        one_file = {"left_HR.csv": _csv("RecvJST,HR_BPM\n")}
        ok, message = validate_required_files(one_file, "ppg_analysis", False)
        self.assertFalse(ok)
        self.assertIn("2 個以上", message)

        files = {
            "left_HR.csv": _csv("RecvJST,HR_BPM\n"),
            "right_HR.csv": _csv("RecvJST,HR_BPM\n"),
        }
        self.assertEqual(validate_required_files(files, "ppg_analysis", False), (True, None))

        files["right_HR.csv"] = _csv("RecvJST,Other\n")
        ok, message = validate_required_files(files, "ppg_analysis", False)
        self.assertFalse(ok)
        self.assertIn("HR_BPM", message)

    def test_log_columns_are_checked_only_when_log_is_enabled(self):
        files = {"data.csv": _csv("arbitrary,columns\n")}
        self.assertEqual(validate_required_files(files, "show_files", False), (True, None))

        files["subject_log.csv"] = _csv("Task_Name,WrongColumn\n")
        ok, message = validate_required_files(files, "show_files", True)
        self.assertFalse(ok)
        self.assertIn("Timestamp", message)

    def test_ppg_acc_requires_fin_ear_and_valid_log(self):
        files = {
            "sensor_fin.csv": _csv(RAW_HEADER),
            "sensor_ear.csv": _csv(RAW_HEADER),
        }
        ok, message = validate_required_files(files, "ppg_acc_analysis", False)
        self.assertFalse(ok)
        self.assertIn("ログファイル", message)

        files["subject_log.csv"] = _csv(LOG_HEADER)
        self.assertEqual(validate_required_files(files, "ppg_acc_analysis", True), (True, None))

        files["subject_log.csv"] = _csv("Task_Name,Other\n")
        ok, message = validate_required_files(files, "ppg_acc_analysis", True)
        self.assertFalse(ok)
        self.assertIn("Timestamp", message)

    def test_ppg_to_hr_checks_all_raw_columns(self):
        files = {"raw.csv": _csv(RAW_HEADER)}
        self.assertEqual(validate_required_files(files, "ppg_to_hr", False), (True, None))

        files["raw.csv"] = _csv("RecvJST,IR_Value,RED_Value,SensorElapsed_ms\n")
        ok, message = validate_required_files(files, "ppg_to_hr", False)
        self.assertFalse(ok)
        self.assertIn("Accel_X_mg", message)

    def test_mlx_requires_a_measurement_file_with_minimum_columns(self):
        body = _csv("Temp,Time\n")
        mlx_header = ",".join(f"column_{index}" for index in range(8)) + "\n"
        files = {
            "body_temperature.csv": body,
            "MLX_R_mini.csv": _csv(mlx_header),
        }
        self.assertEqual(validate_required_files(files, "mlx_evaluation", False), (True, None))

        files["MLX_R_mini.csv"] = _csv("a,b,c\n")
        ok, message = validate_required_files(files, "mlx_evaluation", False)
        self.assertFalse(ok)
        self.assertIn("8 列以上", message)


REAL_DATA_DIR = Path(__file__).parent / "real_data"
REAL_ARCHIVES = (
    "mlx_ayane.zip", "mlx_shion.zip", "ppg_acc_ayane.zip",
    "ppg_acc_shion.zip", "ppg_compare_day1.zip", "ppg_compare_day2.zip",
    "ppg_hr_ayane.zip", "ppg_hr_shion.zip",
)


@unittest.skipUnless(
    all((REAL_DATA_DIR / name).is_file() for name in REAL_ARCHIVES),
    "tests/real_data のローカル実測 ZIP が未配置",
)
class RealInputFileContractTests(unittest.TestCase):
    def _archive_files(self, archive_name):
        with ZipFile(REAL_DATA_DIR / archive_name) as archive:
            return {
                Path(name).name: BytesIO(archive.read(name))
                for name in archive.namelist()
                if name.lower().endswith(".csv")
            }

    def test_existing_mlx_and_ppg_acc_inputs_match_the_schema(self):
        for archive_name in ("mlx_ayane.zip", "mlx_shion.zip"):
            files = self._archive_files(archive_name)
            self.assertEqual(
                validate_required_files(files, "mlx_evaluation", True),
                (True, None), archive_name,
            )

        for archive_name in ("ppg_acc_ayane.zip", "ppg_acc_shion.zip"):
            files = self._archive_files(archive_name)
            self.assertEqual(
                validate_required_files(files, "ppg_acc_analysis", True),
                (True, None), archive_name,
            )

    def test_existing_ppg_hr_comparison_inputs_match_the_schema(self):
        for archive_name in ("ppg_compare_day1.zip", "ppg_compare_day2.zip"):
            files = self._archive_files(archive_name)
            self.assertEqual(
                validate_required_files(files, "ppg_analysis", True),
                (True, None), archive_name,
            )

    def test_existing_raw_ppg_inputs_match_conversion_and_waveform_modes(self):
        for archive_name in ("ppg_hr_ayane.zip", "ppg_hr_shion.zip"):
            files = self._archive_files(archive_name)
            raw_file = next(name for name in files if name.lower().endswith(".csv") and "_hr.csv" not in name.lower())
            self.assertEqual(
                validate_required_files(
                    {raw_file: files[raw_file]}, "ppg_to_hr", False
                ),
                (True, None), archive_name,
            )
            self.assertEqual(
                validate_required_files(
                    {raw_file: files[raw_file]}, "ppg_hr_analysis", False
                ), (True, None), archive_name,
            )


if __name__ == "__main__":
    unittest.main()
