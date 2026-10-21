from flask import Flask, abort, request, jsonify, send_from_directory
from flask_cors import CORS
import warnings
import math
import os
from pathlib import Path


from services.common import (
    UploadSizeLimitError,
    get_uploaded_files_dict,
    validate_required_files,
    validate_uploaded_file_sizes,
)
from services.settings import config
from services.file_preview_service import perform_file_preview
from services.mlx_service import process_mlx_common
from services.max_service import perform_max_evaluation
from services.ppg_service import process_ppg_to_hr, perform_ppg_hr_comparison, perform_ppg_wave_hrv_analysis
from services.ppg_acc_service import perform_ppg_acc_analysis
from services.security import (
    STATIC_ASSETS,
    is_allowed_upload_origin,
    parse_cors_origins,
)

app = Flask(__name__)
APP_ROOT = Path(__file__).resolve().parent
UPLOAD_LIMITS = config.get("upload_limits", {})
MAX_UPLOAD_FILE_BYTES = int(
    UPLOAD_LIMITS.get("max_file_size_mb", 256)
) * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = int(
    UPLOAD_LIMITS.get("max_request_size_mb", 512)
) * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_REQUEST_BYTES
CORS_ORIGINS = parse_cors_origins(
    os.environ.get("VITBUDS_CORS_ORIGINS", "")
)
if CORS_ORIGINS:
    CORS(
        app,
        resources={r"/upload": {"origins": list(CORS_ORIGINS)}}
    )
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

@app.errorhandler(413)
def handle_request_too_large(_error):
    max_request_mb = MAX_UPLOAD_REQUEST_BYTES // (1024 * 1024)
    return jsonify([{
        "analysis_type": "error",
        "status": "error",
        "message": (
            f"アップロード全体の上限（{max_request_mb} MiB）を超えています"
        )
    }]), 413


@app.route('/')
def index():
    return send_from_directory(APP_ROOT, 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    if filename not in STATIC_ASSETS:
        abort(404)
    return send_from_directory(APP_ROOT, filename)

@app.route('/upload', methods=['POST'])
def upload_files():
    origin = request.headers.get("Origin")
    same_origin = request.host_url.rstrip("/")
    if not is_allowed_upload_origin(origin, same_origin, CORS_ORIGINS):
        return jsonify([{
            "analysis_type": "error",
            "status": "error",
            "message": "許可されていない送信元からのリクエストです"
        }]), 403

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

    try:
        uploaded_files = get_uploaded_files_dict(files)
        validate_uploaded_file_sizes(
            files,
            max_file_bytes=MAX_UPLOAD_FILE_BYTES,
            max_total_bytes=MAX_UPLOAD_REQUEST_BYTES
        )
    except UploadSizeLimitError as error:
        return jsonify([{
            "analysis_type": "error",
            "status": "error",
            "message": str(error)
        }]), 413
    except ValueError as error:
        return jsonify([{
            "analysis_type": "error",
            "status": "error",
            "message": str(error)
        }]), 400

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
    debug_enabled = os.environ.get("VITBUDS_DEBUG", "").strip().lower() in {
        "1", "true", "yes"
    }
    app.run(host="127.0.0.1", debug=debug_enabled, port=5000)
