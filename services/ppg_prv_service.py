"""Task-bounded PPG-derived PRV analysis in fixed windows."""
import re

import numpy as np
import pandas as pd
from scipy.integrate import trapezoid
from scipy.interpolate import interp1d
from scipy.signal import butter, find_peaks, sosfiltfilt, welch

from services.log_service import load_log_tasks
from services.ppg_service import (
    estimate_hr_and_waveform,
    load_ppg_wave_csv,
    resolve_ppg_wave_files,
)


WINDOW_SEC = 30
SHORT_PPI_LIMIT_SEC = 30
PPG_FREQ_BAND = (0.5, 2.5)  # 30–150 bpm
PPI_BOUNDS_SEC = (0.4, 2.0)  # 30–150 bpm
QUALITY_ACCEPT = 0.90
QUALITY_WARN = 0.80


def _sampling_rate(frame):
    times = _times_seconds(frame["RecvJST"])
    differences = np.diff(times)
    positive = differences[differences > 0]
    if not len(positive):
        raise ValueError("サンプル時刻からサンプリング周波数を推定できません")
    return float(1.0 / np.median(positive))


def _epoch_seconds(timestamp):
    """Keep naive timestamps aligned with pandas' int64 epoch values."""
    return float(pd.Timestamp(timestamp).value / 1e9)


def _times_seconds(series):
    """Normalize pandas datetime64 ns/us/ms storage to epoch seconds."""
    values = series.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    return values.astype(float) / 1e9


def _filter_signal(values, fs, low_hz, high_hz):
    values = np.asarray(values, dtype=float).copy()
    if len(values) < max(20, int(fs * 2)) or not np.isfinite(values).any():
        return None
    values = pd.Series(values).interpolate(limit_direction="both").to_numpy(copy=True)
    values -= np.mean(values)
    high_hz = min(high_hz, fs * 0.45)
    if high_hz <= low_hz:
        return None
    try:
        sos = butter(3, (low_hz, high_hz), btype="bandpass", fs=fs, output="sos")
        return sosfiltfilt(sos, values)
    except (ValueError, FloatingPointError):
        return None


def _spectrum_metrics(signal, fs):
    if signal is None or len(signal) < int(fs * 9):
        return {"hr_bpm": None, "valid": False, "peak_ratio": None,
                "peak_mean_ratio": None, "peak_median_ratio": None}
    frequencies, power = welch(signal, fs=fs, nperseg=min(len(signal), int(fs * 10)))
    mask = (frequencies >= PPG_FREQ_BAND[0]) & (frequencies <= PPG_FREQ_BAND[1])
    band_freqs, band_power = frequencies[mask], power[mask]
    if len(band_power) < 4 or not np.isfinite(band_power).all():
        return {"hr_bpm": None, "valid": False, "peak_ratio": None,
                "peak_mean_ratio": None, "peak_median_ratio": None}
    local_peaks, _ = find_peaks(band_power)
    peak_idx = int(local_peaks[np.argmax(band_power[local_peaks])]) if len(local_peaks) else int(np.argmax(band_power))
    peak_power = float(band_power[peak_idx])
    peak_hz = float(band_freqs[peak_idx])
    other_peaks = [idx for idx in local_peaks if abs(band_freqs[idx] - peak_hz) >= 0.2]
    if other_peaks:
        second_power = float(np.max(band_power[other_peaks]))
    else:
        other_bins = np.abs(band_freqs - peak_hz) >= 0.2
        second_power = float(np.max(band_power[other_bins])) if np.any(other_bins) else 0.0
    peak_ratio = np.sqrt(peak_power / max(second_power, np.finfo(float).tiny))
    mean_ratio = peak_power / max(float(np.mean(band_power)), np.finfo(float).tiny)
    median_ratio = peak_power / max(float(np.median(band_power)), np.finfo(float).tiny)
    valid = peak_ratio >= 2 and mean_ratio >= 2 and median_ratio >= 2
    return {
        "hr_bpm": peak_hz * 60.0,
        "valid": bool(valid),
        "peak_ratio": float(peak_ratio),
        "peak_mean_ratio": float(mean_ratio),
        "peak_median_ratio": float(median_ratio),
    }


def _accel_components(frame, fs):
    cols = ["Accel_X_mg", "Accel_Y_mg", "Accel_Z_mg"]
    if not all(col in frame.columns for col in cols):
        return None
    axes = []
    high_hz = min(10.0, fs * 0.45)
    for col in cols:
        axis = _filter_signal(frame[col].to_numpy(dtype=float) / 1000.0, fs, 0.5, high_hz)
        if axis is None:
            return None
        axes.append(axis)
    return np.sqrt(np.sum(np.square(axes), axis=0))


def _accel_rms(values):
    if values is None or len(values) == 0:
        return None
    return float(np.sqrt(np.mean(np.square(values))))


def _mean_valid_hr(frame):
    if "HR_BPM" not in frame.columns:
        return None
    values = pd.to_numeric(frame["HR_BPM"], errors="coerce").to_numpy(dtype=float)
    valid = values[np.isfinite(values) & (values >= 30.0) & (values <= 220.0)]
    return float(np.mean(valid)) if len(valid) else None


def _dominant_frequency(values, fs, low_hz=0.5, high_hz=10.0):
    if values is None or len(values) < int(fs * 2):
        return None
    frequencies, power = welch(values, fs=fs, nperseg=min(len(values), int(fs * 10)))
    band = (frequencies >= low_hz) & (frequencies <= min(high_hz, fs * 0.45))
    return float(frequencies[band][np.argmax(power[band])]) if np.any(band) else None


def _analyse_prv(frame, fs):
    signal = _filter_signal(frame["IR_Value"].to_numpy(dtype=float), fs, 0.5, 4.0)
    if signal is None:
        return {"ppi_count": 0, "valid_ppi_pct": 0.0, "mean_ppi_ms": None,
                "mean_hr_bpm": None, "rmssd_ms": None, "sdnn_ms": None,
                "pppi50_pct": None,
                "_ppi_times": None, "_ppi_values": None}
    distance = max(1, int(round(fs * PPI_BOUNDS_SEC[0])))
    prominence = max(float(np.std(signal) * 0.25), 1e-9)
    peaks, _ = find_peaks(signal, distance=distance, prominence=prominence)
    time_sec = _times_seconds(frame["RecvJST"])
    all_ppi = np.diff(time_sec[peaks])
    valid_mask = (all_ppi >= PPI_BOUNDS_SEC[0]) & (all_ppi <= PPI_BOUNDS_SEC[1])
    ppi = all_ppi[valid_mask]
    valid_pct = float(np.mean(valid_mask) * 100) if len(all_ppi) else 0.0
    adjacent = valid_mask[:-1] & valid_mask[1:] if len(valid_mask) > 1 else np.array([], dtype=bool)
    differences = np.abs(np.diff(all_ppi))[adjacent]
    rmssd = float(np.sqrt(np.mean(np.square(np.diff(all_ppi)[adjacent]))) * 1000) if len(differences) else None
    sdnn = float(np.std(ppi, ddof=1) * 1000) if len(ppi) > 1 else None
    pppi50 = float(np.mean(differences > 0.05) * 100) if len(differences) else None
    ppi_times = time_sec[peaks][1:][valid_mask] if len(ppi) else None
    return {
        "ppi_count": int(len(ppi)),
        "valid_ppi_pct": valid_pct,
        "mean_ppi_ms": float(np.mean(ppi) * 1000) if len(ppi) else None,
        "mean_hr_bpm": float(60.0 / np.mean(ppi)) if len(ppi) else None,
        "rmssd_ms": rmssd,
        "sdnn_ms": sdnn,
        "pppi50_pct": pppi50,
        "_ppi_times": ppi_times,
        "_ppi_values": ppi,
    }


def _spectral_hrv(prv_metrics, segment_start_epoch):
    times, ppi = prv_metrics.get("_ppi_times"), prv_metrics.get("_ppi_values")
    if times is None or ppi is None or len(ppi) < 30:
        return None, None, None, "有効なPPIが不足しています"
    relative = times - segment_start_epoch
    if relative[-1] - relative[0] < 290:
        return None, None, None, "有効なPPIが5分未満です"
    uniform_t = np.arange(relative[0], relative[-1], 0.25)
    if len(uniform_t) < 100:
        return None, None, None, "補間後のPPIデータが不足しています"
    series = interp1d(relative, ppi, kind="linear", bounds_error=False,
                      fill_value="extrapolate")(uniform_t)
    series -= np.mean(series)
    freqs, power = welch(series, fs=4.0, nperseg=min(512, len(series)))
    lf_mask = (freqs >= 0.04) & (freqs < 0.15)
    hf_mask = (freqs >= 0.15) & (freqs <= 0.40)
    lf = float(trapezoid(power[lf_mask], freqs[lf_mask])) if np.sum(lf_mask) > 1 else None
    hf = float(trapezoid(power[hf_mask], freqs[hf_mask])) if np.sum(hf_mask) > 1 else None
    ratio = float(lf / hf) if lf is not None and hf is not None and hf > 0 else None
    return lf, hf, ratio, "計算済み" if ratio is not None else "LF/HF帯域のパワーを算出できません"


def _quality_status(spectral_ratio, ppi_ratio):
    spectral_ratio = float(spectral_ratio or 0.0)
    ppi_ratio = float(ppi_ratio or 0.0)
    if spectral_ratio >= QUALITY_ACCEPT and ppi_ratio >= QUALITY_ACCEPT:
        return "採用"
    if spectral_ratio >= QUALITY_WARN and ppi_ratio >= QUALITY_WARN:
        return "注意付き採用"
    return "除外"


def _file_segments(uploaded_files, filename, frame, has_log, interval_min,
                   analysis_start_offset_sec, analysis_duration_sec):
    first = frame["RecvJST"].iloc[0]
    last = frame["RecvJST"].iloc[-1]
    positive = frame["RecvJST"].diff().dt.total_seconds()
    positive = positive[positive > 0]
    sample_period = float(positive.median()) if not positive.empty else 0.01
    end_exclusive = last + pd.Timedelta(seconds=sample_period)
    if has_log:
        tasks = load_log_tasks(uploaded_files, True, interval_min, first,
                               end_exclusive, first.normalize())
        segments = [(str(task["Task_Name"]), max(task["Start_Time"], first),
                     min(task["End_Time"], end_exclusive)) for task in tasks]
        return [(name, start, end) for name, start, end in segments if start < end]
    if float(interval_min) <= 0:
        raise ValueError("区切り分数には1以上を指定してください")
    start = first + pd.Timedelta(seconds=float(analysis_start_offset_sec or 0))
    end = end_exclusive
    if float(analysis_duration_sec or 0) > 0:
        requested_end = start + pd.Timedelta(seconds=float(analysis_duration_sec))
        if requested_end > end:
            raise ValueError(f"{filename} は指定した解析時間を確保できません")
        end = requested_end
    if start >= end:
        raise ValueError(f"{filename} は開始オフセット後に解析できるデータがありません")
    segments, segment_start, index = [], start, 1
    group_duration = pd.Timedelta(minutes=float(interval_min))
    while segment_start < end:
        segment_end = min(segment_start + group_duration, end)
        segments.append((f"区間{index}", segment_start, segment_end))
        segment_start, index = segment_end, index + 1
    return segments


def _segment_rows(frame, task, task_start, task_end, filename, acc_threshold):
    rows = []
    cursor = task_start
    index = 1
    while cursor < task_end:
        end = min(cursor + pd.Timedelta(seconds=WINDOW_SEC), task_end)
        segment = frame[(frame["RecvJST"] >= cursor) & (frame["RecvJST"] < end)].copy()
        duration = (end - cursor).total_seconds()
        row = {
            "filename": filename, "task": task,
            "task_start_time": pd.Timestamp(task_start).isoformat(),
            "task_end_time": pd.Timestamp(task_end).isoformat(),
            "window_kind": "30秒" if duration >= WINDOW_SEC else "短区間",
            "window_index": index,
            "start_time": cursor.isoformat(), "end_time": end.isoformat(),
            "sample_count": int(len(segment)), "duration_sec": float(duration),
            "hr_bpm": _mean_valid_hr(segment),
            "paired_filename": None, "right_minus_left": None,
            "hr_jump_count": 0, "hr_continuity_warning": False,
            "lf_power": None, "hf_power": None, "lf_hf": None,
            "frequency_status": "5分窓ではないため算出対象外",
        }
        if len(segment) >= 20:
            fs = _sampling_rate(segment)
            ppg_filtered = _filter_signal(segment["IR_Value"].to_numpy(dtype=float), fs, 0.5, 2.5)
            accel = _accel_components(segment, fs)
            times = _times_seconds(segment["RecvJST"])
            local_start = times[0]
            spectral = []
            offset = 0.0
            while offset + 10.0 <= duration + 1e-6:
                mask = (times >= local_start + offset) & (times < local_start + offset + 10.0)
                signal_window = ppg_filtered[mask] if ppg_filtered is not None else None
                measure = _spectrum_metrics(signal_window, fs)
                measure["start_offset_sec"] = offset
                if accel is not None:
                    acc_window = accel[mask]
                    measure["accel_rms_g"] = _accel_rms(acc_window)
                    if signal_window is not None and len(signal_window) >= int(fs * 9):
                        motion_hz = _dominant_frequency(acc_window, fs)
                        hr_hz = measure["hr_bpm"] / 60 if measure["hr_bpm"] is not None else None
                        measure["motion_hz"] = motion_hz
                        measure["ppg_acc_overlap"] = bool(
                            motion_hz is not None and hr_hz is not None
                            and (abs(motion_hz - hr_hz) <= 0.1 or abs(motion_hz - 2 * hr_hz) <= 0.1)
                        )
                    else:
                        measure["motion_hz"], measure["ppg_acc_overlap"] = None, None
                else:
                    measure["accel_rms_g"], measure["motion_hz"], measure["ppg_acc_overlap"] = None, None, None
                spectral.append(measure)
                offset += 5.0
            valid_spectral = [item for item in spectral if item["valid"]]
            hr_values = [item["hr_bpm"] for item in spectral if item["hr_bpm"] is not None]
            hr_jump_count = int(np.sum(np.abs(np.diff(hr_values)) > 20)) if len(hr_values) > 1 else 0
            spectral_ratio = len(valid_spectral) / len(spectral) if spectral else 0.0
            row.update({
                "spectral_window_count": len(spectral),
                "valid_spectral_window_count": len(valid_spectral),
                "valid_spectral_pct": spectral_ratio * 100,
                "spectral_hr_bpm": float(np.median(hr_values)) if hr_values else None,
                "hr_jump_count": hr_jump_count,
                "hr_continuity_warning": hr_jump_count > 0,
                "ppg_peak_ratio_median": float(np.median([x["peak_ratio"] for x in valid_spectral])) if valid_spectral else None,
                "accel_rms_g": _accel_rms(accel),
                "accel_dominant_hz": float(np.median([x["motion_hz"] for x in spectral if x.get("motion_hz") is not None]))
                    if any(x.get("motion_hz") is not None for x in spectral) else None,
                "ppg_acc_overlap_pct": float(np.mean([x["ppg_acc_overlap"] for x in spectral if x["ppg_acc_overlap"] is not None]) * 100)
                    if any(x["ppg_acc_overlap"] is not None for x in spectral) else None,
                "low_motion_pct": float(np.mean([x["accel_rms_g"] <= acc_threshold for x in spectral if x["accel_rms_g"] is not None]) * 100)
                    if acc_threshold is not None and any(x["accel_rms_g"] is not None for x in spectral) else None,
            })
            if duration >= SHORT_PPI_LIMIT_SEC:
                prv = _analyse_prv(segment, fs)
                ppi_ratio = (prv["valid_ppi_pct"] or 0.0) / 100
                status = _quality_status(spectral_ratio, ppi_ratio)
                row.update({key: value for key, value in prv.items() if not key.startswith("_")})
                row["quality_status"] = status
                row["status"] = "success" if status != "除外" else "quality_rejected"
                row["message"] = None if status != "除外" else "PPG品質または生理的PPI率が暫定基準を下回りました"
            else:
                row.update({"quality_status": "短区間", "status": "spectral_only",
                            "message": "30秒未満のためPRV指標は算出しません",
                            "ppi_count": None, "valid_ppi_pct": None, "mean_ppi_ms": None,
                            "mean_hr_bpm": None, "rmssd_ms": None, "sdnn_ms": None,
                            "pppi50_pct": None,
                            "nn50": None, "pnn50": None})
        else:
            row.update({"quality_status": "除外", "status": "error",
                        "message": "解析対象サンプルが不足しています", "spectral_window_count": 0,
                        "valid_spectral_window_count": 0, "valid_spectral_pct": 0.0,
                        "spectral_hr_bpm": None, "ppi_count": 0, "valid_ppi_pct": 0.0,
                        "mean_ppi_ms": None, "mean_hr_bpm": None,
                        "rmssd_ms": None, "sdnn_ms": None, "pppi50_pct": None,
                        "nn50": None, "pnn50": None,
                        "accel_rms_g": None, "ppg_acc_overlap_pct": None, "low_motion_pct": None})
        rows.append(row)
        cursor, index = end, index + 1
    return rows


def _five_minute_rows(frame, segments, filename, acc_threshold):
    rows = []
    for task, task_start, task_end in segments:
        cursor, index = task_start, 1
        while cursor + pd.Timedelta(minutes=5) <= task_end:
            end = cursor + pd.Timedelta(minutes=5)
            segment = frame[(frame["RecvJST"] >= cursor) & (frame["RecvJST"] < end)].copy()
            if len(segment) >= 100:
                fs = _sampling_rate(segment)
                ppg = _filter_signal(segment["IR_Value"].to_numpy(dtype=float), fs, 0.5, 2.5)
                accel = _accel_components(segment, fs)
                times = _times_seconds(segment["RecvJST"])
                spectra, acc_windows, acc_freqs, overlaps = [], [], [], []
                for offset in np.arange(0, 291, 5):
                    mask = (times >= times[0] + offset) & (times < times[0] + offset + 10)
                    measure = _spectrum_metrics(ppg[mask] if ppg is not None else None, fs)
                    spectra.append(measure)
                    if accel is not None:
                        acc_window = accel[mask]
                        acc_windows.append(_accel_rms(acc_window))
                        motion_hz = _dominant_frequency(acc_window, fs)
                        if motion_hz is not None:
                            acc_freqs.append(motion_hz)
                        hr_hz = measure["hr_bpm"] / 60 if measure["hr_bpm"] is not None else None
                        if hr_hz is not None and motion_hz is not None:
                            overlaps.append(abs(motion_hz - hr_hz) <= 0.1 or abs(motion_hz - 2 * hr_hz) <= 0.1)
                spectral_ratio = np.mean([x["valid"] for x in spectra]) if spectra else 0.0
                prv = _analyse_prv(segment, fs)
                ppi_ratio = (prv["valid_ppi_pct"] or 0.0) / 100
                quality = _quality_status(spectral_ratio, ppi_ratio)
                low_motion_pct = (float(np.mean([v <= acc_threshold for v in acc_windows if v is not None]) * 100)
                                  if acc_threshold is not None and any(v is not None for v in acc_windows) else None)
                lf = hf = ratio = None
                if quality != "採用":
                    freq_status = "PPG品質が採用基準未満のためLF/HFを抑制"
                elif accel is None:
                    freq_status = "ACC列がないためLF/HFを抑制"
                elif low_motion_pct is None or low_motion_pct < 80:
                    freq_status = "低体動窓が80%未満のためLF/HFを抑制"
                else:
                    lf, hf, ratio, freq_status = _spectral_hrv(prv, times[0])
                rows.append({
                    "filename": filename, "task": task, "window_kind": "5分",
                    "window_index": index, "start_time": cursor.isoformat(),
                    "end_time": end.isoformat(), "duration_sec": 300,
                    "sample_count": len(segment), "quality_status": quality,
                    "status": "success" if quality != "除外" else "quality_rejected",
                    "spectral_window_count": len(spectra),
                    "valid_spectral_window_count": int(np.sum([x["valid"] for x in spectra])),
                    "valid_spectral_pct": float(spectral_ratio * 100),
                    "valid_ppi_pct": prv["valid_ppi_pct"],
                    "ppi_count": prv["ppi_count"], "mean_ppi_ms": prv["mean_ppi_ms"],
                    "mean_hr_bpm": prv["mean_hr_bpm"], "rmssd_ms": prv["rmssd_ms"],
                    "hr_jump_count": int(np.sum(np.abs(np.diff([x["hr_bpm"] for x in spectra if x["hr_bpm"] is not None])) > 20))
                        if sum(x["hr_bpm"] is not None for x in spectra) > 1 else 0,
                    "hr_continuity_warning": any(
                        abs(b - a) > 20 for a, b in zip(
                            [x["hr_bpm"] for x in spectra if x["hr_bpm"] is not None],
                            [x["hr_bpm"] for x in spectra if x["hr_bpm"] is not None][1:]
                        )
                    ),
                    "pppi50_pct": prv["pppi50_pct"], "spectral_hr_bpm": None,
                    "accel_rms_g": _accel_rms(accel), "low_motion_pct": low_motion_pct,
                    "accel_dominant_hz": float(np.median(acc_freqs)) if acc_freqs else None,
                    "ppg_acc_overlap_pct": float(np.mean(overlaps) * 100) if overlaps else None,
                    "lf_power": lf, "hf_power": hf,
                    "lf_hf": ratio, "frequency_status": freq_status,
                    "paired_filename": None, "right_minus_left": None,
                })
            cursor, index = end, index + 1
    return rows


def _bilateral_pairs(filenames):
    pairs = {}
    for filename in filenames:
        stem = filename.rsplit(".", 1)[0]
        match = re.search(r"(?<![A-Za-z0-9])(left|right|l|r)(\d*)(?![A-Za-z0-9])", stem, re.I)
        if not match:
            continue
        side = "L" if match.group(1).lower() in {"l", "left"} else "R"
        identity = stem[:match.start()] + "SIDE" + match.group(2) + stem[match.end():]
        pairs.setdefault(identity.casefold(), {})[side] = filename
    return [(sides["L"], sides["R"]) for sides in pairs.values() if "L" in sides and "R" in sides]


def _attach_bilateral_deltas(rows, filenames):
    by_file = {name: {} for name in filenames}
    for row in rows:
        if row.get("window_kind") not in {"30秒", "5分"}:
            continue
        key = (row["task"], row["window_kind"], row["start_time"], row["end_time"])
        by_file.setdefault(row["filename"], {})[key] = row
    metrics = ("mean_ppi_ms", "mean_hr_bpm", "rmssd_ms", "pppi50_pct")
    for left, right in _bilateral_pairs(filenames):
        for key in by_file.get(left, {}).keys() & by_file.get(right, {}).keys():
            lrow, rrow = by_file[left][key], by_file[right][key]
            if lrow.get("quality_status") not in {"採用", "注意付き採用"} or rrow.get("quality_status") not in {"採用", "注意付き採用"}:
                continue
            delta = {metric: (rrow.get(metric) - lrow.get(metric)
                              if rrow.get(metric) is not None and lrow.get(metric) is not None else None)
                     for metric in metrics}
            lrow["paired_filename"], rrow["paired_filename"] = right, left
            lrow["right_minus_left"] = delta
            rrow["right_minus_left"] = delta


def _task_summary_rows(rows):
    """Summarize accepted 30-second windows as per-task arithmetic means."""
    grouped = {}
    for row in rows:
        key = (
            row.get("filename"), row.get("task"),
            row.get("task_start_time", row.get("start_time")),
            row.get("task_end_time", row.get("end_time")),
        )
        grouped.setdefault(key, []).append(row)

    summaries = []
    for (filename, task, task_start, task_end), task_rows in grouped.items():
        windows = [row for row in task_rows if row.get("window_kind") == "30秒"]
        included = [
            row for row in windows
            if row.get("quality_status") in {"採用", "注意付き採用"}
        ]
        summary = {
            "filename": filename,
            "task": task,
            "start_time": task_start,
            "end_time": task_end,
            "window_count": len(windows),
            "included_window_count": len(included),
            "excluded_window_count": len(windows) - len(included),
        }
        for metric in ("hr_bpm", "rmssd_ms", "sdnn_ms", "pppi50_pct"):
            values = [
                float(row[metric]) for row in included
                if row.get(metric) is not None
                and np.isfinite(float(row[metric]))
            ]
            summary[f"mean_{metric}"] = float(np.mean(values)) if values else None
            summary[f"{metric}_count"] = len(values)
        summaries.append(summary)

    return sorted(
        summaries,
        key=lambda row: (str(row["filename"]), str(row["start_time"])),
    )


def perform_ppg_wave_hrv_analysis(uploaded_files, has_log, interval_min,
                                  analysis_start_offset_sec=0, analysis_duration_sec=0):
    try:
        filenames = resolve_ppg_wave_files(uploaded_files)
        rows = []
        for filename in filenames:
            frame = load_ppg_wave_csv(uploaded_files[filename], filename=filename)
            frame = frame.drop_duplicates(subset=["RecvJST"], keep="first").reset_index(drop=True)
            if "HR_BPM" not in frame.columns:
                frame["HR_BPM"] = estimate_hr_and_waveform(frame, fs=_sampling_rate(frame))
            segments = _file_segments(uploaded_files, filename, frame, has_log, interval_min,
                                      analysis_start_offset_sec, analysis_duration_sec)
            if not segments:
                raise ValueError(f"{filename} の解析時間に該当するログタスクがありません")
            # P25 is a conservative, file-relative threshold; windows scored below never cross task boundaries.
            rms_values = []
            fs = _sampling_rate(frame)
            full_acc = _accel_components(frame, fs)
            if full_acc is not None:
                all_times = _times_seconds(frame["RecvJST"])
                for _, start, end in segments:
                    start_epoch, end_epoch = _epoch_seconds(start), _epoch_seconds(end)
                    offset = 0.0
                    while start_epoch + offset + 10 <= end_epoch:
                        mask = (all_times >= start_epoch + offset) & (all_times < start_epoch + offset + 10)
                        value = _accel_rms(full_acc[mask])
                        if value is not None:
                            rms_values.append(value)
                        offset += 5.0
            acc_threshold = float(np.percentile(rms_values, 25)) if rms_values else None
            for task, start, end in segments:
                rows.extend(_segment_rows(frame, task, start, end, filename, acc_threshold))
        _attach_bilateral_deltas(rows, filenames)
        return {"analysis_type": "ppg_hr_analysis", "status": "success",
                "title": "PPG脈波解析結果（HR・PRV）", "data": rows,
                "task_summary": _task_summary_rows(rows)}
    except Exception as error:
        return {"analysis_type": "ppg_hr_analysis", "status": "error",
                "message": f"PPG脈波解析エラー: {str(error)}"}
