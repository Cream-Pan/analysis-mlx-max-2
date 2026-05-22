import io
import pandas as pd

from services.common import config, load_log_tasks
from services.hr_compare_service import evaluate_hr_pair

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
    ppg_cfg = config["max_columns"]["ppg_bpm"]

    time_col = ppg_cfg["time"]
    hr_col = ppg_cfg["hr"]

    df = pd.read_csv(
        io.BytesIO(f_obj.read()),
        usecols=[time_col, hr_col]
    )
    f_obj.seek(0)

    df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
    df[hr_col] = pd.to_numeric(df[hr_col], errors='coerce')

    df = df.dropna(subset=[time_col, hr_col])
    df = df.set_index(time_col).sort_index()
    df = df[~df.index.duplicated(keep='first')]

    return df[[hr_col]].rename(columns={hr_col: "HR"})

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
                    **evaluate_hr_pair(df_ecg, df_ppg, s_t, e_t),
                    "device_name": "ECG vs PPG_BPM"
                },
                "eval_2": {
                    **evaluate_hr_pair(df_fin, df_ppg, s_t, e_t),
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