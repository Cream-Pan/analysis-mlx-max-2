"""CSV／Excelファイルのプレビュー用データを構築する．"""
import io

import pandas as pd

from services.common import read_uploaded_csv
from services.log_service import load_preview_log_range
from services.time_utils import _safe_parse_datetime

def _find_column_case_insensitive(df, target_name):
    """列名を大文字・小文字を区別せずに検索する．"""
    target = str(target_name).strip().lower()
    for column in df.columns:
        if str(column).strip().lower() == target:
            return column
    return None


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
