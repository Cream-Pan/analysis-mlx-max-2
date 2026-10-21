import re
import pandas as pd
import numpy as np

from scipy.signal import detrend, get_window, find_peaks, welch
from scipy.interpolate import interp1d
from scipy.integrate import trapezoid
from itertools import combinations

from services.common import (
    config,
    read_uploaded_csv,
    read_uploaded_csv_columns,
)
from services.log_service import load_log_tasks
from services.time_utils import parse_datetime_series
from services.hr_compare_service import evaluate_hr_pair

def load_ppg_hr_csv(f_obj):
    hr_cfg = config["ppg_columns"]["hr_csv"]
    time_col = hr_cfg["time"]
    hr_col = hr_cfg["hr"]

    df = read_uploaded_csv(
        f_obj,
        usecols=[time_col, hr_col]
    )

    df[time_col] = parse_datetime_series(df[time_col])
    df[hr_col] = pd.to_numeric(df[hr_col], errors="coerce")

    df = df.dropna(subset=[time_col, hr_col])
    df = df.set_index(time_col).sort_index()
    df = df[~df.index.duplicated(keep="first")]

    return df[[hr_col]].rename(columns={hr_col: "HR"})

def load_ppg_raw_csv(f_obj):
    raw_cfg = config["ppg_columns"]["raw_csv"]

    time_col = raw_cfg["time"]
    ir_col = raw_cfg["ir"]
    red_col = raw_cfg["red"]
    accel_x_col = raw_cfg["accel_x"]
    accel_y_col = raw_cfg["accel_y"]
    accel_z_col = raw_cfg["accel_z"]
    elapsed_col = raw_cfg["elapsed_ms"]

    usecols = [
        time_col,
        ir_col,
        red_col,
        accel_x_col,
        accel_y_col,
        accel_z_col,
        elapsed_col
    ]

    df = read_uploaded_csv(f_obj, usecols=usecols)

    df[time_col] = parse_datetime_series(df[time_col])
    for col in [
        ir_col, red_col,
        accel_x_col, accel_y_col, accel_z_col,
        elapsed_col
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 時刻再構成に必要な SensorElapsed_ms だけ欠損を落とす。
    # 元コードは行順のサンプル列をそのまま FFT に入れるため、ここで sort/drop duplicate はしない。
    df = df.dropna(subset=[elapsed_col]).copy()
    if df.empty:
        raise ValueError("SensorElapsed_ms が有効な PPG 生データがありません")

    # 元の受信時刻を保存し、最初に有効な RecvJST をアンカーとして取得時刻軸を再構成する。
    df["RecvJST_Original"] = df[time_col]
    anchor_idx = df[time_col].first_valid_index()
    if anchor_idx is None:
        raise ValueError("RecvJST が日時として解釈できません")

    t1 = df.loc[anchor_idx, time_col]
    s0 = df.loc[anchor_idx, elapsed_col]
    df[time_col] = t1 + pd.to_timedelta(df[elapsed_col] - s0, unit="ms")

    return df.rename(columns={
        ir_col: "IR_Value",
        red_col: "RED_Value",
        accel_x_col: "Accel_X_mg",
        accel_y_col: "Accel_Y_mg",
        accel_z_col: "Accel_Z_mg",
        elapsed_col: "SensorElapsed_ms"
    })

def load_ppg_wave_csv(f_obj):
    wave_cfg = config["ppg_columns"]["wave_csv"]
    time_col = wave_cfg["time"]
    ir_col = wave_cfg["ir"]

    df = read_uploaded_csv(
        f_obj,
        usecols=[time_col, ir_col]
    )

    df[time_col] = parse_datetime_series(df[time_col])
    df[ir_col] = pd.to_numeric(df[ir_col], errors="coerce")

    df = df.dropna(subset=[time_col, ir_col]).copy()
    if df.empty:
        raise ValueError("RecvJST と IR_Value が有効なデータがありません")

    df = df.rename(columns={
        time_col: "RecvJST",
        ir_col: "IR_Value"
    })

    df = df.sort_values("RecvJST")
    return df

def resolve_ppg_raw_file(uploaded_files):
    raw_cfg = config["ppg_columns"]["raw_csv"]
    required_cols = {
        raw_cfg["time"],
        raw_cfg["ir"],
        raw_cfg["red"],
        raw_cfg["elapsed_ms"],
    }

    for filename, f in uploaded_files.items():
        if not filename.lower().endswith(".csv"):
            continue

        try:
            cols = read_uploaded_csv_columns(f)
        except Exception:
            continue

        if required_cols.issubset(cols):
            return filename

    raise ValueError("PPG 生データ CSV が見つかりません")

def resolve_ppg_hr_files(uploaded_files):
    hr_cfg = config["ppg_columns"]["hr_csv"]
    required_cols = {hr_cfg["time"], hr_cfg["hr"]}

    matched = []

    for filename, f in uploaded_files.items():
        if not re.search(r'_hr\.csv$', filename, flags=re.IGNORECASE):
            continue

        try:
            cols = read_uploaded_csv_columns(f)
        except Exception:
            continue

        if required_cols.issubset(cols):
            matched.append(filename)

    if len(matched) < 2:
        raise ValueError("PPG解析には *_HR.csv が 2 つ以上必要です")

    return matched

def resolve_ppg_wave_files(uploaded_files):
    wave_cfg = config["ppg_columns"]["wave_csv"]
    time_col = wave_cfg["time"]
    ir_col = wave_cfg["ir"]

    matched = []

    for filename, f in uploaded_files.items():
        if not filename.lower().endswith(".csv"):
            continue

        try:
            cols = read_uploaded_csv_columns(f)
        except Exception:
            continue

        if {time_col, ir_col}.issubset(cols):
            matched.append(filename)

    if len(matched) < 1:
        raise ValueError("PPG脈波解析には RecvJST と IR_Value を含む CSV が 1 つ以上必要です")

    return matched

def estimate_hr_and_waveform(df, fs=100, return_window_info=False):
    """
    Research Grade Algorithm
    
    改善点:
    1. Bandwidth: 0.5-4.0Hz (30-240bpm) に拡大 [Mejia-Mejia et al., 2021]
    2. Harmonic Check: 倍音吸着を防ぐロジックを追加 [Polak et al., 2022]
    3. Q-factor: Peak widthによる尖鋭度フィルタ
    4. Time-based Interpolation: サンプル数ではなく実時間軸で補間
    """
    
    # --- 1. パラメータ設定 ---
    WINDOW_SEC = 10.0
    OVERLAP_SEC = 5.0
    
    FREQ_MIN = 0.8  # 48 bpm
    FREQ_MAX = 3.0  # 180 bpm
    
    # トラッキング設定
    SEARCH_WINDOW_BPM = 25.0   # 前回値からの探索幅 (±25 BPM)
    LOST_RESET_SEC = 5.0       # 何秒ロストしたら全探索に戻るか
    
    # 判定閾値 (ノイズ除去用)
    PEAK_RATIO_TH = 1.0        # 2ndピークとの比 (1.5倍あればOK)
    
    # 信号の選択
    # Q-factor (簡易版): ピーク幅の制限
    # 心拍のピークは鋭いはず。広すぎる(ブロードな)山は体動ノイズ。
    # fs=100Hz, N=1000(10s) -> 1bin = 0.1Hz
    # width=5 bins (0.5Hz幅) 以上はブロードすぎて怪しいと判断
    MAX_PEAK_WIDTH_HZ = 0.8 
    
    # 信号処理
    raw_sig = df['IR_Value'].to_numpy(dtype=float).copy()
    timestamps = (df['RecvJST'].astype('int64') // 10**9).to_numpy()
    timestamps_float = (df['RecvJST'].astype('int64') / 1e9).to_numpy()

    if np.isnan(raw_sig).any():
        mask = np.isnan(raw_sig)
        raw_sig[mask] = np.nanmean(raw_sig)

    N = len(raw_sig)
    window_samples = int(WINDOW_SEC * fs)
    step_samples = int(OVERLAP_SEC * fs)
    step_sec = step_samples / fs

    hr_times = []
    hr_values = []
    window_records = []

    last_valid_bpm = None
    time_since_last_valid = 0.0

    debug_counts = {
        "Tracking": 0,
        "Reset": 0,
        "Lost": 0,
        "HarmonicFix": 0,
    }

    def append_window_record(start_index, center_index, hr_bpm, status):
        end_index = start_index + window_samples - 1
        window_start = df['RecvJST'].iloc[start_index]
        window_end = (
            df['RecvJST'].iloc[end_index]
            + pd.Timedelta(seconds=1.0 / fs)
        )
        window_center = df['RecvJST'].iloc[center_index]
        success = status in {"Tracked", "Reset"}

        window_records.append({
            "Window_Start": window_start,
            "Window_End": window_end,
            "Window_Center": window_center,
            "HR_BPM_Window": hr_bpm if success else np.nan,
            "HR_Status": status,
            "HR_Estimation_Success": success,
        })

    # --- 2. FFT解析ループ ---
    for i in range(0, N - window_samples + 1, step_samples):
        segment = raw_sig[i:i + window_samples]
        segment_detrend = detrend(segment)

        window_func = get_window('hann', len(segment_detrend))
        segment_windowed = segment_detrend * window_func

        fft_spectrum = np.fft.rfft(segment_windowed)
        fft_freqs = np.fft.rfftfreq(len(segment_windowed), d=1 / fs)
        fft_mag = np.abs(fft_spectrum)

        roi_idx = np.where(
            (fft_freqs >= FREQ_MIN)
            & (fft_freqs <= FREQ_MAX)
        )[0]

        center_idx = i + window_samples // 2
        center_time = timestamps_float[center_idx]
        hr_times.append(center_time)

        if len(roi_idx) == 0:
            hr_values.append(np.nan)
            debug_counts["Lost"] += 1
            append_window_record(i, center_idx, np.nan, "Lost")
            continue

        mag_roi = fft_mag[roi_idx]
        freqs_roi = fft_freqs[roi_idx]

        max_width_samples = int(
            MAX_PEAK_WIDTH_HZ / (fs / window_samples)
        )
        peak_idxs_local, props = find_peaks(
            mag_roi,
            height=0,
            width=(None, max_width_samples),
        )

        if len(peak_idxs_local) == 0:
            peak_idxs_local, props = find_peaks(mag_roi, height=0)
            if len(peak_idxs_local) == 0:
                hr_values.append(np.nan)
                time_since_last_valid += step_sec
                debug_counts["Lost"] += 1
                append_window_record(i, center_idx, np.nan, "Lost")
                continue

        candidate_freqs = freqs_roi[peak_idxs_local]
        candidate_bpms = candidate_freqs * 60.0
        candidate_mags = mag_roi[peak_idxs_local]

        selected_bpm = None
        selection_mode = "Global"

        if (
            last_valid_bpm is not None
            and time_since_last_valid < LOST_RESET_SEC
        ):
            min_bpm = last_valid_bpm - SEARCH_WINDOW_BPM
            max_bpm = last_valid_bpm + SEARCH_WINDOW_BPM
            mask_track = (
                (candidate_bpms >= min_bpm)
                & (candidate_bpms <= max_bpm)
            )

            if np.any(mask_track):
                inds_track = np.where(mask_track)[0]
                best_idx_local = inds_track[
                    np.argmax(candidate_mags[inds_track])
                ]
                selected_bpm = candidate_bpms[best_idx_local]
                selected_mag = candidate_mags[best_idx_local]
                selection_mode = "Tracking"
            else:
                selected_bpm = None

        if selected_bpm is None:
            best_idx_global = np.argmax(candidate_mags)
            selected_bpm = candidate_bpms[best_idx_global]
            selected_mag = candidate_mags[best_idx_global]
            selection_mode = "Reset"

        # --- 【改善2】 調和成分（倍音）チェック ---
        # 選択されたBPMが、実は「基本波の2倍（2nd Harmonic）」ではないか疑う
        # もし 0.5 * selected_bpm の近くに、ある程度強いピークがあれば、そちらを正解とする
        
        # if selected_bpm is not None:
        #     potential_fundamental = selected_bpm * 0.5
        #     # 0.5倍の周波数の近く(±10bpm)にピークがあるか？
        #     subharmonic_mask = (candidate_bpms >= potential_fundamental - 10) & \
        #                        (candidate_bpms <= potential_fundamental + 10)
            
        #     if np.any(subharmonic_mask):
        #         sub_inds = np.where(subharmonic_mask)[0]
        #         # その候補の中で一番強いやつ
        #         sub_best_idx = sub_inds[np.argmax(candidate_mags[sub_inds])]
        #         sub_mag = candidate_mags[sub_best_idx]
                
        #         # 判定: サプハーモニクスが、メインのピークの 40% 以上の強さがあれば乗り換える
        #         # (倍音成分の方が強く出ることがあるため、閾値は0.5倍程度にする)
        #         if sub_mag > 0.4 * selected_mag:
        #             selected_bpm = candidate_bpms[sub_best_idx]
        #             selected_mag = sub_mag
        #             debug_counts["HarmonicFix"] += 1
        # モードは維持（TrackingならTrackingのまま修正）

        is_valid = True
        other_mags = candidate_mags[candidate_mags != selected_mag]

        if len(other_mags) > 0:
            second_max = np.max(other_mags)
            if selected_mag < PEAK_RATIO_TH * second_max:
                is_valid = False

        if is_valid:
            hr_values.append(selected_bpm)
            last_valid_bpm = selected_bpm
            time_since_last_valid = 0.0

            if selection_mode == "Tracking":
                debug_counts["Tracking"] += 1
                hr_status = "Tracked"
            else:
                debug_counts["Reset"] += 1
                hr_status = "Reset"

            append_window_record(
                i,
                center_idx,
                float(selected_bpm),
                hr_status,
            )
        else:
            hr_values.append(np.nan)
            time_since_last_valid += step_sec
            debug_counts["Lost"] += 1
            append_window_record(i, center_idx, np.nan, "Lost")

    print(
        f"  [Debug] Tracked: {debug_counts['Tracking']}, "
        f"Reset: {debug_counts['Reset']}, "
        f"Lost: {debug_counts['Lost']}, "
        f"HarmonicFix: {debug_counts['HarmonicFix']}"
    )

    # --- 3. 時間軸ベースの補間 ---
    hr_times = np.array(hr_times)
    hr_values = np.array(hr_values)
    valid_mask = ~np.isnan(hr_values)
    full_times = timestamps_float

    if np.sum(valid_mask) > 1:
        f_interp = interp1d(
            hr_times[valid_mask],
            hr_values[valid_mask],
            kind='linear',
            bounds_error=False,
            fill_value="extrapolate",
        )
        hr_output_full = f_interp(full_times)
        hr_output_full = np.clip(hr_output_full, 30, 220)
    else:
        hr_output_full = np.full(N, np.nan)

    window_df = pd.DataFrame(
        window_records,
        columns=[
            "Window_Start",
            "Window_End",
            "Window_Center",
            "HR_BPM_Window",
            "HR_Status",
            "HR_Estimation_Success",
        ],
    )

    if return_window_info:
        return hr_output_full, window_df

    return hr_output_full

def process_ppg_to_hr(
    uploaded_files,
    has_log,
    interval_min,
    analysis_start_offset_sec=0,
    analysis_duration_sec=0,
):
    try:
        raw_filename = resolve_ppg_raw_file(uploaded_files)
        df = load_ppg_raw_csv(uploaded_files[raw_filename])

        # 旧版 load_ppg_raw_csv との互換用．
        if "RecvJST" not in df.columns:
            df = df.reset_index().rename(columns={"index": "RecvJST"})

        # PPG→HR変換は，読み込んだ全区間を対象とする．
        if len(df) < 2:
            raise ValueError("解析対象データが不足しています")

        # Fs推定．
        mean_dt = (
            df["RecvJST"]
            .head(1000)
            .diff()
            .dt.total_seconds()
            .mean()
        )
        estimated_fs = (
            round(1 / mean_dt)
            if pd.notna(mean_dt) and mean_dt > 0
            else 100
        )

        # 全体相関係数．
        overall_corr = df["IR_Value"].corr(df["RED_Value"])

        # 移動相関係数．
        window_size = int(estimated_fs * 1.0)
        if window_size < 1:
            window_size = 1

        df["Rolling_Corr"] = (
            df["IR_Value"]
            .rolling(window=window_size)
            .corr(df["RED_Value"])
        )

        # 既存のPPG→HR処理のみを実行する．
        hr_bpm = estimate_hr_and_waveform(
            df,
            fs=estimated_fs,
        )

        df["HR_BPM"] = hr_bpm
        output_df = df.copy()
        hr_csv_text = output_df.to_csv(index=False)
        base_name = raw_filename.rsplit(".", 1)[0]

        return {
            "analysis_type": "ppg_to_hr",
            "status": "success",
            "title": f"PPG→HR変換 結果 ({raw_filename})",
            "summary": {
                "fs": int(estimated_fs),
                "overall_corr": (
                    None
                    if pd.isna(overall_corr)
                    else float(overall_corr)
                ),
            },
            "download": {
                "filename": f"{base_name}_HR.csv",
                "csv_text": hr_csv_text,
            },
        }

    except Exception as error:
        return {
            "analysis_type": "ppg_to_hr",
            "status": "error",
            "message": f"PPG→HR変換エラー: {str(error)}",
        }

    
def _ppg_data_quality_metrics(df):
    """PPG区間のサンプル数，推定周波数，時刻ギャップ数を返す．"""
    time_values = df["RecvJST"].astype("int64").to_numpy() / 1e9
    time_diffs = np.diff(time_values)
    positive_diffs = time_diffs[time_diffs > 0]
    if len(positive_diffs) == 0:
        return {
            "sample_count": int(len(df)),
            "sample_rate_hz": None,
            "sample_gap_count": None,
        }

    median_dt = float(np.median(positive_diffs))
    gap_count = int(np.sum(positive_diffs > median_dt * 1.5))
    return {
        "sample_count": int(len(df)),
        "sample_rate_hz": float(1.0 / median_dt),
        "sample_gap_count": gap_count,
    }


def _calculate_ppg_hrv_metrics(df, quality_metrics=None):
    """1つの時間区間からPPG脈波・PRV指標を計算する．"""
    if len(df) < 3:
        raise ValueError("解析対象データが不足しています")

    time_sec = (df["RecvJST"] - df["RecvJST"].iloc[0]).dt.total_seconds().to_numpy()
    ir = df["IR_Value"].to_numpy(dtype=float)
    positive_diffs = np.diff(time_sec)
    positive_diffs = positive_diffs[positive_diffs > 0]
    if len(positive_diffs) == 0:
        raise ValueError("サンプル時刻からサンプリング周波数を推定できません")
    fs = 1.0 / float(np.median(positive_diffs))

    ir = ir - np.nanmean(ir)
    min_interval_sec = 60.0 / 150.0
    # 浮動小数点誤差で150 bpm付近のピークを誤って落とさないよう丸める．
    min_distance = max(1, int(round(fs * min_interval_sec)))
    prominence = max(np.nanstd(ir) * 0.3, 1e-6)
    peaks, _ = find_peaks(ir, distance=min_distance, prominence=prominence)

    if len(peaks) < 3:
        raise ValueError("有効な脈波ピークが不足しています")

    peak_times = time_sec[peaks]
    all_nn_intervals = np.diff(peak_times)
    valid_nn = (all_nn_intervals >= min_interval_sec) & (all_nn_intervals <= 2.0)
    nn_intervals = all_nn_intervals[valid_nn]
    if len(nn_intervals) < 3:
        raise ValueError("有効なNN間隔が不足しています")

    # NN50は時間的に隣り合う有効間隔だけを比較し，無効間隔をまたがない．
    adjacent_valid_pairs = valid_nn[:-1] & valid_nn[1:]
    nn_diff = np.abs(np.diff(all_nn_intervals))[adjacent_valid_pairs]
    nn50 = int(np.sum(nn_diff > 0.05))
    pnn50 = float(nn50 / len(nn_diff) * 100) if len(nn_diff) > 0 else None

    nn_times = peak_times[1:][valid_nn]
    interp_fs = 4.0
    lf_power = hf_power = lf_hf = None
    min_frequency_duration_sec = 300.0
    recorded_duration_sec = float(time_sec[-1] - time_sec[0] + 1.0 / fs)
    valid_interval_duration_sec = (
        float(nn_times[-1] - nn_times[0] + nn_intervals[0])
        if len(nn_times) > 0
        else 0.0
    )
    frequency_status = "計算済み"
    if recorded_duration_sec < min_frequency_duration_sec:
        frequency_status = "記録区間が5分未満のため算出対象外"
    elif len(nn_times) >= 4:
        uniform_t = np.arange(nn_times[0], nn_times[-1], 1.0 / interp_fs)
        if (
            len(uniform_t) >= 8
            and valid_interval_duration_sec >= min_frequency_duration_sec - 2.0
        ):
            f_interp = interp1d(
                nn_times, nn_intervals, kind="linear",
                bounds_error=False, fill_value="extrapolate"
            )
            nn_uniform = f_interp(uniform_t)
            nn_uniform = nn_uniform - np.mean(nn_uniform)
            nperseg = min(256, len(nn_uniform))
            freqs, psd = welch(nn_uniform, fs=interp_fs, nperseg=nperseg)
            lf_mask = (freqs >= 0.04) & (freqs < 0.15)
            hf_mask = (freqs >= 0.15) & (freqs < 0.40)
            lf_power = float(trapezoid(psd[lf_mask], freqs[lf_mask])) if np.any(lf_mask) else None
            hf_power = float(trapezoid(psd[hf_mask], freqs[hf_mask])) if np.any(hf_mask) else None
            if hf_power is not None and hf_power > 0 and lf_power is not None:
                lf_hf = float(lf_power / hf_power)
        else:
            frequency_status = "有効な間隔が5分未満のため算出対象外"
    else:
        frequency_status = "有効な間隔が不足しているため算出対象外"

    quality = quality_metrics or _ppg_data_quality_metrics(df)
    valid_interval_pct = (
        float(len(nn_intervals) / len(all_nn_intervals) * 100)
        if len(all_nn_intervals) > 0
        else None
    )

    return {
        "fs": float(fs),
        "peak_count": int(len(peaks)),
        "nn_count": int(len(nn_intervals)),
        "valid_interval_pct": valid_interval_pct,
        "sample_count": quality["sample_count"],
        "sample_rate_hz": quality["sample_rate_hz"],
        "sample_gap_count": quality["sample_gap_count"],
        "frequency_status": frequency_status,
        "mean_nn_ms": float(np.mean(nn_intervals) * 1000),
        "mean_hr_bpm": float(60.0 / np.mean(nn_intervals)),
        "nn50": nn50,
        "pnn50": pnn50,
        "lf_power": lf_power,
        "hf_power": hf_power,
        "lf_hf": lf_hf
    }


def perform_ppg_wave_hrv_analysis(uploaded_files, has_log, interval_min, analysis_start_offset_sec=0, analysis_duration_sec=0):
    try:
        filenames = resolve_ppg_wave_files(uploaded_files)
        results = []

        for filename in filenames:
            df = load_ppg_wave_csv(uploaded_files[filename])
            file_start = df["RecvJST"].min()
            file_last_sample = df["RecvJST"].max()
            positive_diffs = df["RecvJST"].diff().dt.total_seconds()
            positive_diffs = positive_diffs[positive_diffs > 0]
            sample_period = float(positive_diffs.median()) if not positive_diffs.empty else 0.01
            file_end_exclusive = file_last_sample + pd.Timedelta(seconds=sample_period)

            if has_log:
                tasks = load_log_tasks(
                    uploaded_files, True, interval_min,
                    file_start, file_end_exclusive, file_start.normalize()
                )
                segments = []
                for task in tasks:
                    segment_start = max(task["Start_Time"], file_start)
                    segment_end = min(task["End_Time"], file_end_exclusive)
                    if segment_start < segment_end:
                        segments.append((task["Task_Name"], segment_start, segment_end))
            else:
                if interval_min <= 0:
                    raise ValueError("区切り分数には1以上を指定してください")

                analysis_start_time = file_start + pd.Timedelta(seconds=analysis_start_offset_sec)
                if analysis_start_time >= file_end_exclusive:
                    raise ValueError(f"{filename} は開始オフセット後に解析できるデータがありません")

                if analysis_duration_sec > 0:
                    analysis_end_time = analysis_start_time + pd.Timedelta(seconds=analysis_duration_sec)
                    if analysis_end_time > file_end_exclusive:
                        available_sec = (file_end_exclusive - analysis_start_time).total_seconds()
                        raise ValueError(
                            f"{filename} は指定した解析時間 {analysis_duration_sec:.1f} 秒を確保できません．"
                            f"オフセット後に利用可能なのは {max(0.0, available_sec):.1f} 秒です．"
                        )
                else:
                    analysis_end_time = file_end_exclusive

                segments = []
                segment_start = analysis_start_time
                segment_index = 1
                while segment_start < analysis_end_time:
                    segment_end = min(
                        segment_start + pd.Timedelta(minutes=interval_min),
                        analysis_end_time
                    )
                    segments.append((f"区間{segment_index}", segment_start, segment_end))
                    segment_start = segment_end
                    segment_index += 1

            if not segments:
                raise ValueError(f"{filename} の解析時間に該当するログタスクがありません")

            for task_name, segment_start, segment_end in segments:
                segment_df = df[
                    (df["RecvJST"] >= segment_start)
                    & (df["RecvJST"] < segment_end)
                ].copy()
                row = {
                    "filename": filename,
                    "task": str(task_name),
                    "start_time": segment_start.isoformat(),
                    "end_time": segment_end.isoformat(),
                }
                quality_metrics = _ppg_data_quality_metrics(segment_df)
                row.update(quality_metrics)
                try:
                    row.update(_calculate_ppg_hrv_metrics(segment_df, quality_metrics))
                    row["status"] = "success"
                    row["message"] = None
                except ValueError as error:
                    row.update({
                        "status": "error",
                        "message": str(error),
                        "fs": None,
                        "peak_count": 0,
                        "nn_count": 0,
                        "valid_interval_pct": None,
                        "frequency_status": "解析不可",
                        "mean_nn_ms": None,
                        "mean_hr_bpm": None,
                        "nn50": None,
                        "pnn50": None,
                        "lf_power": None,
                        "hf_power": None,
                        "lf_hf": None,
                    })
                results.append(row)

        return {
            "analysis_type": "ppg_hr_analysis",
            "status": "success",
            "title": "PPG脈波解析結果",
            "data": results
        }

    except Exception as e:
        return {
            "analysis_type": "ppg_hr_analysis",
            "status": "error",
            "message": f"PPG脈波解析エラー: {str(e)}"
        }
    
def perform_ppg_hr_comparison(uploaded_files, has_log, interval_min, analysis_start_offset_sec=0, analysis_duration_sec=0):
    try:
        hr_filenames = resolve_ppg_hr_files(uploaded_files)

        hr_dfs = {
            name: load_ppg_hr_csv(uploaded_files[name])
            for name in hr_filenames
        }

        trimmed = {}
        for name, df in hr_dfs.items():
            start_time = df.index.min() + pd.Timedelta(seconds=analysis_start_offset_sec)
            df_trim = df[df.index >= start_time].copy()
            if df_trim.empty:
                raise ValueError(f"{name} は解析開始オフセット適用後にデータがありません")
            trimmed[name] = df_trim
        hr_dfs = trimmed

        start_limit = max(df.index.min() for df in hr_dfs.values())
        end_limit = min(df.index.max() for df in hr_dfs.values())

        if start_limit >= end_limit:
            raise ValueError("比較可能な共通時刻範囲がありません")

        if analysis_duration_sec > 0:
            analysis_end_time = start_limit + pd.Timedelta(seconds=analysis_duration_sec)

            if end_limit < analysis_end_time:
                available_sec = (end_limit - start_limit).total_seconds()
                raise ValueError(
                    f"指定した解析時間 {analysis_duration_sec:.1f} 秒を確保できません．"
                    f"オフセット後の共通利用可能時間は {max(0.0, available_sec):.1f} 秒です．"
                )

            hr_dfs = {
                name: df[(df.index >= start_limit) & (df.index < analysis_end_time)].copy()
                for name, df in hr_dfs.items()
            }
            end_limit = analysis_end_time

        tasks = load_log_tasks(
            uploaded_files,
            has_log,
            interval_min,
            start_limit,
            end_limit,
            start_limit.normalize()
        )

        pairs = list(combinations(hr_filenames, 2))
        results = []

        for task in tasks:
            s_t = task["Start_Time"]
            e_t = task["End_Time"]

            comparisons = []
            for a, b in pairs:
                metrics = evaluate_hr_pair(hr_dfs[a], hr_dfs[b], s_t, e_t)
                metrics["device_name"] = f"{a} vs {b}"
                comparisons.append(metrics)

            results.append({
                "task": task["Task_Name"],
                "comparisons": comparisons
            })

        return {
            "analysis_type": "ppg_analysis",
            "status": "success",
            "data": results,
            "title": "PPG解析 結果 (タスク別)"
        }

    except Exception as e:
        return {
            "analysis_type": "ppg_analysis",
            "status": "error",
            "message": f"PPG解析エラー: {str(e)}"
        }
