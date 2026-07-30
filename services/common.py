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
    return required


def validate_required_files(uploaded_files, analysis_type, has_log):
    required = get_required_files(analysis_type, has_log)
    missing = [name for name in required if name not in uploaded_files]
    if missing:
        return False, f"必要なファイルが不足しています: {', '.join(missing)}"
    if has_log:
        try:
            resolve_log_file(uploaded_files)
        except ValueError as e:
            return False, str(e)
    return True, None

def resolve_log_file(uploaded_files):
    candidates = []

    for filename in uploaded_files.keys():
        lower_name = filename.lower()

        if lower_name.endswith('_log.csv'):
            candidates.append(filename)

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        raise ValueError(
            f"ログファイルが複数あります: {', '.join(candidates)}"
        )

    if 'log.csv' in uploaded_files:
        return 'log.csv'

    raise ValueError(
        "ログファイル(*_log.csv)が見つかりません"
    )

def get_log_start_time(uploaded_files):
    log_filename = resolve_log_file(uploaded_files)

    df_log = pd.read_csv(
        io.BytesIO(uploaded_files[log_filename].read())
    )
    uploaded_files[log_filename].seek(0)

    if "Task_Name" not in df_log.columns or "Timestamp" not in df_log.columns:
        raise ValueError(
            "ログファイルに必要な列(Task_Name, Timestamp)がありません"
        )

    task_name_clean = (
        df_log["Task_Name"]
        .astype(str)
        .str.replace('"', '', regex=False)
        .str.strip()
        .str.lower()
    )


    start_rows = df_log[
        task_name_clean.str.contains(
            "ble_start_time|start",
            regex=True
        )
    ]

    if len(start_rows) == 0:
        raise ValueError(
            "BLE_START_TIME (Main) がログファイルにありません"
        )

    return parse_datetime_or_duration(
        start_rows.iloc[0]["Timestamp"]
    )

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
        log_filename = resolve_log_file(uploaded_files)

        df_log = pd.read_csv(
            io.BytesIO(uploaded_files[log_filename].read())
        )
        uploaded_files[log_filename].seek(0)

        if 'Task_Name' not in df_log.columns or 'Timestamp' not in df_log.columns:
            raise ValueError("log.csv に必要な列(Task_Name, Timestamp)がありません")

        df_log['Task_Name'] = df_log['Task_Name'].astype(str).str.replace('"', '', regex=False)
        df_log['Timestamp_dt'] = df_log['Timestamp'].apply(lambda x: parse_datetime_or_duration(x, base_day))
        df_log = df_log.dropna(subset=['Task_Name', 'Timestamp_dt']).sort_values('Timestamp_dt')

        # task_names = config.get('task_names', [])
        # if task_names:
        #     df_log = df_log[df_log['Task_Name'].isin(task_names)].copy()

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

def load_preview_tasks(uploaded_files, has_log, interval_min=5, start_time=None, end_time=None):
    if not has_log:
        if start_time is None or end_time is None:
            return []
        tasks = []
        curr = start_time
        idx = 1
        while curr < end_time:
            nxt = (
                curr +
                pd.Timedelta(minutes=interval_min)
            )
            if nxt > end_time:
                nxt = end_time

            tasks.append({
                "name":
                f"区間{idx}",
                "start":
                (
                    curr-start_time
                ).total_seconds(),

                "end":
                (
                    nxt-start_time
                ).total_seconds()
            })

            curr = nxt
            idx += 1

        return tasks

    log_filename = resolve_log_file(uploaded_files)
    df_log = pd.read_csv(
        io.BytesIO(
            uploaded_files[log_filename].read()
        )
    )
    uploaded_files[log_filename].seek(0)

    df_log["Task_Name"] = (
        df_log["Task_Name"]
        .astype(str)
        .str.replace('"',"",regex=False)
    )

    df_log["Timestamp_dt"] = (
        df_log["Timestamp"]
        .apply(parse_datetime_or_duration)
    )

    df_log = (
        df_log
        .sort_values("Timestamp_dt")
        .reset_index(drop=True)
    )

    df_log["End_Time"] = (
        df_log["Timestamp_dt"]
        .shift(-1)
    )

    df_log = df_log.dropna(
        subset=["End_Time"]
    )

    start_time = get_log_start_time(uploaded_files)

    return [
        {
        "name":row["Task_Name"],
        "start":
        (
            row["Timestamp_dt"]
            -
            start_time
        ).total_seconds(),

        "end":
        (
            row["End_Time"]
            -
            start_time
        ).total_seconds()
        }
        for _,row in df_log.iterrows()
    ]


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


def _build_preview_sheet(
    df,
    sheet_name,
    column_numbers,
    preview_axis="index",
    preview_scale="same",
    time_values=None,
    tasks=None
):
    series_list = []
    errors = []

    row_count = len(df)
    column_count = df.shape[1]

    for column_number in column_numbers:
        column_index = column_number - 1

        if column_index >= column_count:
            errors.append(
                f"{column_number}列目は存在しません"
                f"（このデータは{column_count}列です）"
            )
            continue

        numeric_series = pd.to_numeric(
            df.iloc[:, column_index],
            errors='coerce'
        )

        valid_count = int(numeric_series.notna().sum())

        if valid_count == 0:
            errors.append(
                f"{column_number}列目には"
                "プロット可能な数値がありません"
            )
            continue

        values = [
            None if pd.isna(value) else float(value)
            for value in numeric_series
        ]


        # 正規化
        if preview_scale == "normalize":

            valid_values = [
                v for v in values
                if v is not None
            ]

            if len(valid_values) > 0:

                min_v = min(valid_values)
                max_v = max(valid_values)

                if max_v != min_v:

                    values = [
                        (
                            (v - min_v) /
                            (max_v - min_v)
                            if v is not None
                            else None
                        )
                        for v in values
                    ]

        points = []
        for index, value in enumerate(values):
            if preview_axis == "time" and time_values is not None:
                x = float(time_values[index])
            else:
                x = index + 1

            points.append({
                "x": x,
                "y": value
            })

        series_list.append({
            "column_number": column_number,
            "valid_count": valid_count,
            "points": points
        })

    return {
        "sheet_name": sheet_name,
        "row_count": row_count,
        "column_count": column_count,
         "columns": [
            str(col)
            for col in df.columns
        ],
        "series": series_list,
        "errors": errors,
        "tasks": tasks if tasks else []
    }


def perform_file_preview(uploaded_files, column_numbers,preview_axis="index", preview_scale="same", has_log=False, interval_min=5):
    results = []

    for filename, file_obj in uploaded_files.items():
        lower_filename = filename.lower()

        try:
            if lower_filename.endswith('_log.csv'):
                continue
            if lower_filename.endswith(('.xlsx', '.xls')):
                excel_sheets = pd.read_excel(
                    io.BytesIO(file_obj.read()),
                    sheet_name=None,
                    header=None
                )
                time_values = None
                tasks = []
                if has_log:
                    tasks = load_preview_tasks(
                        uploaded_files
                    )

                results.append({
                    "filename": filename,
                    "type": "excel",
                    "sheets": [
                        _build_preview_sheet(
                            df,
                            sheet_name,
                            column_numbers,
                            preview_axis,
                            preview_scale,
                            time_values,
                            tasks
                        )
                        for sheet_name, df in excel_sheets.items()
                    ]
                })

            elif lower_filename.endswith('.csv'):
                df = pd.read_csv(
                    io.BytesIO(file_obj.read()),
                    low_memory=False
                )
                time_values = None

                if preview_axis == "time":
                    time_col = None

                    for col in df.columns:
                        col_name = str(col)
                        if (
                            "RecvJST" in col_name
                            or
                            "sampling_time" in col_name.lower()
                        ):
                            time_col = col
                            break

                    if time_col is not None:
                        if "sampling_time" in str(time_col).lower():
                            dt = (
                                df[time_col]
                                .apply(parse_datetime_or_duration)
                            )
                            base_time = dt.iloc[0]
                            time_values = (
                                dt - base_time
                            ).dt.total_seconds().tolist()

                        else:
                            base_time = get_log_start_time(
                                uploaded_files
                            )
                            dt = (
                                df[time_col]
                                .apply(parse_datetime_or_duration)
                            )
                            time_values = (
                                dt - base_time
                            ).dt.total_seconds().tolist()

                tasks = []
                if has_log:
                    tasks = load_preview_tasks(
                        uploaded_files,
                        True
                    )
                else:
                    if preview_axis == "time" and time_values is not None:

                        total_time = time_values[-1]
                    else:
                        total_time = len(df)

                    start_time = pd.Timestamp(0)
                    end_time = (
                        start_time +
                        pd.Timedelta(
                            seconds=total_time
                        )
                    )

                    tasks = load_preview_tasks(
                        uploaded_files,
                        False,
                        interval_min,
                        start_time,
                        end_time
                    )

                results.append({
                    "filename": filename,
                    "type": "csv",
                    "sheets": [
                        _build_preview_sheet(
                            df,
                            None,
                            column_numbers,
                            preview_axis,
                            preview_scale,
                            time_values,
                            tasks
                        )
                    ]
                })

            else:
                results.append({
                    "filename": filename,
                    "type": "error",
                    "message": (
                        "対応していないファイル形式です．"
                        "CSV，XLSX，XLSのみ対応しています．"
                    ),
                    "sheets": []
                })

        except Exception as error:
            results.append({
                "filename": filename,
                "type": "error",
                "message": f"エラー: {error}",
                "sheets": []
            })

        finally:
            file_obj.seek(0)

    return results