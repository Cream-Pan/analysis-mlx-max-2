import io
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error

from services.common import config, load_body_temp, load_log_tasks, parse_datetime_or_duration, get_log_start_time


def get_mlx_layout(mode, file_kind):
    mlx_cfg = config.get("mlx_columns", {})

    if mode == "normal" and file_kind == "csv":
        return mlx_cfg["normal_csv"]
    if mode == "normal" and file_kind == "xlsx":
        return mlx_cfg["normal_xlsx"]
    if mode == "corrected" and file_kind == "csv":
        return mlx_cfg["corrected_csv"]

    raise ValueError(f"未対応の MLX レイアウトです: mode={mode}, file_kind={file_kind}")


def resolve_mlx_evaluation_file(uploaded_files):
    """
    mlx_evaluation 用の入力ファイルを自動選択する
    """
    fixed_candidates = config.get("mlx_evaluation_file_candidates", [])
    for name in fixed_candidates:
        if name in uploaded_files:
            return name

    keywords = [k.lower() for k in config.get("mlx_evaluation_filename_keywords", [])]

    for filename in uploaded_files.keys():
        lower_name = filename.lower()

        if not (lower_name.endswith(".csv") or lower_name.endswith(".xlsx") or lower_name.endswith(".xls")):
            continue

        if all(keyword in lower_name for keyword in keywords):
            return filename

    raise ValueError("mlx_evaluation 用の MLX 生データファイルが見つかりません")


def load_mlx_device_data(uploaded_files, mode, has_log, t1=None):
    """MLX デバイスデータを読み込んで時系列 DataFrame に整形"""
    if mode == "normal":
        target_filename = resolve_mlx_evaluation_file(uploaded_files)
        target_file = uploaded_files[target_filename]
        lower_name = target_filename.lower()

        # -----------------------------
        # Excel の場合
        # -----------------------------
        if lower_name.endswith((".xlsx", ".xls")):
            layout = get_mlx_layout("normal", "xlsx")

            xls = pd.ExcelFile(io.BytesIO(target_file.read()))
            target_file.seek(0)

            sheet_candidates = config.get("mlx_sheet_candidates", [])
            sheet = next((s for s in sheet_candidates if s in xls.sheet_names), None)
            if sheet is None:
                raise ValueError("MLX シートが見つかりません")

            recvjst_h = pd.read_excel(
                io.BytesIO(target_file.read()),
                sheet_name=sheet,
                header=None,
                skiprows=1,
                nrows=1,
                usecols=layout["recvjst_col_letter"]
            )
            target_file.seek(0)

            recvjst_raw = recvjst_h.iloc[0, 0]
            if not has_log:
                t1 = parse_datetime_or_duration(recvjst_raw)
                offset_td = pd.to_timedelta("0s")

            else:
                f2 = pd.read_excel(
                    io.BytesIO(target_file.read()),
                    sheet_name=sheet,
                    header=None,
                    skiprows=1,
                    nrows=1,
                    usecols=layout["offset_col_letter"]
                )
                target_file.seek(0)

                raw_offset = f2.iloc[0, 0]
                try:
                    offset_td = pd.to_timedelta(float(raw_offset), unit="s")
                except Exception:
                    offset_td = pd.to_timedelta("0s")

            df_raw = pd.read_excel(io.BytesIO(target_file.read()), sheet_name=sheet)
            target_file.seek(0)

            if len(df_raw.columns) < layout["min_columns"]:
                raise ValueError(f"{target_filename} の列数が不足しています")

            amb_col = df_raw.columns[layout["ambient"]]
            obj_col = df_raw.columns[layout["object"]]
            elap_col = df_raw.columns[layout["elapsed_ms"]]

            title = f"MLX評価 結果 ({target_filename} / {sheet})"

        # -----------------------------
        # CSV の場合
        # -----------------------------
        elif lower_name.endswith(".csv"):
            layout = get_mlx_layout("normal", "csv")

            try:
                df_raw = pd.read_csv(io.BytesIO(target_file.read()))
                target_file.seek(0)
            except Exception:
                target_file.seek(0)
                df_raw = pd.read_csv(io.BytesIO(target_file.read()), encoding="shift_jis")
                target_file.seek(0)

            if len(df_raw.columns) < layout["min_columns"]:
                raise ValueError(f"{target_filename} の列数が不足しています")

            amb_col = df_raw.columns[layout["ambient"]]
            obj_col = df_raw.columns[layout["object"]]
            elap_col = df_raw.columns[layout["elapsed_ms"]]

            if not has_log:
                recvjst_raw = df_raw.iloc[0, layout["recvjst"]]
                t1 = parse_datetime_or_duration(recvjst_raw)
                offset_td = pd.to_timedelta("0s")

            else:
                raw_offset = df_raw.iloc[0, layout["offset_s"]]
                offset_td = pd.to_timedelta(raw_offset, unit="s", errors="coerce")
                if pd.isna(offset_td):
                    offset_td = pd.to_timedelta("0s")

            title = f"MLX評価 結果 ({target_filename})"

        else:
            raise ValueError("MLX 生データファイルの形式が未対応です")

    # -----------------------------
    # corrected の場合
    # -----------------------------
    else:
        layout = get_mlx_layout("corrected", "csv")

        try:
            df_raw = pd.read_csv(io.BytesIO(uploaded_files["mlx_re.csv"].read()))
            uploaded_files["mlx_re.csv"].seek(0)
        except Exception:
            uploaded_files["mlx_re.csv"].seek(0)
            df_raw = pd.read_csv(io.BytesIO(uploaded_files["mlx_re.csv"].read()), encoding="shift_jis")
            uploaded_files["mlx_re.csv"].seek(0)

        if len(df_raw.columns) < layout["min_columns"]:
            raise ValueError("mlx_re.csv の列数が不足しています")

        amb_col = df_raw.columns[layout["ambient"]]
        elap_col = df_raw.columns[layout["elapsed_ms"]]
        obj_col = df_raw.columns[layout["object"]]

        if not has_log:
            recvjst_raw = df_raw.iloc[0, layout["recvjst"]]
            t1 = parse_datetime_or_duration(recvjst_raw)
            offset_td = pd.to_timedelta("0s")

        else:
            raw_offset = df_raw.iloc[0, layout["offset_s"]]
            offset_td = pd.to_timedelta(raw_offset, unit="s", errors="coerce")
            if pd.isna(offset_td):
                offset_td = pd.to_timedelta("0s")

        title = "MLX修正後評価 結果 (mlx_re.csv)"

    if t1 is None:
        raise ValueError("MLX の基準時刻 t1 を決定できませんでした")

    time_1 = t1 + offset_td

    sensor_td = pd.to_timedelta(df_raw[elap_col], unit="ms", errors="coerce")
    if sensor_td.isna().all():
        raise ValueError("経過時間列の変換に失敗しました")

    diff_td = sensor_td.diff().fillna(pd.Timedelta(seconds=0))

    df_dev = pd.DataFrame({
        "Timestamp": time_1 + diff_td.cumsum(),
        "Ambient_C": pd.to_numeric(df_raw[amb_col], errors="coerce"),
        "Object_C": pd.to_numeric(df_raw[obj_col], errors="coerce")
    }).dropna(subset=["Timestamp", "Ambient_C", "Object_C"]).set_index("Timestamp").sort_index()

    if df_dev.empty:
        raise ValueError("MLX デバイスデータが空です")

    return df_dev, title


def process_mlx_common(uploaded_files, mode, has_log, interval_min):
    try:
        # 1. 真値(体温)
        df_true = load_body_temp(uploaded_files["body_temperature.csv"])
        if df_true.empty:
            raise ValueError("body_temperature.csv が空です")

        base_day = df_true.index.min().normalize()

        # 2. 開始時刻
        sensor_start = get_log_start_time(uploaded_files)

        # 3. デバイスデータ
        df_dev, title = load_mlx_device_data(uploaded_files, mode, has_log, sensor_start)

        # 4. タスク分割
        tasks = load_log_tasks(
            uploaded_files,
            has_log,
            interval_min,
            df_dev.index.min(),
            df_dev.index.max(),
            base_day
        )

        # 5. 補間と比較
        pred = df_dev.reindex(df_true.index.union(df_dev.index)).interpolate("time").reindex(df_true.index)
        comp = pd.DataFrame({
            "true": df_true["temp"],
            "pred": pred["Object_C"]
        }).dropna()

        if comp.empty:
            raise ValueError("補間後の有効データがありません")

        # 6. タスクごとの評価
        results = []
        for task in tasks:
            start_t = task["Start_Time"]
            end_t = task["End_Time"]
            task_name = task["Task_Name"]

            seg = comp.loc[start_t:end_t]
            seg_dev = df_dev.loc[start_t:end_t]
            seg_true = df_true.loc[start_t:end_t]

            if seg.empty or seg_dev.empty or seg_true.empty:
                results.append({
                    "task": task_name,
                    "count": 0,
                    "mae": None,
                    "rmse": None,
                    "mean_object_c": None,
                    "mean_ambient_c": None,
                    "mean_body_temp": None
                })
                continue

            results.append({
                "task": task_name,
                "count": len(seg),
                "mae": float(mean_absolute_error(seg["true"], seg["pred"])),
                "rmse": float(np.sqrt(mean_squared_error(seg["true"], seg["pred"]))),
                "mean_object_c": float(seg_dev["Object_C"].mean()),
                "mean_ambient_c": float(seg_dev["Ambient_C"].mean()),
                "mean_body_temp": float(seg_true["temp"].mean())
            })

        return {"status": "success", "data": results, "title": title}

    except Exception as e:
        return {"status": "error", "message": f"MLX解析エラー: {str(e)}"}