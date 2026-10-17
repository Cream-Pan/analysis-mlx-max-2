import io
import re
import pandas as pd

from services.settings import config

# ----------------------------------------
# 共通: 設定とアップロードファイル
# ----------------------------------------



def read_uploaded_csv(file_obj, **kwargs):
    """Read an uploaded CSV and restore its stream position, even on failure."""
    try:
        return pd.read_csv(io.BytesIO(file_obj.read()), **kwargs)
    finally:
        file_obj.seek(0)


def read_uploaded_csv_columns(file_obj):
    """Return the header columns of an uploaded CSV."""
    return set(read_uploaded_csv(file_obj, nrows=0).columns)


def get_uploaded_files_dict(files):
    return {f.filename: f for f in files}


def _config_value(path):
    value = config
    for key in str(path).split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"入力仕様の設定参照が不正です: {path}")
        value = value[key]
    return value


def _required_columns(spec):
    if "columns_ref" not in spec:
        return []
    columns = _config_value(spec["columns_ref"])
    if isinstance(columns, dict):
        return [str(value) for value in columns.values()]
    if isinstance(columns, (list, tuple)):
        return [str(value) for value in columns]
    raise ValueError(f"列名の設定が不正です: {spec['columns_ref']}")


def _filename_matches_rule(filename, rule):
    lower_name = filename.lower()
    extensions = [value.lower() for value in rule.get("extensions", [])]
    if extensions and not any(lower_name.endswith(ext) for ext in extensions):
        return False
    suffix = rule.get("suffix")
    if suffix and not lower_name.endswith(suffix.lower()):
        return False
    if any(value.lower() not in lower_name for value in rule.get("contains_all", [])):
        return False
    contains_any = rule.get("contains_any", [])
    if contains_any and not any(value.lower() in lower_name for value in contains_any):
        return False
    if any(value.lower() in lower_name for value in rule.get("exclude_contains", [])):
        return False
    return True


def read_uploaded_file_columns(file_obj, filename, sheet_candidates=None):
    """CSV／Excel の見出しを読み，アップロードストリームを先頭へ戻す．"""
    try:
        payload = file_obj.read()
    finally:
        file_obj.seek(0)

    lower_name = filename.lower()
    if lower_name.endswith((".xlsx", ".xls")):
        workbook = pd.ExcelFile(io.BytesIO(payload))
        candidates = sheet_candidates or []
        sheet = next((name for name in candidates if name in workbook.sheet_names), None)
        if sheet is None:
            if not workbook.sheet_names:
                raise ValueError("シートがありません")
            sheet = workbook.sheet_names[0]
        columns = pd.read_excel(
            io.BytesIO(payload), sheet_name=sheet, nrows=0
        ).columns
        return set(str(value) for value in columns)

    try:
        return set(read_uploaded_csv(io.BytesIO(payload), nrows=0).columns.astype(str))
    except Exception as utf8_error:
        try:
            return set(read_uploaded_csv(
                io.BytesIO(payload), nrows=0, encoding="shift_jis"
            ).columns.astype(str))
        except Exception:
            raise ValueError(f"CSV の見出しを読み取れません: {utf8_error}")


def _validate_input_file(filename, file_obj, file_spec):
    try:
        sheet_candidates = []
        if "sheet_candidates_ref" in file_spec:
            sheet_candidates = _config_value(file_spec["sheet_candidates_ref"])
        columns = read_uploaded_file_columns(
            file_obj, filename, sheet_candidates=sheet_candidates
        )
    except Exception as error:
        return f"{filename} の見出しを確認できません: {error}"

    required = _required_columns(file_spec)
    missing = [name for name in required if name not in columns]
    if missing:
        return f"{filename} に必要な列がありません: {', '.join(missing)}"

    min_columns = file_spec.get("min_columns")
    if min_columns is not None and len(columns) < int(min_columns):
        return f"{filename} の列数が不足しています（{min_columns} 列以上が必要です）"
    return None


def get_required_files(analysis_type, has_log):
    input_spec = config.get("input_specs", {}).get(analysis_type, {})
    return [item["name"] for item in input_spec.get("fixed_files", [])]


def validate_required_files(uploaded_files, analysis_type, has_log):
    input_spec = config.get("input_specs", {}).get(analysis_type)
    if input_spec is None:
        return False, "未対応の解析タイプです"

    missing = [
        item["name"] for item in input_spec.get("fixed_files", [])
        if item["name"] not in uploaded_files
    ]
    if missing:
        return False, f"必要なファイルが不足しています: {', '.join(missing)}"

    for item in input_spec.get("fixed_files", []):
        error = _validate_input_file(
            item["name"], uploaded_files[item["name"]], item
        )
        if error:
            return False, error

    for rule in input_spec.get("file_rules", []):
        filename_candidates = [
            name for name in uploaded_files
            if _filename_matches_rule(name, rule)
        ]
        if rule.get("selection") == "columns":
            candidates = []
            for name in filename_candidates:
                try:
                    sheet_candidates = rule.get("sheet_candidates", [])
                    if "sheet_candidates_ref" in rule:
                        sheet_candidates = _config_value(
                            rule["sheet_candidates_ref"]
                        )
                    columns = read_uploaded_file_columns(
                        uploaded_files[name], name,
                        sheet_candidates=sheet_candidates
                    )
                except Exception:
                    continue
                required = _required_columns(rule)
                if set(required).issubset(columns):
                    candidates.append(name)
        else:
            candidates = filename_candidates

        minimum = int(rule.get("min_count", 0))
        maximum = rule.get("max_count")
        if len(candidates) < minimum:
            required_columns = _required_columns(rule)
            details = (
                f"（必要列: {', '.join(required_columns)}）"
                if required_columns else ""
            )
            return False, (
                f"{rule.get('label', '入力ファイル')}が不足しています．"
                f"{minimum} 個以上選択してください{details}"
            )
        if maximum is not None and len(candidates) > int(maximum):
            return False, (
                f"{rule.get('label', '入力ファイル')}は {maximum} 個まで選択してください"
            )

        for name in candidates:
            error = _validate_input_file(name, uploaded_files[name], rule)
            if error:
                return False, error

    log_policy = input_spec.get("log_policy", "optional")
    if log_policy == "required" and not has_log:
        return False, "この解析ではログファイルの使用が必要です"
    if log_policy == "unused" and has_log:
        return False, "この解析ではログファイルを使用できません"
    if has_log:
        try:
            log_filename = resolve_log_file(uploaded_files)
        except ValueError as e:
            return False, str(e)
        required_log_columns = _config_value(
            input_spec.get("log_columns_ref", "common_input_columns.log")
        )
        try:
            log_columns = read_uploaded_file_columns(
                uploaded_files[log_filename], log_filename
            )
        except Exception as error:
            return False, f"ログファイルの見出しを確認できません: {error}"
        missing_log_columns = [
            column for column in required_log_columns if column not in log_columns
        ]
        if missing_log_columns:
            return False, (
                "ログファイルに必要な列がありません: "
                + ", ".join(missing_log_columns)
            )
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

def _read_log_dataframe(uploaded_files, missing_columns_message=None):
    """ログCSVを読み，必要な列を共通確認する．"""
    filename = resolve_log_file(uploaded_files)
    df_log = read_uploaded_csv(uploaded_files[filename])
    required_columns = {"Task_Name", "Timestamp"}
    if not required_columns.issubset(df_log.columns):
        message = missing_columns_message or (
            "ログファイルに必要な列(Task_Name, Timestamp)がありません"
        )
        raise ValueError(message)
    return df_log.copy()


def _parse_log_timestamps(df_log, base_day=None, invalid="raise"):
    """ログ時刻を共通パーサで変換する．invalid='coerce' は不正値をNaTにする．"""
    parsed = df_log.copy()
    if invalid == "coerce":
        parsed["Timestamp_dt"] = parsed["Timestamp"].apply(
            lambda value: _safe_parse_datetime(value, base_day)
        )
    elif invalid == "raise":
        parsed["Timestamp_dt"] = parsed["Timestamp"].apply(
            lambda value: parse_datetime_or_duration(value, base_day)
        )
    else:
        raise ValueError(f"未対応の時刻エラー処理です: {invalid}")
    valid_timestamps = parsed["Timestamp_dt"].dropna()
    duplicate_timestamps = valid_timestamps[
        valid_timestamps.duplicated(keep=False)
    ]
    if not duplicate_timestamps.empty:
        raise ValueError(
            "ログファイルに同じ時刻の記録があります: "
            f"{duplicate_timestamps.iloc[0]}"
        )
    return parsed


def _sort_log_rows_with_end_time(df_log):
    """時刻順に並べ，各行へ次の境界時刻を付ける．"""
    sorted_log = df_log.sort_values("Timestamp_dt").reset_index(drop=True)
    sorted_log["End_Time"] = sorted_log["Timestamp_dt"].shift(-1)
    return sorted_log


def _find_log_start_row(df_log):
    task_name_clean = (
        df_log["Task_Name"]
        .astype(str)
        .str.replace('"', '', regex=False)
        .str.strip()
        .str.lower()
    )
    start_rows = df_log[
        task_name_clean.str.contains("ble_start_time|start", regex=True)
    ]
    if start_rows.empty:
        raise ValueError("BLE_START_TIME (Main) がログファイルにありません")
    return start_rows.iloc[0]

def get_log_start_time(uploaded_files):
    df_log = _parse_log_timestamps(_read_log_dataframe(uploaded_files))
    start_row = _find_log_start_row(df_log)
    return start_row["Timestamp_dt"]

def get_log_end_time(uploaded_files):
    df_log = _parse_log_timestamps(_read_log_dataframe(uploaded_files))
    return df_log["Timestamp_dt"].max()

# ----------------------------------------
# 汎用: 時刻 or 持続時間の柔軟パーサ
# ----------------------------------------
def parse_datetime_series(series):
    """CSV の日時列を整形して datetime に変換する．"""
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace('="', '', regex=False)
        .str.replace('"', '', regex=False)
    )
    return pd.to_datetime(cleaned, errors="coerce")


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
        df_log = _read_log_dataframe(
            uploaded_files,
            missing_columns_message="log.csv に必要な列(Task_Name, Timestamp)がありません",
        )

        df_log['Task_Name'] = df_log['Task_Name'].astype(str).str.replace('"', '', regex=False)
        df_log = _parse_log_timestamps(df_log, base_day=base_day)
        df_log = df_log.dropna(subset=['Task_Name', 'Timestamp_dt']).sort_values('Timestamp_dt')

        # task_names = config.get('task_names', [])
        # if task_names:
        #     df_log = df_log[df_log['Task_Name'].isin(task_names)].copy()

        if len(df_log) < 2:
            raise ValueError("タスク境界が 2 つ未満です")

        df_log = _sort_log_rows_with_end_time(df_log)
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

    df_log = _read_log_dataframe(uploaded_files)

    df_log["Task_Name"] = (
        df_log["Task_Name"]
        .astype(str)
        .str.replace('"',"",regex=False)
    )

    df_log = _parse_log_timestamps(df_log)
    _find_log_start_row(df_log)

    df_log = _sort_log_rows_with_end_time(df_log)

    df_log = df_log.dropna(
        subset=["End_Time"]
    )

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
    df = read_uploaded_csv(
        file_obj,
        header=None,
        skiprows=1,
        usecols=[0, 1],
        names=['temp', 'time']
    )

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
    df_log = _read_log_dataframe(uploaded_files)

    df_log = df_log.copy()
    df_log["Task_Name"] = (
        df_log["Task_Name"]
        .astype(str)
        .str.replace('"', '', regex=False)
        .str.strip()
    )
    df_log = _parse_log_timestamps(
        df_log, base_day=base_day, invalid="coerce"
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
    range_rows = _sort_log_rows_with_end_time(
        df_log.loc[start_index:end_index]
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
    for _, row in range_rows.dropna(subset=["End_Time"]).iterrows():
        task_start = row["Timestamp_dt"]
        task_end = row["End_Time"]

        if task_end <= task_start:
            continue

        tasks.append({
            "name": str(row["Task_Name"]),
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
                df = read_uploaded_csv(
                    file_obj,
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
