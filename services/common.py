import io
import re
import json
import os
import pandas as pd

# ----------------------------------------
# 共通: 設定とアップロードファイル
# ----------------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)


def get_uploaded_files_dict(files):
    return {f.filename: f for f in files}


def get_required_files(analysis_type, has_log):
    required = list(config.get('required_files', {}).get(analysis_type, []))
    if has_log and analysis_type != 'show_files' and 'log.csv' not in required:
        required.insert(0, 'log.csv')
    return required


def validate_required_files(uploaded_files, analysis_type, has_log):
    required = get_required_files(analysis_type, has_log)
    missing = [name for name in required if name not in uploaded_files]
    if missing:
        return False, f"必要なファイルが不足しています: {', '.join(missing)}"
    return True, None

# ----------------------------------------
# 汎用: 時刻 or 持続時間の柔軟パーサ
# ----------------------------------------
def parse_datetime_or_duration(value, base_day=None):
    s = str(value).strip().replace('"', '').replace('=', '')

    dt = pd.to_datetime(s, errors='coerce')
    if pd.notna(dt):
        return dt

    try:
        num = float(s)
        return pd.Timestamp('1899-12-30') + pd.to_timedelta(num, unit='D')
    except Exception:
        pass

    if re.match(r'^\d{1,3}:\d{2}(\.\d+)?$', s):
        td = pd.to_timedelta("0:" + s, errors='coerce')
    else:
        td = pd.to_timedelta(s, errors='coerce')

    if pd.notna(td):
        base_day = base_day or pd.Timestamp.today().normalize()
        return base_day + td

    raise ValueError(f"未知の時刻書式: {s}")

# ----------------------------------------
# 共通: ログ・真値・プレビュー
# ----------------------------------------
def load_log_tasks(uploaded_files, has_log, interval_min, start_time_limit, end_time_limit, base_day):
    if has_log:
        if 'log.csv' not in uploaded_files:
            raise ValueError("log.csv が必要です")

        df_log = pd.read_csv(io.BytesIO(uploaded_files['log.csv'].read()))
        uploaded_files['log.csv'].seek(0)

        if 'Task_Name' not in df_log.columns or 'Timestamp' not in df_log.columns:
            raise ValueError("log.csv に必要な列(Task_Name, Timestamp)がありません")

        df_log['Task_Name'] = df_log['Task_Name'].astype(str).str.replace('"', '', regex=False)
        df_log['Timestamp_dt'] = df_log['Timestamp'].apply(lambda x: parse_datetime_or_duration(x, base_day))
        df_log = df_log.dropna(subset=['Task_Name', 'Timestamp_dt']).sort_values('Timestamp_dt')

        task_names = config.get('task_names', [])
        if task_names:
            df_log = df_log[df_log['Task_Name'].isin(task_names)].copy()

        if len(df_log) < 2:
            raise ValueError("タスク境界が 2 つ未満です")

        df_log = df_log.reset_index(drop=True)
        df_log['End_Time'] = df_log['Timestamp_dt'].shift(-1)
        df_log = df_log.dropna(subset=['End_Time'])

        return [
            {
                'Task_Name': row['Task_Name'],
                'Start_Time': row['Timestamp_dt'],
                'End_Time': row['End_Time']
            }
            for _, row in df_log.iterrows()
        ]

    tasks = []
    curr = start_time_limit
    idx = 1

    while curr < end_time_limit:
        nxt = curr + pd.Timedelta(minutes=interval_min)
        if nxt > end_time_limit:
            nxt = end_time_limit

        tasks.append({
            'Task_Name': f'区間{idx}',
            'Start_Time': curr,
            'End_Time': nxt
        })
        curr = nxt
        idx += 1

    return tasks


def load_body_temp(file_obj):
    df = pd.read_csv(
        io.BytesIO(file_obj.read()),
        header=None,
        skiprows=1,
        usecols=[0, 1],
        names=['temp', 'time']
    )
    file_obj.seek(0)

    df['dt'] = df['time'].apply(lambda x: parse_datetime_or_duration(x))
    df['temp'] = pd.to_numeric(df['temp'], errors='coerce')

    return df.dropna(subset=['dt', 'temp']).set_index('dt').sort_index()


def perform_file_preview(uploaded_files):
    results = []

    for fn, f in uploaded_files.items():
        try:
            if fn.endswith(('.xlsx', '.xls')):
                xls = pd.read_excel(io.BytesIO(f.read()), sheet_name=None, header=None)
                f.seek(0)
                results.append({
                    "filename": fn,
                    "type": "excel",
                    "sheets": [
                        {
                            "sheet_name": s,
                            "data": df.head(5).astype(str).iloc[:, 0].tolist()
                        }
                        for s, df in xls.items()
                    ]
                })

            elif fn.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(f.read()), header=None, nrows=5)
                f.seek(0)
                results.append({
                    "filename": fn,
                    "type": "csv",
                    "sheets": [
                        {
                            "sheet_name": None,
                            "data": df.iloc[:, 0].astype(str).tolist()
                        }
                    ]
                })

        except Exception as e:
            f.seek(0)
            results.append({
                "filename": fn,
                "type": "error",
                "sheets": [
                    {
                        "sheet_name": None,
                        "data": [f"エラー: {e}"]
                    }
                ]
            })

    return results