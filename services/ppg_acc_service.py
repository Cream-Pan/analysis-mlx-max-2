# PPG＋ACC解析：ローデータ＋ログから共通時刻窓を生成する版
# 入力：Fin生データCSV，耳たぶ生データCSV，ログCSV
# Quality CSVは使用しない
# 10 s窓，5 s間隔をログのタスク開始時刻から共通生成する

import io
import re

import numpy as np
import pandas as pd
from scipy.signal import coherence, detrend, find_peaks, get_window

from services.common import config, load_log_tasks
from services.ppg_service import load_ppg_raw_csv


WINDOW_SEC = 10.0
STEP_SEC = 5.0
FREQ_MIN_HZ = 0.8
FREQ_MAX_HZ = 3.0
FREQ_DIFF_THRESHOLD_HZ = 0.1
COHERENCE_THRESHOLD = 0.8
TASK_EVALUABLE_THRESHOLD = 50.0

# 10 s窓のうち，最低80 %のサンプルがある場合にFFT解析する．
MIN_SAMPLE_RATIO = 0.8

# 現行HR推定ロジックの設定値．
SEARCH_WINDOW_BPM = 25.0
LOST_RESET_SEC = 5.0
PEAK_RATIO_THRESHOLD = 1.0
MAX_PEAK_WIDTH_HZ = 0.8


DETAIL_COLUMNS = [
    "Task_Name",
    "Window_Number",
    "Window_Start",
    "Window_End",
    "Window_Center",
    "Fin_Sample_Count",
    "Fin_Data_Sufficient",
    "Fin_HR_BPM_Window",
    "Fin_HR_Status",
    "Fin_HR_Estimation_Success",
    "Fin_PPG_Peak_Hz",
    "Fin_ACC_Peak_Hz",
    "Fin_Peak_Diff_Hz",
    "Fin_Coherence_At_ACC_Peak",
    "Fin_Motion_Artifact",
    "Fin_HR_Usable",
    "Ear_Sample_Count",
    "Ear_Data_Sufficient",
    "Ear_HR_BPM_Window",
    "Ear_HR_Status",
    "Ear_HR_Estimation_Success",
    "Ear_PPG_Peak_Hz",
    "Ear_ACC_Peak_Hz",
    "Ear_Peak_Diff_Hz",
    "Ear_Coherence_At_ACC_Peak",
    "Ear_Motion_Artifact",
    "Ear_HR_Usable",
    "Pair_Usable",
    "Error_BPM",
]


def _fill_nan(values):
    arr = np.asarray(values, dtype=float).copy()
    valid = np.isfinite(arr)

    if not np.any(valid):
        return None

    arr[~valid] = np.mean(arr[valid])
    return arr


def _estimate_sampling_frequency(df):
    if "RecvJST" not in df.columns or len(df) < 2:
        return 100

    mean_dt = (
        df["RecvJST"]
        .head(1000)
        .diff()
        .dt.total_seconds()
        .mean()
    )

    if pd.isna(mean_dt) or mean_dt <= 0:
        return 100

    return max(1, int(round(1.0 / mean_dt)))


def _resolve_raw_files(uploaded_files):
    raw_cfg = config["ppg_columns"]["raw_csv"]
    required_columns = {
        raw_cfg["time"],
        raw_cfg["ir"],
        raw_cfg["red"],
        raw_cfg["accel_x"],
        raw_cfg["accel_y"],
        raw_cfg["accel_z"],
        raw_cfg["elapsed_ms"],
    }

    candidates = []

    for filename, file_obj in uploaded_files.items():
        if not filename.lower().endswith(".csv"):
            continue

        if re.search(r"_log\.csv$", filename, flags=re.IGNORECASE):
            continue

        try:
            header = pd.read_csv(
                io.BytesIO(file_obj.read()),
                nrows=0,
            )
            file_obj.seek(0)
        except Exception:
            file_obj.seek(0)
            continue

        if required_columns.issubset(set(header.columns)):
            candidates.append(filename)

    fin_candidates = [
        filename
        for filename in candidates
        if "fin" in filename.lower()
    ]
    ear_candidates = [
        filename
        for filename in candidates
        if "fin" not in filename.lower()
    ]

    if len(fin_candidates) != 1:
        detail = ", ".join(fin_candidates) if fin_candidates else "なし"
        raise ValueError(
            "FinのPPG生データCSVを1つ指定してください．"
            f"候補: {detail}"
        )

    if len(ear_candidates) != 1:
        detail = ", ".join(ear_candidates) if ear_candidates else "なし"
        raise ValueError(
            "耳たぶのPPG生データCSVを1つ指定してください．"
            f"候補: {detail}"
        )

    return fin_candidates[0], ear_candidates[0]


def _create_task_windows(tasks):
    """
    ログの各タスク開始時刻を基準として，
    10 s窓を5 s間隔で作る．

    タスク境界をまたぐ窓は作らない．
    """
    windows = []

    for task in tasks:
        task_start = pd.Timestamp(task["Start_Time"])
        task_end = pd.Timestamp(task["End_Time"])

        window_number = 1
        window_start = task_start

        while window_start + pd.Timedelta(seconds=WINDOW_SEC) <= task_end:
            window_end = window_start + pd.Timedelta(seconds=WINDOW_SEC)
            window_center = window_start + pd.Timedelta(
                seconds=WINDOW_SEC / 2.0
            )

            windows.append({
                "Task_Name": task["Task_Name"],
                "Window_Number": window_number,
                "Window_Start": window_start,
                "Window_End": window_end,
                "Window_Center": window_center,
            })

            window_number += 1
            window_start += pd.Timedelta(seconds=STEP_SEC)

    return windows


def _dominant_frequency(values, fs):
    arr = _fill_nan(values)

    if (
        arr is None
        or len(arr) < 2
        or fs <= 0
        or np.std(arr) <= 0
    ):
        return np.nan

    arr = detrend(arr)
    arr = arr * get_window("hann", len(arr))

    spectrum = np.abs(np.fft.rfft(arr))
    freqs = np.fft.rfftfreq(len(arr), d=1.0 / fs)
    mask = (
        (freqs >= FREQ_MIN_HZ)
        & (freqs <= FREQ_MAX_HZ)
    )

    if not np.any(mask):
        return np.nan

    return float(freqs[mask][np.argmax(spectrum[mask])])


def _coherence_at_frequency(ppg_values, acc_values, fs, target_hz):
    if not np.isfinite(target_hz) or fs <= 0:
        return np.nan

    ppg = _fill_nan(ppg_values)
    acc = _fill_nan(acc_values)

    if ppg is None or acc is None:
        return np.nan

    length = min(len(ppg), len(acc))
    if length < 8:
        return np.nan

    ppg = ppg[:length]
    acc = acc[:length]

    if np.std(ppg) <= 0 or np.std(acc) <= 0:
        return np.nan

    ppg = detrend(ppg)
    acc = detrend(acc)

    nperseg = min(
        max(8, int(round(5.0 * fs))),
        length,
    )
    noverlap = nperseg // 2

    try:
        with np.errstate(divide="ignore", invalid="ignore"):
            freqs, coherence_values = coherence(
                ppg,
                acc,
                fs=fs,
                window="hann",
                nperseg=nperseg,
                noverlap=noverlap,
                detrend=False,
            )
    except Exception:
        return np.nan

    if len(freqs) == 0:
        return np.nan

    nearest_index = int(
        np.argmin(np.abs(freqs - target_hz))
    )
    value = coherence_values[nearest_index]

    return float(value) if np.isfinite(value) else np.nan


def _lost_hr_result(sample_count, data_sufficient):
    return {
        "Sample_Count": int(sample_count),
        "Data_Sufficient": bool(data_sufficient),
        "HR_BPM_Window": np.nan,
        "HR_Status": "Lost",
        "HR_Estimation_Success": False,
        "PPG_Peak_Hz": np.nan,
        "ACC_Peak_Hz": np.nan,
        "Peak_Diff_Hz": np.nan,
        "Coherence_At_ACC_Peak": np.nan,
        "Motion_Artifact": False,
        "HR_Usable": False,
    }


def _estimate_hr_for_window(ppg_values, fs, state):
    """
    現行estimate_hr_and_waveform()と同じ候補選択条件で，
    1つの10 s窓からHR候補を推定する．
    """
    segment = _fill_nan(ppg_values)

    if (
        segment is None
        or len(segment) < 2
        or np.std(segment) <= 0
    ):
        state["time_since_last_valid"] += STEP_SEC
        return np.nan, "Lost", False

    segment_detrended = detrend(segment)
    windowed = (
        segment_detrended
        * get_window("hann", len(segment_detrended))
    )

    fft_spectrum = np.fft.rfft(windowed)
    fft_freqs = np.fft.rfftfreq(
        len(windowed),
        d=1.0 / fs,
    )
    fft_magnitude = np.abs(fft_spectrum)

    roi_indices = np.where(
        (fft_freqs >= FREQ_MIN_HZ)
        & (fft_freqs <= FREQ_MAX_HZ)
    )[0]

    if len(roi_indices) == 0:
        state["time_since_last_valid"] += STEP_SEC
        return np.nan, "Lost", False

    magnitude_roi = fft_magnitude[roi_indices]
    frequency_roi = fft_freqs[roi_indices]

    frequency_resolution = fs / len(windowed)
    max_width_samples = max(
        1,
        int(MAX_PEAK_WIDTH_HZ / frequency_resolution),
    )

    peak_indices, _ = find_peaks(
        magnitude_roi,
        height=0,
        width=(None, max_width_samples),
    )

    if len(peak_indices) == 0:
        peak_indices, _ = find_peaks(
            magnitude_roi,
            height=0,
        )

    if len(peak_indices) == 0:
        state["time_since_last_valid"] += STEP_SEC
        return np.nan, "Lost", False

    candidate_frequencies = frequency_roi[peak_indices]
    candidate_bpms = candidate_frequencies * 60.0
    candidate_magnitudes = magnitude_roi[peak_indices]

    selected_bpm = None
    selected_index = None
    selection_mode = "Reset"

    if (
        state["last_valid_bpm"] is not None
        and state["time_since_last_valid"] < LOST_RESET_SEC
    ):
        minimum_bpm = (
            state["last_valid_bpm"]
            - SEARCH_WINDOW_BPM
        )
        maximum_bpm = (
            state["last_valid_bpm"]
            + SEARCH_WINDOW_BPM
        )
        tracking_mask = (
            (candidate_bpms >= minimum_bpm)
            & (candidate_bpms <= maximum_bpm)
        )

        if np.any(tracking_mask):
            tracking_indices = np.where(tracking_mask)[0]
            selected_index = tracking_indices[
                np.argmax(
                    candidate_magnitudes[tracking_indices]
                )
            ]
            selected_bpm = candidate_bpms[selected_index]
            selection_mode = "Tracked"

    if selected_bpm is None:
        selected_index = int(np.argmax(candidate_magnitudes))
        selected_bpm = candidate_bpms[selected_index]
        selection_mode = "Reset"

    selected_magnitude = candidate_magnitudes[selected_index]
    other_magnitudes = np.delete(
        candidate_magnitudes,
        selected_index,
    )

    is_valid = True
    if len(other_magnitudes) > 0:
        second_maximum = np.max(other_magnitudes)
        if (
            selected_magnitude
            < PEAK_RATIO_THRESHOLD * second_maximum
        ):
            is_valid = False

    if not is_valid:
        state["time_since_last_valid"] += STEP_SEC
        return np.nan, "Lost", False

    selected_bpm = float(selected_bpm)
    state["last_valid_bpm"] = selected_bpm
    state["time_since_last_valid"] = 0.0

    return selected_bpm, selection_mode, True


def _analyze_device_window(
    df,
    fs,
    window_start,
    window_end,
    state,
):
    window_df = df[
        (df["RecvJST"] >= window_start)
        & (df["RecvJST"] < window_end)
    ].copy()

    sample_count = len(window_df)
    expected_samples = max(
        1,
        int(round(WINDOW_SEC * fs)),
    )
    minimum_samples = max(
        8,
        int(np.floor(expected_samples * MIN_SAMPLE_RATIO)),
    )
    data_sufficient = sample_count >= minimum_samples

    if not data_sufficient:
        state["time_since_last_valid"] += STEP_SEC
        return _lost_hr_result(
            sample_count,
            data_sufficient=False,
        )

    ppg_values = window_df["IR_Value"].to_numpy(dtype=float)
    acceleration_magnitude = np.sqrt(
        window_df["Accel_X_mg"].to_numpy(dtype=float) ** 2
        + window_df["Accel_Y_mg"].to_numpy(dtype=float) ** 2
        + window_df["Accel_Z_mg"].to_numpy(dtype=float) ** 2
    )

    hr_bpm, hr_status, hr_success = _estimate_hr_for_window(
        ppg_values,
        fs,
        state,
    )

    # Motion Artifact判定では，実際にHRとして採用した周波数を使用する．
    ppg_peak_hz = (
        float(hr_bpm / 60.0)
        if hr_success and np.isfinite(hr_bpm)
        else _dominant_frequency(ppg_values, fs)
    )
    acc_peak_hz = _dominant_frequency(
        acceleration_magnitude,
        fs,
    )

    peak_diff_hz = (
        float(abs(ppg_peak_hz - acc_peak_hz))
        if (
            np.isfinite(ppg_peak_hz)
            and np.isfinite(acc_peak_hz)
        )
        else np.nan
    )

    coherence_value = _coherence_at_frequency(
        ppg_values,
        acceleration_magnitude,
        fs,
        acc_peak_hz,
    )

    frequency_match = bool(
        np.isfinite(peak_diff_hz)
        and peak_diff_hz <= FREQ_DIFF_THRESHOLD_HZ
    )
    strong_coupling = bool(
        np.isfinite(coherence_value)
        and coherence_value >= COHERENCE_THRESHOLD
    )

    motion_artifact = bool(
        hr_success
        and frequency_match
        and strong_coupling
    )
    hr_usable = bool(
        hr_success
        and not motion_artifact
    )

    return {
        "Sample_Count": int(sample_count),
        "Data_Sufficient": True,
        "HR_BPM_Window": (
            float(hr_bpm)
            if hr_success
            else np.nan
        ),
        "HR_Status": hr_status,
        "HR_Estimation_Success": bool(hr_success),
        "PPG_Peak_Hz": ppg_peak_hz,
        "ACC_Peak_Hz": acc_peak_hz,
        "Peak_Diff_Hz": peak_diff_hz,
        "Coherence_At_ACC_Peak": coherence_value,
        "Motion_Artifact": motion_artifact,
        "HR_Usable": hr_usable,
    }


def _prefix_result(result, prefix):
    return {
        f"{prefix}_{key}": value
        for key, value in result.items()
    }


def _safe_rate(count, total):
    if total <= 0:
        return None

    return float(count / total * 100.0)


def _summarize_device(task_df, prefix):
    total = int(len(task_df))

    tracked_count = int(
        (task_df[f"{prefix}_HR_Status"] == "Tracked").sum()
    )
    reset_count = int(
        (task_df[f"{prefix}_HR_Status"] == "Reset").sum()
    )
    lost_count = int(
        (task_df[f"{prefix}_HR_Status"] == "Lost").sum()
    )
    success_count = int(
        task_df[f"{prefix}_HR_Estimation_Success"].sum()
    )
    motion_count = int(
        task_df[f"{prefix}_Motion_Artifact"].sum()
    )
    usable_count = int(
        task_df[f"{prefix}_HR_Usable"].sum()
    )

    return {
        f"{prefix}_Total_Window_Count": total,
        f"{prefix}_Tracked_Window_Count": tracked_count,
        f"{prefix}_Reset_Window_Count": reset_count,
        f"{prefix}_Lost_Window_Count": lost_count,
        f"{prefix}_Lost_Rate": _safe_rate(lost_count, total),
        f"{prefix}_HR_Estimation_Success_Count": success_count,
        f"{prefix}_HR_Estimation_Success_Rate": _safe_rate(
            success_count,
            total,
        ),
        f"{prefix}_Motion_Artifact_Count": motion_count,
        f"{prefix}_Motion_Artifact_Rate": _safe_rate(
            motion_count,
            total,
        ),
        f"{prefix}_HR_Usable_Count": usable_count,
        f"{prefix}_HR_Usable_Rate": _safe_rate(
            usable_count,
            total,
        ),
    }


def _json_records(df):
    records = []

    for row in df.to_dict(orient="records"):
        converted = {}

        for key, value in row.items():
            if value is None or pd.isna(value):
                converted[key] = None
            elif isinstance(value, pd.Timestamp):
                converted[key] = value.isoformat()
            elif isinstance(value, np.generic):
                converted[key] = value.item()
            else:
                converted[key] = value

        records.append(converted)

    return records


def perform_ppg_acc_analysis(
    uploaded_files,
    has_log,
    interval_min,
    analysis_start_offset_sec=0,
    analysis_duration_sec=0,
):
    """
    ログのタスク時刻からFin・耳たぶ共通の10 s窓を作り，
    両方のPPG生データと加速度を一括解析する．
    """
    try:
        if not has_log:
            raise ValueError(
                "PPG＋ACC解析ではログファイルが必須です"
            )

        fin_filename, ear_filename = _resolve_raw_files(
            uploaded_files
        )

        fin_df = load_ppg_raw_csv(
            uploaded_files[fin_filename]
        )
        ear_df = load_ppg_raw_csv(
            uploaded_files[ear_filename]
        )

        if fin_df.empty or ear_df.empty:
            raise ValueError(
                "Finまたは耳たぶのPPG生データが空です"
            )

        fin_fs = _estimate_sampling_frequency(fin_df)
        ear_fs = _estimate_sampling_frequency(ear_df)

        base_day = min(
            fin_df["RecvJST"].min(),
            ear_df["RecvJST"].min(),
        ).normalize()

        tasks = load_log_tasks(
            uploaded_files,
            True,
            interval_min,
            fin_df["RecvJST"].min(),
            fin_df["RecvJST"].max(),
            base_day,
        )
        common_windows = _create_task_windows(tasks)

        if not common_windows:
            raise ValueError(
                "10秒窓を作成できるタスクがありません"
            )

        fin_state = {
            "last_valid_bpm": None,
            "time_since_last_valid": 0.0,
        }
        ear_state = {
            "last_valid_bpm": None,
            "time_since_last_valid": 0.0,
        }

        detail_rows = []

        for window in common_windows:
            fin_result = _analyze_device_window(
                fin_df,
                fin_fs,
                window["Window_Start"],
                window["Window_End"],
                fin_state,
            )
            ear_result = _analyze_device_window(
                ear_df,
                ear_fs,
                window["Window_Start"],
                window["Window_End"],
                ear_state,
            )

            pair_usable = bool(
                fin_result["HR_Usable"]
                and ear_result["HR_Usable"]
                and np.isfinite(fin_result["HR_BPM_Window"])
                and np.isfinite(ear_result["HR_BPM_Window"])
            )
            error_bpm = (
                float(
                    ear_result["HR_BPM_Window"]
                    - fin_result["HR_BPM_Window"]
                )
                if pair_usable
                else np.nan
            )

            detail_rows.append({
                **window,
                **_prefix_result(fin_result, "Fin"),
                **_prefix_result(ear_result, "Ear"),
                "Pair_Usable": pair_usable,
                "Error_BPM": error_bpm,
            })

        detail_df = pd.DataFrame(
            detail_rows,
            columns=DETAIL_COLUMNS,
        )

        summary_rows = []

        for task in tasks:
            task_name = task["Task_Name"]
            task_df = detail_df[
                detail_df["Task_Name"] == task_name
            ].copy()

            fin_summary = _summarize_device(
                task_df,
                "Fin",
            )
            ear_summary = _summarize_device(
                task_df,
                "Ear",
            )

            total_window_count = int(len(task_df))
            valid_pairs = task_df[task_df["Pair_Usable"]]
            valid_pair_count = int(len(valid_pairs))

            fin_usable_rate = fin_summary[
                "Fin_HR_Usable_Rate"
            ]
            task_evaluable = bool(
                fin_usable_rate is not None
                and fin_usable_rate
                >= TASK_EVALUABLE_THRESHOLD
            )

            mae = None
            rmse = None
            bias = None

            if task_evaluable and valid_pair_count > 0:
                errors = valid_pairs[
                    "Error_BPM"
                ].to_numpy(dtype=float)

                mae = float(np.mean(np.abs(errors)))
                rmse = float(
                    np.sqrt(np.mean(errors ** 2))
                )
                bias = float(np.mean(errors))

            if not task_evaluable:
                evaluation = "リファレンス品質不足"
            elif valid_pair_count == 0:
                evaluation = "有効ペア窓なし"
            else:
                evaluation = "評価可能"

            summary_rows.append({
                "Task_Name": task_name,
                **fin_summary,
                **ear_summary,
                "Valid_Pair_Count": valid_pair_count,
                "Valid_Pair_Rate": _safe_rate(
                    valid_pair_count,
                    total_window_count,
                ),
                "MAE": mae,
                "RMSE": rmse,
                "Bias": bias,
                "Task_Evaluable": task_evaluable,
                "Evaluation": evaluation,
            })

        summary_df = pd.DataFrame(summary_rows)

        return {
            "analysis_type": "ppg_acc_analysis",
            "status": "success",
            "title": "PPG＋ACC解析 結果",
            "fin_filename": fin_filename,
            "ear_filename": ear_filename,
            "fin_fs": int(fin_fs),
            "ear_fs": int(ear_fs),
            "data": _json_records(summary_df),
            "summary_download": {
                "filename": "PPG_ACC_Task_Summary.csv",
                "csv_text": summary_df.to_csv(index=False),
            },
            "detail_download": {
                "filename": "PPG_ACC_Window_Detail.csv",
                "csv_text": detail_df.to_csv(index=False),
            },
        }

    except Exception as error:
        return {
            "analysis_type": "ppg_acc_analysis",
            "status": "error",
            "message": f"PPG＋ACC解析エラー: {str(error)}",
        }
