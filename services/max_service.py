import io
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error

from services.common import config, load_log_tasks


def load_ecg_csv(f_obj):
    ecg_cfg = config["max_columns"]["ecg"]
    time_col = ecg_cfg["time"]
    hr_col = ecg_cfg["hr"]

    df = pd.read_csv(
        io.BytesIO(f_obj.read()),
        usecols=[time_col, hr_col]
    )
    f_obj.seek(0)

    df = df.dropna(subset=[hr_col]).copy()
    cleaned_timestamp = df[time_col].astype(str).str.replace('="', '', regex=False).str.replace('"', '', regex=False)
    df[time_col] = pd.to_datetime(cleaned_timestamp, errors='coerce')
    df[hr_col] = pd.to_numeric(df[hr_col], errors='coerce')
    df = df.dropna(subset=[time_col, hr_col])
    df = df.set_index(time_col).sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df[[hr_col]].rename(columns={hr_col: 'HR'})


def load_ppg_csv(f_obj):
    eval_cfg = config["max_columns"]["ppg_eval"]
    raw_cfg = config["max_columns"]["ppg_raw_csv"]

    time_col = eval_cfg["time"]
    hr_col = eval_cfg["hr"]
    ir_col = raw_cfg["ir"]
    red_col = raw_cfg["red"]
    elapsed_col = raw_cfg["elapsed_ms"]

    usecols = list(dict.fromkeys([
        time_col,
        hr_col,
        ir_col,
        red_col,
        elapsed_col
    ]))

    df = pd.read_csv(
        io.BytesIO(f_obj.read()),
        usecols=usecols
    )
    f_obj.seek(0)

    df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
    df[hr_col] = pd.to_numeric(df[hr_col], errors='coerce')
    df[ir_col] = pd.to_numeric(df[ir_col], errors='coerce')
    df[red_col] = pd.to_numeric(df[red_col], errors='coerce')
    df[elapsed_col] = pd.to_numeric(df[elapsed_col], errors='coerce')

    df = df.dropna(subset=[time_col, hr_col])
    df = df.set_index(time_col).sort_index()
    df = df[~df.index.duplicated(keep='first')]

    return df.rename(columns={
        hr_col: 'HR',
        ir_col: 'IR_Value',
        red_col: 'RED_Value',
        elapsed_col: 'SensorElapsed_ms'
    })


def evaluate_max_device(df_true, df_dev, start_t, end_t):
    try:
        t_sub = df_true.loc[start_t:end_t]
        d_sub = df_dev.loc[start_t:end_t]

        if t_sub.empty or d_sub.empty:
            return {
                "raw_mae": None,
                "raw_rmse": None,
                "raw_count": 0,
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": "データ不足"
            }

        combined_idx = t_sub.index.union(d_sub.index)

        interp_true = (
            t_sub[['HR']]
            .reindex(combined_idx)
            .interpolate(method='time')
            .reindex(d_sub.index)
        )

        comp = pd.DataFrame({
            'true': interp_true['HR'],
            'dev': d_sub['HR']
        }).dropna()

        if comp.empty:
            return {
                "raw_mae": None,
                "raw_rmse": None,
                "raw_count": 0,
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": "同期データなし"
            }

        raw_mae = float(mean_absolute_error(comp['true'], comp['dev']))
        raw_rmse = float(np.sqrt(mean_squared_error(comp['true'], comp['dev'])))

        resampled = comp.resample('1min', origin=start_t).mean().dropna()
        if resampled.empty:
            return {
                "raw_mae": raw_mae,
                "raw_rmse": raw_rmse,
                "raw_count": len(comp),
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": None
            }

        resampled_mae = float(mean_absolute_error(resampled['true'], resampled['dev']))
        resampled_rmse = float(np.sqrt(mean_squared_error(resampled['true'], resampled['dev'])))

        return {
            "raw_mae": raw_mae,
            "raw_rmse": raw_rmse,
            "raw_count": len(comp),
            "resampled_mae": resampled_mae,
            "resampled_rmse": resampled_rmse,
            "resampled_count": len(resampled),
            "error": None
        }

    except Exception as e:
        return {
            "raw_mae": None,
            "raw_rmse": None,
            "raw_count": 0,
            "resampled_mae": None,
            "resampled_rmse": None,
            "resampled_count": 0,
            "error": str(e)
        }


def perform_max_evaluation(uploaded_files, has_log, interval_min):
    try:
        df_ecg = load_ecg_csv(uploaded_files['ecg.csv'])
        df_ppg = load_ppg_csv(uploaded_files['PPG_BPM.csv'])
        df_fin = load_ppg_csv(uploaded_files['PPG_fin_BPM.csv'])

        start_limit = max(df_ecg.index.min(), df_ppg.index.min(), df_fin.index.min())
        end_limit = min(df_ecg.index.max(), df_ppg.index.max(), df_fin.index.max())

        if start_limit >= end_limit:
            raise ValueError("比較可能な時刻範囲がありません")

        tasks = load_log_tasks(
            uploaded_files,
            has_log,
            interval_min,
            start_limit,
            end_limit,
            start_limit.normalize()
        )

        results = []
        for task in tasks:
            s_t = task['Start_Time']
            e_t = task['End_Time']

            results.append({
                "task": task['Task_Name'],
                "eval_1": {
                    **evaluate_max_device(df_ecg, df_ppg, s_t, e_t),
                    "device_name": "ECG vs PPG_BPM"
                },
                "eval_2": {
                    **evaluate_max_device(df_fin, df_ppg, s_t, e_t),
                    "device_name": "PPG_fin vs PPG_BPM"
                }
            })

        return {
            "analysis_type": "max_evaluation",
            "status": "success",
            "data": results,
            "title": "MAX評価 結果 (タスク別)"
        }

    except Exception as e:
        return {
            "analysis_type": "max_evaluation",
            "status": "error",
            "message": f"MAX解析エラー: {str(e)}"
        }