from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import io
import re
import json
import os
import warnings
from sklearn.metrics import mean_squared_error, mean_absolute_error

app = Flask(__name__)
CORS(app)
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)


# ----------------------------------------
# 共通: 設定とアップロードファイル
# ----------------------------------------
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
    """
    value: '2025/01/01 12:34:56.789' または '32:19.3' 等
    base_day: pandas.Timestamp (datetime)
    """
    s = str(value).strip().replace('"', '').replace('=', '')

    # 絶対時刻
    dt = pd.to_datetime(s, errors='coerce')
    if pd.notna(dt):
        return dt

    # Excel シリアル
    try:
        num = float(s)
        return pd.Timestamp('1899-12-30') + pd.to_timedelta(num, unit='D')
    except Exception:
        pass

    # 分:秒(.f) or 時:分:秒(.f)
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
    """タスク分割リストを作成（ログあり/なし両対応）"""
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
    # ログなし
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
    """体温データの読み込み"""
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


# ----------------------------------------
# MLX 共通処理
# ----------------------------------------
def load_mlx_device_data(uploaded_files, mode, has_log, t1=None):
    """MLX デバイスデータを読み込んで時系列 DataFrame に整形"""
    if mode == 'normal':
        target_filename = resolve_mlx_evaluation_file(uploaded_files)
        target_file = uploaded_files[target_filename]
        lower_name = target_filename.lower()

        # -----------------------------
        # Excel の場合
        # -----------------------------
        if lower_name.endswith(('.xlsx', '.xls')):
            xls = pd.ExcelFile(io.BytesIO(target_file.read()))
            target_file.seek(0)

            sheet_candidates = config.get('mlx_sheet_candidates', [])
            sheet = next((s for s in sheet_candidates if s in xls.sheet_names), None)
            if sheet is None:
                raise ValueError("MLX シートが見つかりません")
            
            recvjst_h = pd.read_excel(
                io.BytesIO(target_file.read()),
                sheet_name=sheet,
                header=None,
                skiprows=1,
                nrows=1,
                usecols="H"
            )
            target_file.seek(0)

            recvjst_raw = recvjst_h.iloc[0, 0]
            if not has_log:
                t1 = parse_datetime_or_duration(recvjst_raw)

            f2 = pd.read_excel(
                io.BytesIO(target_file.read()),
                sheet_name=sheet,
                header=None,
                skiprows=1,
                nrows=1,
                usecols="F"
            )
            target_file.seek(0)

            raw_offset = f2.iloc[0, 0]
            try:
                offset_td = pd.to_timedelta(float(raw_offset), unit='s')
            except Exception:
                offset_td = pd.to_timedelta("0s")

            df_raw = pd.read_excel(io.BytesIO(target_file.read()), sheet_name=sheet)
            target_file.seek(0)

            if len(df_raw.columns) < 8:
                raise ValueError(f"{target_filename} の列数が不足しています")

            amb_col = df_raw.columns[0]
            obj_col = df_raw.columns[1]
            elap_col = df_raw.columns[4]

            title = f"MLX評価 結果 ({target_filename} / {sheet})"

        # -----------------------------
        # CSV の場合
        # -----------------------------
        elif lower_name.endswith('.csv'):
            try:
                df_raw = pd.read_csv(io.BytesIO(target_file.read()))
                target_file.seek(0)
            except Exception:
                target_file.seek(0)
                df_raw = pd.read_csv(io.BytesIO(target_file.read()), encoding='shift_jis')
                target_file.seek(0)

            if len(df_raw.columns) < 5:
                raise ValueError(f"{target_filename} の列数が不足しています")

            # 体裁が同じ前提なら列位置で読む
            amb_col = df_raw.columns[0]
            obj_col = df_raw.columns[1]
            elap_col = df_raw.columns[4]

            # ログなしなら RecvJST 列先頭をそのまま基準時刻にする
            if not has_log:
                recvjst_col = df_raw.columns[7]   # H列
                recvjst_raw = df_raw.iloc[0, 7]
                t1 = parse_datetime_or_duration(recvjst_raw)

            # csv 側に開始オフセット列がある場合だけ使う
            if len(df_raw.columns) > 5:
                raw_offset = df_raw.iloc[0, 5]
                offset_td = pd.to_timedelta(raw_offset, unit='s', errors='coerce')
                if pd.isna(offset_td):
                    offset_td = pd.to_timedelta("0s")
            else:
                offset_td = pd.to_timedelta("0s")

            title = f"MLX評価 結果 ({target_filename})"

        else:
            raise ValueError("MLX 生データファイルの形式が未対応です")

    else:
        try:
            df_raw = pd.read_csv(io.BytesIO(uploaded_files['mlx_re.csv'].read()))
            uploaded_files['mlx_re.csv'].seek(0)
        except Exception:
            uploaded_files['mlx_re.csv'].seek(0)
            df_raw = pd.read_csv(io.BytesIO(uploaded_files['mlx_re.csv'].read()), encoding='shift_jis')
            uploaded_files['mlx_re.csv'].seek(0)

        if len(df_raw.columns) < 9:
            raise ValueError("mlx_re.csv の列数が不足しています")

        raw_offset = df_raw.iloc[0, 5]
        offset_td = pd.to_timedelta(raw_offset, unit='s', errors='coerce')
        if pd.isna(offset_td):
            raise ValueError("mlx_re.csv の F 列先頭値が数値ではありません")

        amb_col = df_raw.columns[0]
        elap_col = df_raw.columns[4]
        obj_col = df_raw.columns[8]

        if not has_log:
            recvjst_raw = df_raw.iloc[0, 7]   # H列
            t1 = parse_datetime_or_duration(recvjst_raw)

        raw_offset = df_raw.iloc[0, 5]
        offset_td = pd.to_timedelta(raw_offset, unit='s', errors='coerce')
        if pd.isna(offset_td):
            offset_td = pd.to_timedelta("0s")

        title = "MLX修正後評価 結果 (mlx_re.csv)"

        if t1 is None:
            raise ValueError("MLX の基準時刻 t1 を決定できませんでした")

    time_1 = t1 + offset_td

    sensor_td = pd.to_timedelta(df_raw[elap_col], unit='ms', errors='coerce')
    if sensor_td.isna().all():
        raise ValueError("経過時間列の変換に失敗しました")

    diff_td = sensor_td.diff().fillna(pd.Timedelta(seconds=0))

    df_dev = pd.DataFrame({
        'Timestamp': time_1 + diff_td.cumsum(),
        'Ambient_C': pd.to_numeric(df_raw[amb_col], errors='coerce'),
        'Object_C': pd.to_numeric(df_raw[obj_col], errors='coerce')
    }).dropna(subset=['Timestamp', 'Ambient_C', 'Object_C']).set_index('Timestamp').sort_index()

    if df_dev.empty:
        raise ValueError("MLX デバイスデータが空です")

    return df_dev, title

def resolve_mlx_evaluation_file(uploaded_files):
    """
    mlx_evaluation 用の入力ファイルを自動選択する
    """
    # 1. 固定候補名
    fixed_candidates = config.get("mlx_evaluation_file_candidates", [])
    for name in fixed_candidates:
        if name in uploaded_files:
            return name

    # 2. キーワード一致
    keywords = [k.lower() for k in config.get("mlx_evaluation_filename_keywords", [])]

    for filename in uploaded_files.keys():
        lower_name = filename.lower()

        if not (lower_name.endswith(".csv") or lower_name.endswith(".xlsx") or lower_name.endswith(".xls")):
            continue

        if all(keyword in lower_name for keyword in keywords):
            return filename

    raise ValueError("mlx_evaluation 用の MLX 生データファイルが見つかりません")


def process_mlx_common(uploaded_files, mode, has_log, interval_min):
    """MLX評価の共通処理（通常版と修正版）"""
    try:
        # 1. 真値(体温)
        df_true = load_body_temp(uploaded_files['body_temperature.csv'])
        if df_true.empty:
            raise ValueError("body_temperature.csv が空です")

        base_day = df_true.index.min().normalize()

        # 2. 開始時刻
        if has_log:
            log_df = pd.read_csv(io.BytesIO(uploaded_files['log.csv'].read()))
            uploaded_files['log.csv'].seek(0)

            if 'Task_Name' not in log_df.columns or 'Timestamp' not in log_df.columns:
                raise ValueError("log.csv に必要な列(Task_Name, Timestamp)がありません")

            sensor_start = log_df[log_df['Task_Name'].astype(str).str.replace('"', '', regex=False) == 'BLE_START_TIME (Main)']
            if sensor_start.empty:
                raise ValueError("BLE_START_TIME (Main) が見つかりません")

            sensor_start_raw = sensor_start['Timestamp'].iloc[0]
            t1 = parse_datetime_or_duration(sensor_start_raw, base_day)
        else:
            t1 = None

        # 3. デバイスデータ
        df_dev, title = load_mlx_device_data(uploaded_files, mode, has_log, t1)

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
        pred = df_dev.reindex(df_true.index.union(df_dev.index)).interpolate('time').reindex(df_true.index)
        comp = pd.DataFrame({
            'true': df_true['temp'],
            'pred': pred['Object_C']
        }).dropna()

        if comp.empty:
            raise ValueError("補間後の有効データがありません")

        # 6. タスクごとの評価
        results = []
        for task in tasks:
            start_t = task['Start_Time']
            end_t = task['End_Time']
            task_name = task['Task_Name']

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
                "mae": float(mean_absolute_error(seg['true'], seg['pred'])),
                "rmse": float(np.sqrt(mean_squared_error(seg['true'], seg['pred']))),
                "mean_object_c": float(seg_dev['Object_C'].mean()),
                "mean_ambient_c": float(seg_dev['Ambient_C'].mean()),
                "mean_body_temp": float(seg_true['temp'].mean())
            })

        return {"status": "success", "data": results, "title": title}

    except Exception as e:
        return {"status": "error", "message": f"MLX解析エラー: {str(e)}"}


# ----------------------------------------
# MAX 評価
# ----------------------------------------
def load_ecg_csv(f_obj):
    df = pd.read_csv(
        io.BytesIO(f_obj.read()),
        usecols=['Timestamp', 'HeartRate_BPM']
    )
    f_obj.seek(0)

    df = df.dropna(subset=['HeartRate_BPM']).copy()
    cleaned_timestamp = df['Timestamp'].astype(str).str.replace('="', '', regex=False).str.replace('"', '', regex=False)
    df['Timestamp'] = pd.to_datetime(cleaned_timestamp, errors='coerce')
    df['HeartRate_BPM'] = pd.to_numeric(df['HeartRate_BPM'], errors='coerce')
    df = df.dropna(subset=['Timestamp', 'HeartRate_BPM'])
    df = df.set_index('Timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df[['HeartRate_BPM']].rename(columns={'HeartRate_BPM': 'HR'})


def load_ppg_csv(f_obj):
    df = pd.read_csv(
        io.BytesIO(f_obj.read()),
        usecols=['RecvJST', 'HR_BPM']
    )
    f_obj.seek(0)

    df['RecvJST'] = pd.to_datetime(df['RecvJST'], errors='coerce')
    df['HR_BPM'] = pd.to_numeric(df['HR_BPM'], errors='coerce')
    df = df.dropna(subset=['RecvJST', 'HR_BPM'])
    df = df.set_index('RecvJST').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df[['HR_BPM']].rename(columns={'HR_BPM': 'HR'})


def evaluate_max_device(df_true, df_dev, start_t, end_t):
    """MAX評価用の単一比較．フロントの表示形式に合わせて返す"""
    try:
        t_sub = df_true.loc[start_t:end_t]
        d_sub = df_dev.loc[start_t:end_t]

        if t_sub.empty or d_sub.empty:
            return {
                "raw_mae": None,
                "raw_rmse": None,
                "raw_count": 0,
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": "データ不足"
            }

        combined_idx = t_sub.index.union(d_sub.index)

        # HR 列だけを補間対象にする
        interp_true = (
            t_sub[['HR']]
            .reindex(combined_idx)
            .interpolate(method='time')
            .reindex(d_sub.index)
        )

        comp = pd.DataFrame({
            'true': interp_true['HR'],
            'dev': d_sub['HR']
        }).dropna()

        if comp.empty:
            return {
                "raw_mae": None,
                "raw_rmse": None,
                "raw_count": 0,
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": "同期データなし"
            }

        raw_mae = float(mean_absolute_error(comp['true'], comp['dev']))
        raw_rmse = float(np.sqrt(mean_squared_error(comp['true'], comp['dev'])))

        resampled = comp.resample('1min', origin=start_t).mean().dropna()
        if resampled.empty:
            return {
                "raw_mae": raw_mae,
                "raw_rmse": raw_rmse,
                "raw_count": len(comp),
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": None
            }

        resampled_mae = float(mean_absolute_error(resampled['true'], resampled['dev']))
        resampled_rmse = float(np.sqrt(mean_squared_error(resampled['true'], resampled['dev'])))

        return {
            "raw_mae": raw_mae,
            "raw_rmse": raw_rmse,
            "raw_count": len(comp),
            "resampled_mae": resampled_mae,
            "resampled_rmse": resampled_rmse,
            "resampled_count": len(resampled),
            "error": None
        }

    except Exception as e:
        return {
            "raw_mae": None,
            "raw_rmse": None,
            "raw_count": 0,
            "resampled_mae": None,
            "resampled_rmse": None,
            "resampled_count": 0,
            "error": str(e)
        }


def perform_max_evaluation(uploaded_files, has_log, interval_min):
    try:
        df_ecg = load_ecg_csv(uploaded_files['ecg.csv'])
        df_ppg = load_ppg_csv(uploaded_files['PPG_BPM.csv'])
        df_fin = load_ppg_csv(uploaded_files['PPG_fin_BPM.csv'])

        start_limit = max(df_ecg.index.min(), df_ppg.index.min(), df_fin.index.min())
        end_limit = min(df_ecg.index.max(), df_ppg.index.max(), df_fin.index.max())

        if start_limit >= end_limit:
            raise ValueError("比較可能な時刻範囲がありません")

        tasks = load_log_tasks(
            uploaded_files,
            has_log,
            interval_min,
            start_limit,
            end_limit,
            start_limit.normalize()
        )

        results = []
        for task in tasks:
            s_t = task['Start_Time']
            e_t = task['End_Time']

            results.append({
                "task": task['Task_Name'],
                "eval_1": {
                    **evaluate_max_device(df_ecg, df_ppg, s_t, e_t),
                    "device_name": "ECG vs PPG_BPM"
                },
                "eval_2": {
                    **evaluate_max_device(df_fin, df_ppg, s_t, e_t),
                    "device_name": "PPG_fin vs PPG_BPM"
                }
            })

        return {
            "analysis_type": "max_evaluation",
            "status": "success",
            "data": results,
            "title": "MAX評価 結果 (タスク別)"
        }

    except Exception as e:
        return {
            "analysis_type": "max_evaluation",
            "status": "error",
            "message": f"MAX解析エラー: {str(e)}"
        }


# ----------------------------------------
# エンドポイント
# ----------------------------------------
@app.route('/upload', methods=['POST'])
def upload_files():
    analysis_types = request.form.getlist('analysis_types[]')
    files = request.files.getlist('files')
    has_log = request.form.get('has_log') == 'true'
    interval_min = int(request.form.get('interval_min', 5))

    if not files:
        return jsonify([{
            "analysis_type": "error",
            "status": "error",
            "message": "ファイルが選択されていません"
        }]), 400

    if not analysis_types:
        return jsonify([{
            "analysis_type": "error",
            "status": "error",
            "message": "解析タイプが選択されていません"
        }]), 400

    uploaded_files = get_uploaded_files_dict(files)
    results = []

    for atype in analysis_types:
        ok, err = validate_required_files(uploaded_files, atype, has_log)
        if not ok:
            results.append({
                "analysis_type": atype,
                "status": "error",
                "message": err
            })
            continue

        if atype == 'mlx_evaluation':
            result = process_mlx_common(uploaded_files, 'normal', has_log, interval_min)
            result["analysis_type"] = atype
            results.append(result)

        elif atype == 'mlx_reevaluation':
            result = process_mlx_common(uploaded_files, 'corrected', has_log, interval_min)
            result["analysis_type"] = atype
            results.append(result)

        elif atype == 'max_evaluation':
            results.append(perform_max_evaluation(uploaded_files, has_log, interval_min))

        elif atype == 'show_files':
            results.append({
                "analysis_type": atype,
                "status": "success",
                "data": perform_file_preview(uploaded_files)
            })

        else:
            results.append({
                "analysis_type": atype,
                "status": "error",
                "message": "未対応の解析タイプです"
            })

    for f in files:
        f.seek(0)

    return jsonify(results)


if __name__ == '__main__':
    app.run(debug=True, port=5000)