"""MLXファイルを固定時間区間に分け，2列の回帰表示データを構築する．"""
import io
import math

import pandas as pd

from services.common import read_uploaded_csv
from services.file_preview_service import (
    _build_preview_sheet,
    _prepare_preview_dataframe,
    build_x_axis,
)


MAX_REGRESSION_SEGMENTS = 20000
SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")


def _read_mlx_sheets(file_obj, filename):
    """CSVまたはExcelからシート名とDataFrameの組を返す．"""
    payload = file_obj.read()
    file_obj.seek(0)
    lower_name = filename.lower()

    if lower_name.endswith(".csv"):
        try:
            dataframe = read_uploaded_csv(io.BytesIO(payload), low_memory=False)
        except Exception:
            dataframe = read_uploaded_csv(
                io.BytesIO(payload), encoding="shift_jis", low_memory=False
            )
        return [(None, dataframe)]

    if lower_name.endswith((".xlsx", ".xls")):
        sheets = pd.read_excel(io.BytesIO(payload), sheet_name=None, header=0)
        return list(sheets.items())

    raise ValueError("CSV，XLSX，XLS以外の形式には対応していません")


def _as_time_values(values, x_type):
    if x_type == "datetime":
        parsed = pd.to_datetime(pd.Series(values), errors="coerce")
        valid = parsed.dropna()
        if valid.empty:
            raise ValueError("有効な日時を含む時間軸がありません")
        return parsed, valid.min(), valid.max()

    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        raise ValueError("有効な時間軸がありません")
    return numeric, float(valid.min()), float(valid.max())


def _format_clock(value, x_type):
    if x_type == "datetime":
        timestamp = pd.Timestamp(value)
        return timestamp.strftime("%H:%M:%S.%f")[:-3] if timestamp.microsecond else timestamp.strftime("%H:%M:%S")
    return f"{float(value):g}"


def _append_windows(segments, name, start, end, interval_seconds, x_type):
    if end <= start:
        return

    index = 1
    while True:
        if x_type == "datetime":
            window_start = start + pd.to_timedelta(
                (index - 1) * interval_seconds, unit="s"
            )
            if window_start >= end:
                break
            window_end = min(
                window_start + pd.to_timedelta(interval_seconds, unit="s"),
                end,
            )
            start_value = window_start.isoformat()
            end_value = window_end.isoformat()
        else:
            window_start = start + (index - 1) * interval_seconds
            if window_start >= end:
                break
            window_end = min(window_start + interval_seconds, end)
            start_value = float(window_start)
            end_value = float(window_end)

        if len(segments) >= MAX_REGRESSION_SEGMENTS:
            raise ValueError(
                f"区間数が上限（{MAX_REGRESSION_SEGMENTS:,}）を超えました．"
                "区切り時間を長くしてください"
            )
        segments.append({
            "name": (
                f"{name} ／ {index}（"
                f"{_format_clock(window_start, x_type)}–"
                f"{_format_clock(window_end, x_type)}）"
            ),
            "start": start_value,
            "end": end_value,
            "origin": start_value,
            "exclude_end": True,
        })
        index += 1


def _build_regression_segments(prepared, interval_seconds, by_task=False):
    x_values = prepared["x_values"]
    x_type = prepared["x_type"]
    if x_type == "index":
        raise ValueError(
            "時間区切りには RecvJST と SensorElapsed_ms，またはsampling_time列が必要です"
        )
    if by_task and not prepared["tasks"]:
        raise ValueError("ログに回帰対象のタスク区間がありません")

    _, data_start, data_end = _as_time_values(x_values, x_type)
    segments = []

    if prepared["tasks"]:
        for task in prepared["tasks"]:
            task_start = pd.Timestamp(task["start"])
            task_end = pd.Timestamp(task["end"])
            clipped_start = max(task_start, pd.Timestamp(data_start))
            clipped_end = min(task_end, pd.Timestamp(data_end))
            if clipped_end > clipped_start:
                if by_task:
                    segments.append({
                        "name": (
                            f"{task.get('name') or 'タスク'}（"
                            f"{_format_clock(clipped_start, 'datetime')}–"
                            f"{_format_clock(clipped_end, 'datetime')}）"
                        ),
                        "start": clipped_start.isoformat(),
                        "end": clipped_end.isoformat(),
                        "origin": clipped_start.isoformat(),
                        "exclude_end": True,
                    })
                    continue
                _append_windows(
                    segments,
                    str(task.get("name") or "タスク"),
                    clipped_start,
                    clipped_end,
                    interval_seconds,
                    "datetime",
                )
    else:
        _append_windows(
            segments,
            "全体",
            data_start,
            data_end,
            interval_seconds,
            x_type,
        )

    if segments:
        # 区間境界のサンプルは次の区間へ割り当て，記録の最後だけ終端を含める．
        segments[-1]["exclude_end"] = False
    if len(segments) > MAX_REGRESSION_SEGMENTS:
        raise ValueError(
            f"区間数が上限（{MAX_REGRESSION_SEGMENTS:,}）を超えました．"
            "区切り時間を長くしてください"
        )
    return segments


def perform_mlx_regression(
    uploaded_files,
    has_log,
    interval_seconds,
    by_task=False,
):
    """MLX_ファイルごとに2列を描画し，タスク内の固定秒区間で回帰する．"""
    try:
        if by_task and not has_log:
            raise ValueError("タスクごとの回帰にはログファイルが必要です")
        if by_task:
            interval_seconds = None
        else:
            interval_seconds = float(interval_seconds)
            if not math.isfinite(interval_seconds) or interval_seconds <= 0:
                raise ValueError("回帰区間には0より大きい秒数を指定してください")

        filenames = [
            name for name in uploaded_files
            if name.strip().lower().startswith("mlx_")
            and name.lower().endswith(SUPPORTED_EXTENSIONS)
            and not name.lower().endswith("_log.csv")
        ]
        if not 1 <= len(filenames) <= 12:
            raise ValueError("MLX_で始まるCSV／Excelを1～12個選択してください")

        results = []
        total_segments = 0
        for filename in filenames:
            file_obj = uploaded_files[filename]
            try:
                sheets = []
                for sheet_name, dataframe in _read_mlx_sheets(file_obj, filename):
                    if dataframe.shape[1] < 2:
                        raise ValueError("先頭2列を読み込めません（2列以上必要です）")

                    axis = build_x_axis(dataframe)
                    if axis["x_type"] == "index":
                        raise ValueError(
                            "時間区切りには RecvJST と SensorElapsed_ms，"
                            "またはsampling_time列が必要です"
                        )

                    prepared = _prepare_preview_dataframe(
                        dataframe, uploaded_files, has_log
                    )
                    segments = _build_regression_segments(
                        prepared, interval_seconds, by_task
                    )
                    if by_task and not segments:
                        raise ValueError(
                            "ログとデータが重なるタスク区間がありません"
                        )
                    total_segments += len(segments)
                    if total_segments > MAX_REGRESSION_SEGMENTS:
                        raise ValueError(
                            f"全ファイルの区間数が上限（{MAX_REGRESSION_SEGMENTS:,}）を超えました．"
                            "区切り時間を長くしてください"
                        )

                    preview_sheet = _build_preview_sheet(
                        prepared["df"],
                        sheet_name,
                        [1, 2],
                        "same",
                        prepared["x_values"],
                        prepared["x_type"],
                        prepared["x_source"],
                        prepared["tasks"],
                        prepared["axis_ticks"],
                        prepared["range_start"],
                        prepared["range_end"],
                    )
                    if len(preview_sheet["series"]) != 2:
                        details = "，".join(preview_sheet["errors"])
                        raise ValueError(
                            "先頭1列目と2列目の両方に数値データが必要です"
                            + (f"（{details}）" if details else "")
                        )
                    preview_sheet["regression_segments"] = segments
                    preview_sheet["regression_segment_mode"] = (
                        "task" if by_task else "interval"
                    )
                    sheets.append(preview_sheet)

                results.append({
                    "filename": filename,
                    "type": "excel" if filename.lower().endswith((".xlsx", ".xls")) else "csv",
                    "sheets": sheets,
                })
            except Exception as error:
                results.append({
                    "filename": filename,
                    "type": "error",
                    "message": f"読み込みエラー: {error}",
                    "sheets": [],
                })
            finally:
                file_obj.seek(0)

        return {
            "analysis_type": "mlx_regression",
            "status": "success",
            "interval_seconds": interval_seconds,
            "regression_segment_mode": "task" if by_task else "interval",
            "data": results,
        }
    except Exception as error:
        return {
            "analysis_type": "mlx_regression",
            "status": "error",
            "message": f"MLX回帰分析エラー: {error}",
        }
