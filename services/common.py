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

def get_log_end_time(uploaded_files):

    log_filename = resolve_log_file(
        uploaded_files
    )

    df_log = pd.read_csv(
        io.BytesIO(
            uploaded_files[log_filename].read()
        )
    )

    uploaded_files[log_filename].seek(0)

    df_log["Timestamp_dt"] = (
        df_log["Timestamp"]
        .apply(parse_datetime_or_duration)
    )

    return df_log["Timestamp_dt"].max()

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
    row["Timestamp_dt"].isoformat(),

    "end":
    row["End_Time"].isoformat()

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

def _find_column_case_insensitive(df, target_name):
    """列名を大文字・小文字を区別せずに検索する．"""
    target = str(target_name).strip().lower()
    for column in df.columns:
        if str(column).strip().lower() == target:
            return column
    return None


def _safe_parse_datetime(value, base_day=None):
    try:
        text = str(value).strip().replace('"', '').replace('=', '')

        # 時刻だけの文字列は，センサデータ側の日付へ明示的に合わせる．
        if base_day is not None and re.match(
            r'^\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?$',
            text
        ):
            duration = pd.to_timedelta(text, errors="coerce")
            if pd.notna(duration):
                return pd.Timestamp(base_day).normalize() + duration

        return parse_datetime_or_duration(value, base_day)
    except (TypeError, ValueError):
        return pd.NaT


def build_x_axis(df):
    """
    ファイル内表示用の時間軸を構築する．

    優先順位:
    1. RecvJST + SensorElapsed_ms
    2. sampling_time
    3. 行番号

    戻り値:
        x_values: フロントへ渡す表示用の値
        compare_values: ログ時刻との比較に使う値
        x_type: datetime / sampling / index
        x_source: 時間軸の生成元
    """
    recv_column = _find_column_case_insensitive(df, "RecvJST")
    elapsed_column = _find_column_case_insensitive(df, "SensorElapsed_ms")

    if recv_column is not None and elapsed_column is not None:
        recv_values = df[recv_column].apply(_safe_parse_datetime)
        elapsed_values = pd.to_numeric(
            df[elapsed_column],
            errors="coerce"
        )

        anchor_mask = recv_values.notna() & elapsed_values.notna()
        if not anchor_mask.any():
            raise ValueError(
                "RecvJSTとSensorElapsed_msから有効な時間軸を構築できません"
            )

        anchor_index = anchor_mask[anchor_mask].index[0]
        anchor_time = recv_values.loc[anchor_index]
        anchor_elapsed = elapsed_values.loc[anchor_index]

        reconstructed = (
            anchor_time
            + pd.to_timedelta(
                elapsed_values - anchor_elapsed,
                unit="ms"
            )
        )

        x_values = [
            value.isoformat() if pd.notna(value) else None
            for value in reconstructed
        ]

        return {
            "x_values": x_values,
            "compare_values": reconstructed,
            "x_type": "datetime",
            "x_source": "RecvJST + SensorElapsed_ms"
        }

    sampling_column = None
    for column in df.columns:
        if "sampling_time" in str(column).strip().lower():
            sampling_column = column
            break

    if sampling_column is not None:
        raw_sampling = df[sampling_column]
        numeric_sampling = pd.to_numeric(raw_sampling, errors="coerce")

        # sampling_timeが数値なら，値をそのまま時間軸として保持する．
        if numeric_sampling.notna().any():
            x_values = [
                None if pd.isna(value) else float(value)
                for value in numeric_sampling
            ]

            return {
                "x_values": x_values,
                "compare_values": numeric_sampling,
                "x_type": "sampling",
                "x_source": str(sampling_column)
            }

        # 日時文字列として保存されているsampling_timeにも対応する．
        datetime_sampling = raw_sampling.apply(_safe_parse_datetime)
        if datetime_sampling.notna().any():
            x_values = [
                value.isoformat() if pd.notna(value) else None
                for value in datetime_sampling
            ]

            return {
                "x_values": x_values,
                "compare_values": datetime_sampling,
                "x_type": "datetime",
                "x_source": str(sampling_column)
            }

        raise ValueError(
            "sampling_time列から有効な時間軸を取得できません"
        )

    index_values = pd.Series(
        range(1, len(df) + 1),
        index=df.index,
        dtype="float64"
    )

    return {
        "x_values": index_values.tolist(),
        "compare_values": index_values,
        "x_type": "index",
        "x_source": "row_index"
    }


def _normalize_task_name(value):
    return (
        str(value)
        .replace('"', '')
        .strip()
        .lower()
    )


def _is_preview_start_name(value):
    name = _normalize_task_name(value)
    return (
        name == "start"
        or name.startswith("start ")
        or name.startswith("start(")
        or "ble_start_time" in name
    )


def _is_preview_end_name(value):
    name = _normalize_task_name(value)
    return (
        name == "end"
        or name.startswith("end ")
        or name.startswith("end(")
        or "experiment_end" in name
        or "ble_end_time" in name
    )


def load_preview_log_range(uploaded_files, base_day=None):
    """
    ログファイル内のStartからEndまでを読み込み，
    描画範囲，タスク区間，x軸に表示する時刻を返す．
    """
    log_filename = resolve_log_file(uploaded_files)
    log_file = uploaded_files[log_filename]

    df_log = pd.read_csv(io.BytesIO(log_file.read()))
    log_file.seek(0)

    required_columns = {"Task_Name", "Timestamp"}
    if not required_columns.issubset(df_log.columns):
        raise ValueError(
            "ログファイルに必要な列(Task_Name, Timestamp)がありません"
        )

    df_log = df_log.copy()
    df_log["Task_Name"] = (
        df_log["Task_Name"]
        .astype(str)
        .str.replace('"', '', regex=False)
        .str.strip()
    )
    df_log["Timestamp_dt"] = df_log["Timestamp"].apply(
        lambda value: _safe_parse_datetime(value, base_day)
    )
    df_log = df_log.dropna(
        subset=["Task_Name", "Timestamp_dt"]
    ).reset_index(drop=True)

    start_candidates = [
        index
        for index, task_name in enumerate(df_log["Task_Name"])
        if _is_preview_start_name(task_name)
    ]
    if not start_candidates:
        raise ValueError(
            "ログファイル内にStartが見つかりません"
        )

    start_index = start_candidates[0]
    end_candidates = [
        index
        for index in range(start_index + 1, len(df_log))
        if _is_preview_end_name(df_log.loc[index, "Task_Name"])
    ]
    if not end_candidates:
        raise ValueError(
            "ログファイル内にStartより後のEndが見つかりません"
        )

    end_index = end_candidates[0]
    range_rows = (
        df_log.loc[start_index:end_index]
        .sort_values("Timestamp_dt")
        .reset_index(drop=True)
    )

    if len(range_rows) < 2:
        raise ValueError(
            "StartからEndまでのタスク境界が不足しています"
        )

    log_start = range_rows.iloc[0]["Timestamp_dt"]
    log_end = range_rows.iloc[-1]["Timestamp_dt"]

    if log_end <= log_start:
        raise ValueError(
            "ログファイルのEnd時刻がStart時刻以前になっています"
        )

    tasks = []
    for index in range(len(range_rows) - 1):
        task_start = range_rows.iloc[index]["Timestamp_dt"]
        task_end = range_rows.iloc[index + 1]["Timestamp_dt"]

        if task_end <= task_start:
            continue

        tasks.append({
            "name": str(range_rows.iloc[index]["Task_Name"]),
            "start": task_start.isoformat(),
            "end": task_end.isoformat()
        })

    axis_ticks = [
        {
            "value": row["Timestamp_dt"].isoformat(),
            "label": row["Timestamp_dt"].strftime("%H:%M:%S")
        }
        for _, row in range_rows.iterrows()
    ]

    return {
        "start": log_start,
        "end": log_end,
        "tasks": tasks,
        "axis_ticks": axis_ticks
    }


def _align_axis_to_log(axis_info, log_start):
    """
    sampling_timeが相対秒の場合，先頭値をログのStart時刻へ対応付ける．
    RecvJST由来または日時型sampling_timeは，その日時をそのまま使う．
    """
    x_type = axis_info["x_type"]
    compare_values = axis_info["compare_values"]

    if x_type == "datetime":
        return pd.to_datetime(compare_values, errors="coerce")

    if x_type == "sampling":
        numeric_values = pd.to_numeric(compare_values, errors="coerce")
        valid_values = numeric_values.dropna()
        if valid_values.empty:
            raise ValueError(
                "sampling_timeからログ比較用の時間軸を作成できません"
            )

        first_sampling_time = valid_values.iloc[0]
        return (
            log_start
            + pd.to_timedelta(
                numeric_values - first_sampling_time,
                unit="s"
            )
        )

    raise ValueError(
        "ログありのファイル内表示には，"
        "RecvJST + SensorElapsed_msまたはsampling_timeが必要です"
    )


def _build_preview_sheet(
    df,
    sheet_name,
    column_numbers,
    preview_scale="same",
    x_values=None,
    x_type="index",
    x_source="row_index",
    tasks=None,
    axis_ticks=None,
    range_start=None,
    range_end=None
):
    series_list = []
    errors = []

    row_count = len(df)
    column_count = df.shape[1]
    x_values = x_values if x_values is not None else list(range(1, row_count + 1))

    if len(x_values) != row_count:
        raise ValueError(
            "時間軸とデータ行数が一致していません"
        )

    for column_number in column_numbers:
        column_index = column_number - 1

        if column_index < 0 or column_index >= column_count:
            errors.append(
                f"{column_number}列目は存在しません"
                f"（このデータは{column_count}列です）"
            )
            continue

        numeric_series = pd.to_numeric(
            df.iloc[:, column_index],
            errors="coerce"
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

        if preview_scale == "normalize":
            valid_values = [
                value
                for value in values
                if value is not None
            ]

            if valid_values:
                min_value = min(valid_values)
                max_value = max(valid_values)

                if max_value != min_value:
                    values = [
                        (
                            (value - min_value) / (max_value - min_value)
                            if value is not None
                            else None
                        )
                        for value in values
                    ]
                else:
                    values = [
                        0.0 if value is not None else None
                        for value in values
                    ]

        points = [
            {
                "x": x_values[index],
                "y": value
            }
            for index, value in enumerate(values)
            if x_values[index] is not None
        ]

        series_list.append({
            "column_number": column_number,
            "valid_count": valid_count,
            "points": points
        })

    return {
        "sheet_name": sheet_name,
        "row_count": row_count,
        "column_count": column_count,
        "x_type": x_type,
        "x_source": x_source,
        "preview_scale": preview_scale,
        "columns": [str(column) for column in df.columns],
        "series": series_list,
        "errors": errors,
        "tasks": tasks or [],
        "axis_ticks": axis_ticks or [],
        "range_start": range_start,
        "range_end": range_end
    }


def _prepare_preview_dataframe(
    df,
    uploaded_files,
    has_log
):
    axis_info = build_x_axis(df)
    tasks = []
    axis_ticks = []
    range_start = None
    range_end = None

    if not has_log:
        return {
            "df": df.reset_index(drop=True),
            "x_values": axis_info["x_values"],
            "x_type": axis_info["x_type"],
            "x_source": axis_info["x_source"],
            "tasks": tasks,
            "axis_ticks": axis_ticks,
            "range_start": range_start,
            "range_end": range_end
        }

    base_day = None
    if axis_info["x_type"] == "datetime":
        valid_datetime = pd.to_datetime(
            axis_info["compare_values"],
            errors="coerce"
        ).dropna()
        if not valid_datetime.empty:
            base_day = valid_datetime.iloc[0].normalize()

    log_info = load_preview_log_range(
        uploaded_files,
        base_day=base_day
    )
    aligned_datetime = _align_axis_to_log(
        axis_info,
        log_info["start"]
    )

    mask = (
        aligned_datetime.notna()
        & (aligned_datetime >= log_info["start"])
        & (aligned_datetime <= log_info["end"])
    )

    if not mask.any():
        raise ValueError(
            "ファイルの時間軸とログのStartからEndまでが重なりません"
        )

    filtered_df = df.loc[mask].reset_index(drop=True)
    filtered_datetime = aligned_datetime.loc[mask].reset_index(drop=True)

    return {
        "df": filtered_df,
        "x_values": [
            value.isoformat() if pd.notna(value) else None
            for value in filtered_datetime
        ],
        "x_type": "datetime",
        "x_source": axis_info["x_source"],
        "tasks": log_info["tasks"],
        "axis_ticks": log_info["axis_ticks"],
        "range_start": log_info["start"].isoformat(),
        "range_end": log_info["end"].isoformat()
    }


def perform_file_preview(
    uploaded_files,
    column_numbers,
    preview_axis="index",
    preview_scale="same",
    has_log=False,
    interval_min=5
):
    # preview_axisとinterval_minは旧UIとの互換性のために残している．
    del preview_axis, interval_min

    results = []

    for filename, file_obj in uploaded_files.items():
        lower_filename = filename.lower()

        try:
            if (
                lower_filename.endswith("_log.csv")
                or lower_filename == "log.csv"
            ):
                continue

            if lower_filename.endswith((".xlsx", ".xls")):
                excel_sheets = pd.read_excel(
                    io.BytesIO(file_obj.read()),
                    sheet_name=None,
                    header=0
                )

                sheets = []
                for sheet_name, sheet_df in excel_sheets.items():
                    prepared = _prepare_preview_dataframe(
                        sheet_df,
                        uploaded_files,
                        has_log
                    )
                    sheets.append(
                        _build_preview_sheet(
                            prepared["df"],
                            sheet_name,
                            column_numbers,
                            preview_scale,
                            prepared["x_values"],
                            prepared["x_type"],
                            prepared["x_source"],
                            prepared["tasks"],
                            prepared["axis_ticks"],
                            prepared["range_start"],
                            prepared["range_end"]
                        )
                    )

                results.append({
                    "filename": filename,
                    "type": "excel",
                    "sheets": sheets
                })

            elif lower_filename.endswith(".csv"):
                df = pd.read_csv(
                    io.BytesIO(file_obj.read()),
                    low_memory=False
                )
                prepared = _prepare_preview_dataframe(
                    df,
                    uploaded_files,
                    has_log
                )

                results.append({
                    "filename": filename,
                    "type": "csv",
                    "sheets": [
                        _build_preview_sheet(
                            prepared["df"],
                            None,
                            column_numbers,
                            preview_scale,
                            prepared["x_values"],
                            prepared["x_type"],
                            prepared["x_source"],
                            prepared["tasks"],
                            prepared["axis_ticks"],
                            prepared["range_start"],
                            prepared["range_end"]
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
