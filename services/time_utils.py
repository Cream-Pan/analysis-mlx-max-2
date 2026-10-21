"""CSV時刻，日時文字列，持続時間の共通変換処理．"""
import re

import pandas as pd


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
