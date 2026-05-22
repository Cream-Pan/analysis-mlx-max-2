import io
import re
import pandas as pd
import numpy as np

from scipy.signal import detrend, get_window, find_peaks, welch
from scipy.interpolate import interp1d
from scipy.integrate import trapezoid
from itertools import combinations

from services.common import config, load_log_tasks
from services.hr_compare_service import evaluate_hr_pair

def _parse_datetime_series(series):
    """CSV に ="..." 形式の時刻が混ざっていても datetime 化する。"""
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace('="', '', regex=False)
        .str.replace('"', '', regex=False)
    )
    return pd.to_datetime(cleaned, errors="coerce")

def load_ppg_hr_csv(f_obj):
    hr_cfg = config["ppg_columns"]["hr_csv"]
    time_col = hr_cfg["time"]
    hr_col = hr_cfg["hr"]

    df = pd.read_csv(
        io.BytesIO(f_obj.read()),
        usecols=[time_col, hr_col]
    )
    f_obj.seek(0)

    df[time_col] = _parse_datetime_series(df[time_col])
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

    df = pd.read_csv(io.BytesIO(f_obj.read()), usecols=usecols)
    f_obj.seek(0)

    df[time_col] = _parse_datetime_series(df[time_col])
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

    df = pd.read_csv(
        io.BytesIO(f_obj.read()),
        usecols=[time_col, ir_col]
    )
    f_obj.seek(0)

    df[time_col] = _parse_datetime_series(df[time_col])
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
            header_df = pd.read_csv(io.BytesIO(f.read()), nrows=0)
            f.seek(0)
        except Exception:
            f.seek(0)
            continue

        cols = set(header_df.columns.tolist())
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
            header_df = pd.read_csv(io.BytesIO(f.read()), nrows=0)
            f.seek(0)
        except Exception:
            f.seek(0)
            continue

        cols = set(header_df.columns.tolist())
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
            header_df = pd.read_csv(io.BytesIO(f.read()), nrows=0)
            f.seek(0)
        except Exception:
            f.seek(0)
            continue

        cols = set(header_df.columns.tolist())
        if {time_col, ir_col}.issubset(cols):
            matched.append(filename)

    if len(matched) < 1:
        raise ValueError("PPG脈波解析には RecvJST と IR_Value を含む CSV が 1 つ以上必要です")

    return matched

def estimate_hr_and_waveform(df, fs=100):
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
    
    hr_times = [] # 実時間 (UNIX Time Float)
    hr_values = [] # 推定された心拍数（BPM）を格納するリスト
    
    last_valid_bpm = None
    time_since_last_valid = 0.0
    
    debug_counts = {"Tracking": 0, "Reset": 0, "Lost": 0, "HarmonicFix": 0}

    # --- 2. FFT解析ループ ---
    for i in range(0, N - window_samples + 1, step_samples):
        segment = raw_sig[i : i + window_samples]
        segment_detrend = detrend(segment)
        
        window_func = get_window('hann', len(segment_detrend))
        segment_windowed = segment_detrend * window_func
        
        # FFT（元コードと完全一致: ゼロパディングしない）
        fft_spectrum = np.fft.rfft(segment_windowed)
        fft_freqs = np.fft.rfftfreq(len(segment_windowed), d=1/fs)
        fft_mag = np.abs(fft_spectrum)
        
        roi_idx = np.where((fft_freqs >= FREQ_MIN) & (fft_freqs <= FREQ_MAX))[0]
        
        # 【改善4】 時間軸の記録 (ウィンドウ中心時刻)
        center_idx = i + window_samples // 2
        center_time = timestamps_float[center_idx]
        hr_times.append(center_time)

        if len(roi_idx) == 0:
            hr_values.append(np.nan)
            continue

        # --- ピーク検出 (with Width Constraint for Q-factor) ---
        mag_roi = fft_mag[roi_idx]
        freqs_roi = fft_freqs[roi_idx]
        
        # width制限: 鋭いピークのみ候補にする
        max_width_samples = int(MAX_PEAK_WIDTH_HZ / (fs/window_samples)) # Hz -> bins
        peak_idxs_local, props = find_peaks(mag_roi, height=0, width=(None, max_width_samples))
        
        if len(peak_idxs_local) == 0:
            # 鋭いピークがないなら、条件を緩めて再トライ（完全にロストするよりマシ）
            peak_idxs_local, props = find_peaks(mag_roi, height=0)
            if len(peak_idxs_local) == 0:
                hr_values.append(np.nan)
                time_since_last_valid += step_sec
                continue
            
        candidate_freqs = freqs_roi[peak_idxs_local]
        candidate_bpms = candidate_freqs * 60.0
        candidate_mags = mag_roi[peak_idxs_local]
        
        selected_bpm = None
        selection_mode = "Global"
        
        # 1. トラッキングモード ±20BPM
        if (last_valid_bpm is not None) and (time_since_last_valid < LOST_RESET_SEC):
            min_bpm = last_valid_bpm - SEARCH_WINDOW_BPM
            max_bpm = last_valid_bpm + SEARCH_WINDOW_BPM
            mask_track = (candidate_bpms >= min_bpm) & (candidate_bpms <= max_bpm)
            
            if np.any(mask_track):
                inds_track = np.where(mask_track)[0]
                best_idx_local = inds_track[np.argmax(candidate_mags[inds_track])]
                selected_bpm = candidate_bpms[best_idx_local]
                selected_mag = candidate_mags[best_idx_local]
                selection_mode = "Tracking"
            else:
                selected_bpm = None
        
        # 2. グローバルサーチ
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

        # --- 最終判定 (Ratio Check) ---
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
            
            if selection_mode == "Tracking": debug_counts["Tracking"] += 1
            else: debug_counts["Reset"] += 1
        else:
            hr_values.append(np.nan)
            time_since_last_valid += step_sec
            debug_counts["Lost"] += 1

    print(f"  [Debug] Tracked: {debug_counts['Tracking']}, Reset: {debug_counts['Reset']}, Lost: {debug_counts['Lost']}, HarmonicFix: {debug_counts['HarmonicFix']}")

    # --- 3. 【改善4】 時間軸ベースの補間 ---
    hr_times = np.array(hr_times)
    hr_values = np.array(hr_values)
    valid_mask = ~np.isnan(hr_values)
    
    # 全期間のタイムスタンプ配列を作成
    full_times = timestamps_float
    
    if np.sum(valid_mask) > 1:
        f_interp = interp1d(
            hr_times[valid_mask], 
            hr_values[valid_mask], 
            kind='linear', 
            bounds_error=False, 
            fill_value="extrapolate"
        )
        hr_output_full = f_interp(full_times)
        hr_output_full = np.clip(hr_output_full, 30, 220) # Clip範囲も拡大
    else:
        hr_output_full = np.full(N, np.nan)

    return hr_output_full

def process_ppg_to_hr(uploaded_files, has_log, interval_min, analysis_start_offset_sec=0, analysis_duration_sec=0):
    try:
        raw_filename = resolve_ppg_raw_file(uploaded_files)
        df = load_ppg_raw_csv(uploaded_files[raw_filename])

        # 旧版 load_ppg_raw_csv との互換用。修正版では RecvJST は列として返る。
        if "RecvJST" not in df.columns:
            df = df.reset_index().rename(columns={"index": "RecvJST"})

        # 解析開始オフセット適用
        analysis_start_time = df["RecvJST"].min() + pd.Timedelta(seconds=analysis_start_offset_sec)

        if analysis_duration_sec > 0:
            analysis_end_time = analysis_start_time + pd.Timedelta(seconds=analysis_duration_sec)

            if df["RecvJST"].max() < analysis_end_time:
                available_sec = (df["RecvJST"].max() - analysis_start_time).total_seconds()
                raise ValueError(
                    f"指定した解析時間 {analysis_duration_sec:.1f} 秒を確保できません．"
                    f"オフセット後に利用可能なのは {max(0.0, available_sec):.1f} 秒です．"
                )

            df = df[(df["RecvJST"] >= analysis_start_time) & (df["RecvJST"] < analysis_end_time)].copy()
        else:
            df = df[df["RecvJST"] >= analysis_start_time].copy()

        if len(df) < 2:
            raise ValueError("解析対象データが不足しています")

        # Fs 推定（元コードと同じく、先頭1000点の RecvJST 差分から推定）
        mean_dt = df["RecvJST"].head(1000).diff().dt.total_seconds().mean()
        estimated_fs = round(1 / mean_dt) if pd.notna(mean_dt) and mean_dt > 0 else 100

        # 注意: HR推定前に IR/RED を ffill/bfill しない。
        # 元コードは estimate_hr_and_waveform() 内で IR の NaN だけ平均値補完する。

        # 全体相関係数
        overall_corr = df["IR_Value"].corr(df["RED_Value"])

        # 移動相関係数
        window_size = int(estimated_fs * 1.0)
        if window_size < 1:
            window_size = 1
        df["Rolling_Corr"] = df["IR_Value"].rolling(window=window_size).corr(df["RED_Value"])

        # HR 推定
        hr_bpm = estimate_hr_and_waveform(df, fs=estimated_fs)
        df["HR_BPM"] = hr_bpm

        # 時間軸を index にして区間作成
        df_plot = df.set_index("RecvJST").sort_index()

        if has_log:
            task_segments = load_log_tasks(
                uploaded_files,
                has_log,
                interval_min,
                df_plot.index.min(),
                df_plot.index.max(),
                df_plot.index.min().normalize()
            )
        else:
            task_segments = [
                {
                    "Task_Name": "解析区間",
                    "Start_Time": df_plot.index.min(),
                    "End_Time": df_plot.index.max()
                }
            ]

        # ダウンロード用CSV
        output_df = df.copy()
        csv_text = output_df.to_csv(index=False)

        return {
            "analysis_type": "ppg_to_hr",
            "status": "success",
            "title": f"PPG→HR変換 結果 ({raw_filename})",
            "summary": {
                "fs": int(estimated_fs),
                "overall_corr": None if pd.isna(overall_corr) else float(overall_corr)
            },
            "task_segments": [
                {
                    "title": seg["Task_Name"],
                    "start_time": seg["Start_Time"].isoformat(),
                    "end_time": seg["End_Time"].isoformat()
                }
                for seg in task_segments
            ],
            "plot_data": {
                "time": df["RecvJST"].dt.strftime("%Y-%m-%dT%H:%M:%S.%f").tolist(),
                "ir": df["IR_Value"].where(pd.notna(df["IR_Value"]), None).tolist(),
                "hr": pd.Series(df["HR_BPM"]).where(pd.notna(df["HR_BPM"]), None).tolist()
            },
            "download": {
                "filename": f"{raw_filename.rsplit('.', 1)[0]}_HR.csv",
                "csv_text": csv_text
            }
        }

    except Exception as e:
        return {
            "analysis_type": "ppg_to_hr",
            "status": "error",
            "message": f"PPG→HR変換エラー: {str(e)}"
        }
    
def perform_ppg_wave_hrv_analysis(uploaded_files, has_log, interval_min, analysis_start_offset_sec=0, analysis_duration_sec=0):
    try:
        filenames = resolve_ppg_wave_files(uploaded_files)
        results = []

        for filename in filenames:
            df = load_ppg_wave_csv(uploaded_files[filename])

            analysis_start_time = df["RecvJST"].min() + pd.Timedelta(seconds=analysis_start_offset_sec)
            analysis_end_time = analysis_start_time + pd.Timedelta(seconds=analysis_duration_sec)

            if analysis_duration_sec <= 0:
                raise ValueError("PPG脈波解析では解析時間を 0 秒より大きく指定してください")

            if df["RecvJST"].max() < analysis_end_time:
                available_sec = (df["RecvJST"].max() - analysis_start_time).total_seconds()
                raise ValueError(
                    f"{filename} は指定した解析時間 {analysis_duration_sec:.1f} 秒を確保できません．"
                    f"オフセット後に利用可能なのは {max(0.0, available_sec):.1f} 秒です．"
                )

            df = df[(df["RecvJST"] >= analysis_start_time) & (df["RecvJST"] < analysis_end_time)].copy()

            if len(df) < 3:
                raise ValueError(f"{filename} は解析対象データが不足しています")

            time_sec = (df["RecvJST"] - df["RecvJST"].iloc[0]).dt.total_seconds().to_numpy()
            ir = df["IR_Value"].to_numpy()

            mean_dt = np.mean(np.diff(time_sec))
            fs = 1.0 / mean_dt if mean_dt > 0 else 100.0

            # PPG波形の前処理
            ir = ir - np.nanmean(ir)

            # 心拍ピーク検出
            # 0.4秒以上離れたピークのみ採用する．これは最大150 bpm相当
            min_distance = max(1, int(fs * 0.4))
            prominence = max(np.nanstd(ir) * 0.3, 1e-6)

            peaks, _ = find_peaks(
                ir,
                distance=min_distance,
                prominence=prominence
            )

            if len(peaks) < 3:
                raise ValueError(f"{filename} は有効な脈波ピークが不足しています")

            peak_times = time_sec[peaks]
            nn_intervals = np.diff(peak_times)

            # 異常なNN間隔を除外
            # 0.3秒未満: 200 bpm超，2.0秒超: 30 bpm未満
            valid_nn = (nn_intervals >= 0.3) & (nn_intervals <= 2.0)
            nn_intervals = nn_intervals[valid_nn]

            if len(nn_intervals) < 3:
                raise ValueError(f"{filename} は有効なNN間隔が不足しています")

            # PNN50
            nn_diff = np.abs(np.diff(nn_intervals))
            nn50 = int(np.sum(nn_diff > 0.05))
            pnn50 = float(nn50 / len(nn_diff) * 100) if len(nn_diff) > 0 else None

            # LF/HF
            # NN間隔系列を4Hzへ補間してPSD計算
            nn_times = peak_times[1:][valid_nn]
            interp_fs = 4.0

            if len(nn_times) < 4:
                lf_power = None
                hf_power = None
                lf_hf = None
            else:
                uniform_t = np.arange(nn_times[0], nn_times[-1], 1.0 / interp_fs)

                if len(uniform_t) < 8:
                    lf_power = None
                    hf_power = None
                    lf_hf = None
                else:
                    f_interp = interp1d(
                        nn_times,
                        nn_intervals,
                        kind="linear",
                        bounds_error=False,
                        fill_value="extrapolate"
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
                        lf_hf = None

            results.append({
                "filename": filename,
                "start_time": analysis_start_time.isoformat(),
                "end_time": analysis_end_time.isoformat(),
                "fs": float(fs),
                "peak_count": int(len(peaks)),
                "nn_count": int(len(nn_intervals)),
                "mean_nn_ms": float(np.mean(nn_intervals) * 1000),
                "mean_hr_bpm": float(60.0 / np.mean(nn_intervals)),
                "nn50": nn50,
                "pnn50": pnn50,
                "lf_power": lf_power,
                "hf_power": hf_power,
                "lf_hf": lf_hf
            })

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

        if has_log:
            tasks = load_log_tasks(
                uploaded_files,
                has_log,
                interval_min,
                start_limit,
                end_limit,
                start_limit.normalize()
            )
        else:
            tasks = [
                {
                    "Task_Name": "解析区間",
                    "Start_Time": start_limit,
                    "End_Time": end_limit
                }
            ]

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