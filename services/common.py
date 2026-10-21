import io
import pandas as pd

from services.settings import config
from services.time_utils import parse_datetime_or_duration

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


class UploadSizeLimitError(ValueError):
    """アップロード容量の上限を超えた場合に送出する．"""


def get_uploaded_files_dict(files):
    uploaded = {}
    seen_names = {}
    duplicates = []

    for file_obj in files:
        raw_name = str(getattr(file_obj, "filename", "") or "")
        filename = raw_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename or filename in {".", ".."} or "\x00" in filename:
            raise ValueError("ファイル名を確認できないファイルがあります")

        normalized_name = filename.casefold()
        if normalized_name in seen_names:
            duplicates.append(filename)
            continue

        seen_names[normalized_name] = filename
        uploaded[filename] = file_obj

    if duplicates:
        names = ", ".join(dict.fromkeys(duplicates))
        raise ValueError(f"同じファイル名のファイルが複数選択されています: {names}")

    return uploaded


def validate_uploaded_file_sizes(files, max_file_bytes, max_total_bytes):
    """各ファイルと合計の容量を確認し，読み込み位置を維持する．"""
    total_bytes = 0

    for file_obj in files:
        stream = getattr(file_obj, "stream", file_obj)
        position = None
        try:
            position = stream.tell()
            stream.seek(0, io.SEEK_END)
            file_size = stream.tell()
        except (AttributeError, OSError, ValueError) as error:
            raise ValueError("アップロードファイルの容量を確認できません") from error
        finally:
            if position is not None:
                stream.seek(position)

        filename = str(getattr(file_obj, "filename", "") or "ファイル")
        if file_size > max_file_bytes:
            raise UploadSizeLimitError(
                f"1ファイルの上限（{max_file_bytes // (1024 * 1024)} MiB）を超えています: {filename}"
            )

        total_bytes += file_size
        if total_bytes > max_total_bytes:
            raise UploadSizeLimitError(
                f"合計アップロード容量の上限（{max_total_bytes // (1024 * 1024)} MiB）を超えています"
            )


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
