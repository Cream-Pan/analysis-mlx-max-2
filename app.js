document.addEventListener('DOMContentLoaded', async () => {

    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const resultDiv = document.getElementById('result');
    const requiredMsg = document.getElementById('required-files-msg');
    const logCheckbox = document.getElementById('hasLogFile');
    const intervalWrapper = document.getElementById('interval-wrapper');
    const intervalInput = document.getElementById('intervalMin');
    const submitButton = uploadForm.querySelector('button[type="submit"]');

    let config = null;

    // -----------------------------
    // 共通ヘルパー
    // -----------------------------
    function normalizeFileName(name) {
        return String(name).trim().toLowerCase();
    }

    function getSelectedAnalysisType() {
        const selected = document.querySelector('input[name="analysis_type"]:checked');
        return selected ? selected.value : null;
    }

    function getRequiredFiles(type, hasLog) {
        if (!config || !config.required_files) return [];

        const requiredList = [...(config.required_files[type] || [])];
        if (hasLog && !requiredList.includes('log.csv')) {
            requiredList.unshift('log.csv');
        }
        return requiredList;
    }

    function getSelectedFileNames() {
        return Array.from(fileInput.files).map(file => file.name);
    }

    function validateRequiredFiles() {
        const type = getSelectedAnalysisType();
        if (!type) {
            return { ok: false, message: '実行したい解析メニューを選択してください。' };
        }

        const hasLog = logCheckbox.checked;
        const requiredFiles = getRequiredFiles(type, hasLog);
        const selectedNames = getSelectedFileNames().map(normalizeFileName);

        const missingFiles = requiredFiles.filter(required =>
            !selectedNames.includes(normalizeFileName(required))
        );

        if (missingFiles.length > 0) {
            return {
                ok: false,
                message: `必要なファイルが不足しています：${missingFiles.join(' , ')}`
            };
        }

        return { ok: true, message: '' };
    }

    function setSubmitEnabled(enabled) {
        if (submitButton) {
            submitButton.disabled = !enabled;
        }
    }

    try {
        const response = await fetch('config.json');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        config = await response.json();
        // console.log('Config loaded:', config);

        setSubmitEnabled(true);
        updateRequiredFiles();
        updateIntervalInputVisibility();
    } catch (error) {
        console.error('config.json の読み込みに失敗しました:', error);
        requiredMsg.innerHTML = '<span style="color:red;">Configファイルの読み込みに失敗しました</span>';
        setSubmitEnabled(false);
    }

    function updateIntervalInputVisibility() {
    if (logCheckbox.checked) {
        intervalWrapper.style.display = 'none';
    } else {
        intervalWrapper.style.display = 'flex';
    }
}

    // メッセージを更新する関数
    function updateRequiredFiles() {
        if (!config) {
            requiredMsg.innerHTML = '<span style="color:red;">Configファイルが未読み込みです</span>';
            return;
        }
        
        const type = getSelectedAnalysisType();
        if (!type) {
            requiredMsg.textContent = '必要なファイル：';
            return;
        }

        const hasLog = logCheckbox.checked;
        const requiredList = getRequiredFiles(type, hasLog);
        const displayList = requiredList.map(name => `<b>${name}</b>`);
        let message = displayList.length > 0 ? displayList.join(' , ') : '任意';

        const note = config.required_file_notes?.[type];
        if (note) {
            message += `<br><span style="color:#666;">補足：${note}</span>`;
        }

        requiredMsg.innerHTML = `必要なファイル： ${message}`;
    }
    document.querySelectorAll('input[name="analysis_type"]').forEach(radio => {
        radio.addEventListener('change', () => {
            const type = getSelectedAnalysisType();

            if (type === 'ppg_to_hr') {
                logCheckbox.checked = false;
            }

            updateRequiredFiles();
            updateIntervalInputVisibility();
        });
    });
    logCheckbox.addEventListener('change', () => {
        updateRequiredFiles();
        updateIntervalInputVisibility();
    });

    // 画像保存
    window.saveResultsAsPng = saveResultsAsPng;

    function saveResultsAsPng(elementId) {
        const element = document.getElementById(elementId);

        if (!element) {
            alert(`エラー: ID "${elementId}" の要素が見つかりません。`);
            return;
        }

        html2canvas(element, { 
            scale: 2, // 高解像度でキャプチャ
            useCORS: true, // クロスオリジン画像を許可 (グラフ画像などに対応)
            // キャプチャ対象がグラフ（Canvas）である場合、Canvasをそのままキャプチャするオプション
            allowTaint: true, 
            ignoreElements: (element) => {
                // 保存ボタン自体は画像に含めない
                return element.tagName === 'BUTTON' && element.textContent === 'PNG保存';
            }
        }).then(canvas => {
            const dataURL = canvas.toDataURL('image/png');
            
            // ダウンロード用のリンクを作成し、自動クリック
            const a = document.createElement('a');
            a.href = dataURL;
            a.download = `${elementId}_${new Date().toISOString().slice(0, 10)}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }).catch(err => {
            console.error('PNG保存中にエラーが発生しました:', err);
            alert(`PNG保存エラーが発生しました: ${err.message}`);
        });
    }

    function downloadCsvText(filename, csvText) {
        const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        URL.revokeObjectURL(url);
    }

    function displayPpgToHrResult(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';

        const uniqueId = `ppg-to-hr-${Date.now()}`;
        const irCanvasId = `${uniqueId}-ir`;
        const hrCanvasId = `${uniqueId}-hr`;

        let html = `<h3>${result.title}</h3>`;

        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
            resultEl.innerHTML = html;
            resultDiv.appendChild(resultEl);
            return;
        }

        const fs = result.summary?.fs ?? 'N/A';
        const overallCorr = result.summary?.overall_corr;
        const corrText = (overallCorr === null || overallCorr === undefined)
            ? 'N/A'
            : Number(overallCorr).toFixed(4);

        html += `
            <table>
                <thead><tr><th>項目</th><th>値</th></tr></thead>
                <tbody>
                    <tr><td>Fs</td><td>${fs} Hz</td></tr>
                    <tr><td>全体相関係数 (IR vs RED)</td><td>${corrText}</td></tr>
                </tbody>
            </table>

            <div class="chart-container" style="margin-top: 20px;">
                <canvas id="${irCanvasId}"></canvas>
            </div>

            <div class="chart-container" style="margin-top: 20px;">
                <canvas id="${hrCanvasId}"></canvas>
            </div>

            <div style="text-align: right; margin-top: 10px;">
                <button class="download-csv-btn">CSVダウンロード</button>
            </div>
        `;

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);

        const makeAnnotations = (segments) => {
            const annotations = {};
            (segments || []).forEach((seg, idx) => {
                annotations[`line${idx}`] = {
                    type: 'line',
                    xMin: seg.start_time,
                    xMax: seg.start_time,
                    borderColor: 'gold',
                    borderWidth: 1,
                    borderDash: [6, 6]
                };
            });
            return annotations;
        };

        const annotations = makeAnnotations(result.task_segments);

        new Chart(document.getElementById(irCanvasId), {
            type: 'line',
            data: {
                labels: result.plot_data.time,
                datasets: [
                    {
                        label: 'Raw IR',
                        data: result.plot_data.ir,
                        pointRadius: 0,
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                parsing: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            displayFormats: { second: 'HH:mm:ss' }
                        }
                    },
                    y: {
                        title: { display: true, text: 'IR Value' }
                    }
                },
                plugins: {
                    legend: { display: true },
                    annotation: { annotations }
                }
            }
        });

        new Chart(document.getElementById(hrCanvasId), {
            type: 'line',
            data: {
                labels: result.plot_data.time,
                datasets: [
                    {
                        label: 'Estimated HR',
                        data: result.plot_data.hr,
                        pointRadius: 0,
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                parsing: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            displayFormats: { second: 'HH:mm:ss' }
                        }
                    },
                    y: {
                        suggestedMin: 40,
                        suggestedMax: 180,
                        title: { display: true, text: 'BPM' }
                    }
                },
                plugins: {
                    legend: { display: true },
                    annotation: { annotations }
                }
            }
        });

        const btn = resultEl.querySelector('.download-csv-btn');
        btn.addEventListener('click', () => {
            downloadCsvText(result.download.filename, result.download.csv_text);
        });
    }

    function displayPpgAnalysis(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';

        let html = `<h3>${result.title}</h3>`;

        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
            resultEl.innerHTML = html;
            resultDiv.appendChild(resultEl);
            return;
        }

        result.data.forEach(task_result => {
            html += `<h4>タスク: ${task_result.task}</h4>`;
            html += '<table>';
            html += '<thead>';
            html += '<tr>';
            html += '<th>比較</th>';
            html += '<th>元データ</th>';
            html += '<th>1分平均</th>';
            html += '</tr>';
            html += '</thead>';
            html += '<tbody>';

            task_result.comparisons.forEach(comp => {
                let rawCell = '';
                if (comp.error) {
                    rawCell = `<span style="color: orange;">${comp.error} (N=${comp.raw_count})</span>`;
                } else {
                    rawCell = `MAE: ${formatMaxMetric(comp.raw_mae)}<br>RMSE: ${formatMaxMetric(comp.raw_rmse)}<br>(N=${comp.raw_count})`;
                }

                let resampledCell = '';
                if (comp.error || comp.resampled_count === 0) {
                    resampledCell = `<span style="color: orange;">${comp.error || 'データなし'} (N=${comp.resampled_count})</span>`;
                } else {
                    resampledCell = `MAE: ${formatMaxMetric(comp.resampled_mae)}<br>RMSE: ${formatMaxMetric(comp.resampled_rmse)}<br>(N=${comp.resampled_count})`;
                }

                html += `
                    <tr>
                        <td>${comp.device_name}</td>
                        <td>${rawCell}</td>
                        <td>${resampledCell}</td>
                    </tr>
                `;
            });

            html += '</tbody></table>';
        });

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

    // 汎用エラーを表示する関数
    function displayError(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';

        const errorMsg = result.message || '予期せぬエラーが発生しました。';
        const typeLabel = result.analysis_type ? `[${result.analysis_type}] ` : '';

        resultEl.innerHTML = `
            <h3 style="color: red;">解析エラー</h3>
            <p style="color: red; font-weight: bold;">${typeLabel}${errorMsg}</p>
            <hr>
            <p style="font-size: 0.9em;">ファイルの形式や、config.jsonの設定を確認してください。</p>
        `;
        resultDiv.appendChild(resultEl);
    }

    // MAE/RMSE の値に応じてスタイルを適用するヘルパー関数
    function formatMlxMetric(value) {
        if (value === null) {
            return 'N/A (データなし)';
        }
        const numericValue = parseFloat(value);
        const text = numericValue.toFixed(4);
        if (numericValue <= 0.3) {
            return `<span style="color: green; font-weight: bold;">${text}</span>`;
        } else if (numericValue > 1.0) {
            return `<span style="color: red; font-weight: bold;">${text}</span>`;
        } else {
            return text; 
        }
    }

    function formatMaxMetric(value) {
        if (value === null) {
            return 'N/A (データなし)';
        }
        const numericValue = parseFloat(value);
        const text = numericValue.toFixed(4);

        if (numericValue <= 5.0) {
            return `<span style="color: green; font-weight: bold;">${text}</span>`;
        } else {
            return `<span style="color: red; font-weight: bold;">${text}</span>`;
        }
    }

    // ファイルプレビューの結果を表示する関数
    function displayFilePreview(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        let html = `<h3>ファイル内容の表示</h3>`;

        if (result.status === 'error' || !result.data) {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message || 'データを表示できません'}</p>`;
        } else {
            result.data.forEach(file => { // result.data はファイルのリスト
                html += `<h4>${file.filename}</h4>`;
                
                if (file.sheets && Array.isArray(file.sheets)) {
                    file.sheets.forEach(sheet => {
                        if (sheet.sheet_name) {
                            const safeSheetName = String(sheet.sheet_name).replace(/</g, "&lt;").replace(/>/g, "&gt;");
                            html += `<h5 style="margin:0.5em 0 0.2em 1.5em;">シート: ${safeSheetName}</h5>`;
                        }
                        html += '<ul>';
                        if (sheet.data && Array.isArray(sheet.data)) {
                            sheet.data.forEach(item => {
                                const safeItem = String(item).replace(/</g, "&lt;").replace(/>/g, "&gt;");
                                html += `<li>${safeItem}</li>`;
                            });
                        } else {
                            html += '<li>(データがありません)</li>';
                        }
                        html += '</ul>';
                    });
                }
            });
        }
        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

    //MLX評価の結果を表示する関数
    function displayMlxEvaluation(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        const uniqueId = `${result.analysis_type}-${Date.now()}`;
        resultEl.id = uniqueId;

        let html = `<h3>${result.title}</h3>`;
        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
        } else {
            result.data.forEach(task_result => {
                html += `<h4>タスク: ${task_result.task}</h4>`;
                html += '<table>';
                html += '<thead><tr><th>指標</th><th>値</th></tr></thead>';
                html += '<tbody>';
                html += `<tr><td>有効データペア数</td><td>${task_result.count}</td></tr>`;
                const mae_str = formatMlxMetric(task_result.mae);
                const rmse_str = formatMlxMetric(task_result.rmse);
                html += `<tr><td>MAE (平均絶対誤差)</td><td>${mae_str}</td></tr>`;
                html += `<tr><td>RMSE (二乗平均平方根誤差)</td><td>${rmse_str}</td></tr>`;
                html += `<tr><td>BodyTemp 平均</td><td>${task_result.mean_body_temp?.toFixed(3) ?? 'N/A'}</td></tr>`;
                html += `<tr><td>Object_C 平均</td><td>${task_result.mean_object_c?.toFixed(3) ?? 'N/A'}</td></tr>`;
                html += `<tr><td>Ambient_C 平均</td><td>${task_result.mean_ambient_c?.toFixed(3) ?? 'N/A'}</td></tr>`;
                html += '</tbody></table>';
            });
            html += `<div style="text-align: right; margin-top: 10px;">
                    <button onclick="saveResultsAsPng('${uniqueId}')">PNG保存</button>
                 </div>`;
        }

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

    //MAX評価の結果を表示する関数
    function displayMaxEvaluation(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        const uniqueId = `result-${result.analysis_type}-${Date.now()}`;
        resultEl.id = uniqueId;
        let html = `<h3>${result.title}</h3>`;
        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
        } else{
            result.data.forEach(task_result => {
                html += `<h4>タスク: ${task_result.task}</h4>`;
                const eval_vs_ecg = task_result.eval_1;
                const eval_vs_fin = task_result.eval_2;
                html += '<table>';
                html += '<thead>';
                html += '<tr>';
                html += '<th></th>';
                html += `<th>${eval_vs_ecg.device_name}</th>`;
                html += `<th>${eval_vs_fin.device_name}</th>`;
                html += '</tr>';
                html += '</thead>';
                html += '<tbody>';
                // --- 行1: 元データ ---
                html += '<tr>';
                html += '<td>元データ</td>';
                // vsECG (元データ)
                if (eval_vs_ecg.error) {
                    html += `<td style="color: orange;">${eval_vs_ecg.error} (N=${eval_vs_ecg.raw_count})</td>`;
                } else {
                    html += `<td>MAE: ${formatMaxMetric(eval_vs_ecg.raw_mae)}<br>RMSE: ${formatMaxMetric(eval_vs_ecg.raw_rmse)}<br>(N=${eval_vs_ecg.raw_count})</td>`;
                }
                // vsPPG_fin (元データ)
                if (eval_vs_fin.error) {
                    html += `<td style="color: orange;">${eval_vs_fin.error} (N=${eval_vs_fin.raw_count})</td>`;
                } else {
                    html += `<td>MAE: ${formatMaxMetric(eval_vs_fin.raw_mae)}<br>RMSE: ${formatMaxMetric(eval_vs_fin.raw_rmse)}<br>(N=${eval_vs_fin.raw_count})</td>`;
                }
                html += '</tr>';
                // --- 行2: 1分平均 ---
                html += '<tr>';
                html += '<td>1分平均</td>';
                // vsECG (1分平均)
                if (eval_vs_ecg.error || eval_vs_ecg.resampled_count === 0) {
                    html += `<td style="color: orange;">${eval_vs_ecg.error || 'データなし'} (N=${eval_vs_ecg.resampled_count})</td>`;
                } else {
                    html += `<td>MAE: ${formatMaxMetric(eval_vs_ecg.resampled_mae)}<br>RMSE: ${formatMaxMetric(eval_vs_ecg.resampled_rmse)}<br>(N=${eval_vs_ecg.resampled_count})</td>`;
                }
                // vsPPG_fin (1分平均)
                // resampled_count が 0 の場合もエラーとして扱う
                if (eval_vs_fin.error || eval_vs_fin.resampled_count === 0) {
                    html += `<td style="color: orange;">${eval_vs_fin.error || 'データなし'} (N=${eval_vs_fin.resampled_count})</td>`;
                } else {
                    html += `<td>MAE: ${formatMaxMetric(eval_vs_fin.resampled_mae)}<br>RMSE: ${formatMaxMetric(eval_vs_fin.resampled_rmse)}<br>(N=${eval_vs_fin.resampled_count})</td>`;
                }
                html += '</tr>';

                html += '</tbody></table>';
            });
            html += `<div style="text-align: right; margin-top: 10px;">
                        <button onclick="saveResultsAsPng('${uniqueId}')">PNG保存</button>
                     </div>`;
        }
        
        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

    // --- メインの submit イベントリスナー ---
    uploadForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        
        if (!config) {
            alert('Configファイルが読み込まれていないため，送信できません．');
            return;
        }

        const validation = validateRequiredFiles();
        if (!validation.ok) {
            alert(validation.message);
            return;
        }

        const formData = new FormData();
        const hasLog = logCheckbox.checked;
        let intervalMin = 0;

        if (!hasLog) {
            intervalMin = parseInt(intervalInput.value, 10);
            if (isNaN(intervalMin) || intervalMin <= 0) {
                alert('区切り分数には 1 以上の整数を入力してください。');
                intervalInput.focus();
                return;
            }
        }

        formData.append('has_log', hasLog);
        formData.append('interval_min', intervalMin);

        for (const file of fileInput.files) {
            formData.append('files', file);
        }

        const selectedType = getSelectedAnalysisType();
        formData.append('analysis_types[]', selectedType);

        resultDiv.innerHTML = '解析中...';

        try {
            const response = await fetch('http://127.0.0.1:5000/upload', {
                method: 'POST',
                body: formData
            });

            let results;
            try {
                results = await response.json();
            } catch (jsonError) {
                throw new Error(`サーバー応答の JSON 解析に失敗しました: ${jsonError.message}`);
            }

            if (!response.ok) {
                const serverMessage = Array.isArray(results) && results.length > 0
                    ? results[0].message
                    : `HTTP ${response.status}`;
                throw new Error(serverMessage);
            }
            resultDiv.innerHTML = '';

            // 結果の配列をループ処理
            results.forEach(result => {
                // analysis_type に応じて適切な表示関数を呼び出す
                switch (result.analysis_type) {
                    case 'mlx_evaluation':
                        displayMlxEvaluation(result);
                        break;
                    case 'max_evaluation':
                        displayMaxEvaluation(result);
                        break;
                    case 'ppg_to_hr':
                        displayPpgToHrResult(result);
                        break;
                    case 'ppg_analysis':
                        displayPpgAnalysis(result);
                        break;
                    case 'show_files':
                        displayFilePreview(result);
                        break;
                    case 'mlx_reevaluation':
                        displayMlxEvaluation(result);
                        break;
                    default:
                        displayError(result);
                        break;
                }
            });

        } catch (error) {
            resultDiv.innerHTML = ''; // 「解析中...」を消す
            displayError({ message: `サーバーとの通信に失敗しました: ${error.message}` });
        }
    });
});