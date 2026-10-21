"""実験ログの読み込みとタスク区間の構築処理．"""
import pandas as pd

from services.common import read_uploaded_csv, resolve_log_file
from services.time_utils import _safe_parse_datetime, parse_datetime_or_duration


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
