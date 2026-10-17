from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import warnings
import math


from services.common import (
    get_uploaded_files_dict,
    validate_required_files,
    perform_file_preview,
)
from services.mlx_service import process_mlx_common
from services.max_service import perform_max_evaluation
from services.ppg_service import process_ppg_to_hr, perform_ppg_hr_comparison, perform_ppg_wave_hrv_analysis
from services.ppg_acc_service import perform_ppg_acc_analysis

app = Flask(__name__)
CORS(app)
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

@app.route('/upload', methods=['POST'])
def upload_files():
    analysis_types = request.form.getlist('analysis_types[]')
    files = request.files.getlist('files')
    has_log_value = request.form.get('has_log', 'false').strip().lower()
    if has_log_value not in {'true', 'false'}:
        return jsonify([{
            "analysis_type": "error", "status": "error",
            "message": "ログ使用の指定が不正です"
        }]), 400
    has_log = has_log_value == 'true'

    try:
        interval_value = float(request.form.get('interval_min', 5))
        analysis_start_offset_sec = float(
            request.form.get('analysis_start_offset_sec', 0)
        )
        analysis_duration_sec = float(
            request.form.get('analysis_duration_sec', 0)
        )
        if not math.isfinite(interval_value) or not interval_value.is_integer():
            raise ValueError
        interval_min = int(interval_value)
        if not math.isfinite(analysis_start_offset_sec) or analysis_start_offset_sec < 0:
            raise ValueError
        if not math.isfinite(analysis_duration_sec) or analysis_duration_sec < 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return jsonify([{
            "analysis_type": "error", "status": "error",
            "message": "区切り分数，開始オフセット，解析時間は有効な数値で指定してください"
        }]), 400

    interval_modes = {'mlx_evaluation', 'mlx_reevaluation', 'max_evaluation',
                      'ppg_analysis', 'ppg_hr_analysis'}
    if not has_log and interval_min <= 0 and any(
        mode in interval_modes for mode in analysis_types
    ):
        return jsonify([{
            "analysis_type": "error", "status": "error",
            "message": "区切り分数には 1 以上の整数を指定してください"
        }]), 400
    preview_axis = request.form.get("preview_axis", "index")
    preview_scale = request.form.get("preview_scale", "same")
    preview_column_values = request.form.getlist('preview_columns[]')

    try:
        preview_columns = sorted({
            int(value)
            for value in preview_column_values
            if str(value).strip()
        })
    except ValueError:
        preview_columns = []

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

        elif atype == 'ppg_analysis':
            results.append(
                perform_ppg_hr_comparison(
                    uploaded_files,
                    has_log,
                    interval_min,
                    analysis_start_offset_sec,
                    analysis_duration_sec
                )
            )

        elif atype == 'ppg_hr_analysis':
            results.append(
                perform_ppg_wave_hrv_analysis(
                    uploaded_files,
                    has_log,
                    interval_min,
                    analysis_start_offset_sec,
                    analysis_duration_sec
                )
            )

        elif atype == 'ppg_to_hr':
            results.append(
                process_ppg_to_hr(
                    uploaded_files,
                    has_log,
                    interval_min,
                    analysis_start_offset_sec,
                    analysis_duration_sec
                )
            )

        elif atype == 'ppg_acc_analysis':
            results.append(
                perform_ppg_acc_analysis(
                    uploaded_files,
                    has_log,
                    interval_min,
                    analysis_start_offset_sec,
                    analysis_duration_sec
                )
            )

        elif atype == 'show_files':
            if (
                not preview_columns or
                any(column_number <= 0 for column_number in preview_columns)
            ):
                results.append({
                    "analysis_type": atype,
                    "status": "error",
                    "message": "プロットする列番号を1つ以上指定してください"
                })
                continue

            results.append({
                "analysis_type": atype,
                "status": "success",
                "data": perform_file_preview(
                    uploaded_files,
                    preview_columns,
                    preview_axis,
                    preview_scale,
                    has_log
                )
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