document.addEventListener('DOMContentLoaded', async () => {
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const resultDiv = document.getElementById('result');
    const requiredMsg = document.getElementById('required-files-msg');
    const logCheckbox = document.getElementById('hasLogFile');
    const intervalWrapper = document.getElementById('interval-wrapper');
    const intervalInput = document.getElementById('intervalMin');
    const offsetInput = document.getElementById('analysisStartOffsetSec');
    const offsetWrapper = document.getElementById('analysis-offset-wrapper');
    const durationInput = document.getElementById('analysisDurationSec');
    const durationWrapper = document.getElementById('analysis-duration-wrapper');
    const submitButton = uploadForm.querySelector('button[type="submit"]');

    // logfile-wrapper が未設定でも最低限落ちないようにする
    const logWrapper =
        document.getElementById('logfile-wrapper') ||
        logCheckbox?.closest('.controls');

    let config = null;

    const PPG_ONLY_MODES = new Set(['ppg_to_hr']);

    // -----------------------------
    // 共通ヘルパー
    // -----------------------------
    function normalizeFileName(name) {
        return String(name).trim().toLowerCase();
    }

    function getSelectedAnalysisType() {
        return document.querySelector('input[name="analysis_type"]:checked')?.value ?? null;
    }

    function isPpgOnlyMode(type = getSelectedAnalysisType()) {
        return PPG_ONLY_MODES.has(type);
    }

    function setVisible(element, visible, display = 'flex') {
        if (!element) return;
        element.style.display = visible ? display : 'none';
    }

    function getEffectiveHasLog(type = getSelectedAnalysisType()) {
        return !isPpgOnlyMode(type) && !!logCheckbox?.checked;
    }

    function getRequiredFiles(type, hasLog) {
        if (!config || !config.required_files) return [];
        return [...(config.required_files[type] || [])];
    }

    function getSelectedFileNames() {
        return Array.from(fileInput.files).map(file => file.name);
    }

    function validateRequiredFiles() {
        const type = getSelectedAnalysisType();
        if (!type) {
            return { ok: false, message: '実行したい解析メニューを選択してください。' };
        }

        const requiredFiles = getRequiredFiles(type, getEffectiveHasLog(type));
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

        const requiredList = getRequiredFiles(type, getEffectiveHasLog(type));
        const displayList = requiredList.map(name => `<b>${name}</b>`);
        let message = displayList.length > 0 ? displayList.join(' , ') : '任意';

        const note = config.required_file_notes?.[type];
        if (note) {
            message += `<br><span style="color:#666;">補足：${note}</span>`;
        }

        requiredMsg.innerHTML = `必要なファイル： ${message}`;
    }

    function updateLogUiVisibility() {
        const type = getSelectedAnalysisType();
        const ppgOnly = isPpgOnlyMode(type);

        if (ppgOnly && logCheckbox) {
            logCheckbox.checked = false;
        }

        setVisible(logWrapper, !ppgOnly);
    }

    function displayPpgHrAnalysis(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';

        let html = `<h3>${result.title || 'PPG脈波解析結果'}</h3>`;

        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
            resultEl.innerHTML = html;
            resultDiv.appendChild(resultEl);
            return;
        }

        if (!result.data || result.data.length === 0) {
            html += `<p style="color: orange; font-weight: bold;">解析結果がありません</p>`;
            resultEl.innerHTML = html;
            resultDiv.appendChild(resultEl);
            return;
        }

        html += `
            <table>
                <thead>
                    <tr>
                        <th>ファイル</th>
                        <th>解析開始</th>
                        <th>解析終了</th>
                        <th>有効拍数</th>
                        <th>LF</th>
                        <th>HF</th>
                        <th>LF/HF</th>
                        <th>NN50</th>
                        <th>PNN50</th>
                    </tr>
                </thead>
                <tbody>
        `;

        result.data.forEach(row => {
            const lf = row.lf_power == null ? 'N/A' : Number(row.lf_power).toFixed(4);
            const hf = row.hf_power == null ? 'N/A' : Number(row.hf_power).toFixed(4);
            const lfHf = row.lf_hf == null ? 'N/A' : Number(row.lf_hf).toFixed(4);
            const pnn50 = row.pnn50 == null ? 'N/A' : `${Number(row.pnn50).toFixed(2)} %`;

            html += `
                <tr>
                    <td>${row.filename}</td>
                    <td>${row.start_time}</td>
                    <td>${row.end_time}</td>
                    <td>${row.nn_count}</td>
                    <td>${lf}</td>
                    <td>${hf}</td>
                    <td>${lfHf}</td>
                    <td>${row.nn50}</td>
                    <td>${pnn50}</td>
                </tr>
            `;
        });

        html += `</tbody></table>`;

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

    function updateIntervalInputVisibility() {
        const type = getSelectedAnalysisType();
        const ppgOnly = isPpgOnlyMode(type);

        if (ppgOnly) {
            setVisible(intervalWrapper, false);
            return;
        }

        setVisible(intervalWrapper, !logCheckbox.checked);
    }

    function updateAnalysisOffsetVisibility() {
        const type = getSelectedAnalysisType();
        const visible =
        type === 'ppg_to_hr' ||
        type === 'ppg_analysis' ||
        type === 'ppg_hr_analysis';

        setVisible(offsetWrapper, visible);
        setVisible(durationWrapper, visible);
    }

    function syncUiState() {
        updateLogUiVisibility();
        updateIntervalInputVisibility();
        updateAnalysisOffsetVisibility();
        updateRequiredFiles();
    }

    try {
        const response = await fetch('config.json');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        config = await response.json();
        setSubmitEnabled(true);
        syncUiState();
    } catch (error) {
        console.error('config.json の読み込みに失敗しました:', error);
        requiredMsg.innerHTML = '<span style="color:red;">Configファイルの読み込みに失敗しました</span>';
        setSubmitEnabled(false);
    }

    document.querySelectorAll('input[name="analysis_type"]').forEach(radio => {
        radio.addEventListener('change', syncUiState);
    });

    logCheckbox.addEventListener('change', syncUiState);

    // -----------------------------
    // 保存系
    // -----------------------------
    window.saveResultsAsPng = saveResultsAsPng;

    function saveResultsAsPng(elementId) {
        const element = document.getElementById(elementId);

        if (!element) {
            alert(`エラー: ID "${elementId}" の要素が見つかりません。`);
            return;
        }

        html2canvas(element, {
            scale: 2,
            useCORS: true,
            allowTaint: true,
            ignoreElements: (el) =>
                el.tagName === 'BUTTON' && el.textContent === 'PNG保存'
        }).then(canvas => {
            const dataURL = canvas.toDataURL('image/png');
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

    // -----------------------------
    // 表示系
    // -----------------------------
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
        const corrText =
            overallCorr === null || overallCorr === undefined
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

        resultEl.querySelector('.download-csv-btn')?.addEventListener('click', () => {
            downloadCsvText(result.download.filename, result.download.csv_text);
        });
    }

    function displayPpgAnalysis(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';

        const uniqueId = `ppg-analysis-${Date.now()}`;
        resultEl.id = uniqueId;

        let html = `<h3>${result.title}</h3>`;

        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
            resultEl.innerHTML = html;
            resultDiv.appendChild(resultEl);
            return;
        }

        result.data.forEach(taskResult => {
            html += `<h4>タスク: ${taskResult.task}</h4>`;
            html += `
                <table>
                    <thead>
                        <tr>
                            <th>比較</th>
                            <th>元データ</th>
                            <th>1分平均</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            taskResult.comparisons.forEach(comp => {
                const rawCell = comp.error
                    ? `<span style="color: orange;">${comp.error} (N=${comp.raw_count})</span>`
                    : `MAE: ${formatMaxMetric(comp.raw_mae)}<br>RMSE: ${formatMaxMetric(comp.raw_rmse)}<br>(N=${comp.raw_count})`;

                const resampledCell = (comp.error || comp.resampled_count === 0)
                    ? `<span style="color: orange;">${comp.error || 'データなし'} (N=${comp.resampled_count})</span>`
                    : `MAE: ${formatMaxMetric(comp.resampled_mae)}<br>RMSE: ${formatMaxMetric(comp.resampled_rmse)}<br>(N=${comp.resampled_count})`;

                html += `
                    <tr>
                        <td>${comp.device_name}</td>
                        <td>${rawCell}</td>
                        <td>${resampledCell}</td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;
        });


        html += `
            <div style="text-align: right; margin-top: 10px;">
                <button onclick="saveResultsAsPng('${uniqueId}')">
                    PNG保存
                </button>
            </div>
        `;

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

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

    function formatMlxMetric(value) {
        if (value === null) return 'N/A (データなし)';

        const numericValue = parseFloat(value);
        const text = numericValue.toFixed(4);

        if (numericValue <= 0.3) {
            return `<span style="color: green; font-weight: bold;">${text}</span>`;
        }
        if (numericValue > 1.0) {
            return `<span style="color: red; font-weight: bold;">${text}</span>`;
        }
        return text;
    }

    function formatMaxMetric(value) {
        if (value === null) return 'N/A (データなし)';

        const numericValue = parseFloat(value);
        const text = numericValue.toFixed(4);

        if (numericValue <= 5.0) {
            return `<span style="color: green; font-weight: bold;">${text}</span>`;
        }
        return `<span style="color: red; font-weight: bold;">${text}</span>`;
    }

    function displayFilePreview(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        let html = `<h3>ファイル内容の表示</h3>`;

        if (result.status === 'error' || !result.data) {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message || 'データを表示できません'}</p>`;
        } else {
            result.data.forEach(file => {
                html += `<h4>${file.filename}</h4>`;

                if (file.sheets && Array.isArray(file.sheets)) {
                    file.sheets.forEach(sheet => {
                        if (sheet.sheet_name) {
                            const safeSheetName = String(sheet.sheet_name)
                                .replace(/</g, '&lt;')
                                .replace(/>/g, '&gt;');
                            html += `<h5 style="margin:0.5em 0 0.2em 1.5em;">シート: ${safeSheetName}</h5>`;
                        }

                        html += '<ul>';
                        if (sheet.data && Array.isArray(sheet.data)) {
                            sheet.data.forEach(item => {
                                const safeItem = String(item)
                                    .replace(/</g, '&lt;')
                                    .replace(/>/g, '&gt;');
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

    function displayMlxEvaluation(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        const uniqueId = `${result.analysis_type}-${Date.now()}`;
        resultEl.id = uniqueId;

        let html = `<h3>${result.title}</h3>`;
        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
        } else {
            result.data.forEach(taskResult => {
                html += `<h4>タスク: ${taskResult.task}</h4>`;
                html += `
                    <table>
                        <thead><tr><th>指標</th><th>値</th></tr></thead>
                        <tbody>
                            <tr><td>有効データペア数</td><td>${taskResult.count}</td></tr>
                            <tr><td>MAE (平均絶対誤差)</td><td>${formatMlxMetric(taskResult.mae)}</td></tr>
                            <tr><td>RMSE (二乗平均平方根誤差)</td><td>${formatMlxMetric(taskResult.rmse)}</td></tr>
                            <tr><td>BodyTemp 平均</td><td>${taskResult.mean_body_temp?.toFixed(3) ?? 'N/A'}</td></tr>
                            <tr><td>Object_C 平均</td><td>${taskResult.mean_object_c?.toFixed(3) ?? 'N/A'}</td></tr>
                            <tr><td>Ambient_C 平均</td><td>${taskResult.mean_ambient_c?.toFixed(3) ?? 'N/A'}</td></tr>
                        </tbody>
                    </table>
                `;
            });

            html += `
                <div style="text-align: right; margin-top: 10px;">
                    <button onclick="saveResultsAsPng('${uniqueId}')">PNG保存</button>
                </div>
            `;
        }

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

    function displayMaxEvaluation(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        const uniqueId = `result-${result.analysis_type}-${Date.now()}`;
        resultEl.id = uniqueId;

        let html = `<h3>${result.title}</h3>`;
        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
        } else {
            result.data.forEach(taskResult => {
                html += `<h4>タスク: ${taskResult.task}</h4>`;
                const evalVsEcg = taskResult.eval_1;
                const evalVsFin = taskResult.eval_2;

                html += `
                    <table>
                        <thead>
                            <tr>
                                <th></th>
                                <th>${evalVsEcg.device_name}</th>
                                <th>${evalVsFin.device_name}</th>
                            </tr>
                        </thead>
                        <tbody>
                `;

                html += `
                    <tr>
                        <td>元データ</td>
                        <td>${
                            evalVsEcg.error
                                ? `<span style="color: orange;">${evalVsEcg.error} (N=${evalVsEcg.raw_count})</span>`
                                : `MAE: ${formatMaxMetric(evalVsEcg.raw_mae)}<br>RMSE: ${formatMaxMetric(evalVsEcg.raw_rmse)}<br>(N=${evalVsEcg.raw_count})`
                        }</td>
                        <td>${
                            evalVsFin.error
                                ? `<span style="color: orange;">${evalVsFin.error} (N=${evalVsFin.raw_count})</span>`
                                : `MAE: ${formatMaxMetric(evalVsFin.raw_mae)}<br>RMSE: ${formatMaxMetric(evalVsFin.raw_rmse)}<br>(N=${evalVsFin.raw_count})`
                        }</td>
                    </tr>
                `;

                html += `
                    <tr>
                        <td>1分平均</td>
                        <td>${
                            evalVsEcg.error || evalVsEcg.resampled_count === 0
                                ? `<span style="color: orange;">${evalVsEcg.error || 'データなし'} (N=${evalVsEcg.resampled_count})</span>`
                                : `MAE: ${formatMaxMetric(evalVsEcg.resampled_mae)}<br>RMSE: ${formatMaxMetric(evalVsEcg.resampled_rmse)}<br>(N=${evalVsEcg.resampled_count})`
                        }</td>
                        <td>${
                            evalVsFin.error || evalVsFin.resampled_count === 0
                                ? `<span style="color: orange;">${evalVsFin.error || 'データなし'} (N=${evalVsFin.resampled_count})</span>`
                                : `MAE: ${formatMaxMetric(evalVsFin.resampled_mae)}<br>RMSE: ${formatMaxMetric(evalVsFin.resampled_rmse)}<br>(N=${evalVsFin.resampled_count})`
                        }</td>
                    </tr>
                `;

                html += `</tbody></table>`;
            });

            html += `
                <div style="text-align: right; margin-top: 10px;">
                    <button onclick="saveResultsAsPng('${uniqueId}')">PNG保存</button>
                </div>
            `;
        }

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);
    }

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

        const selectedType = getSelectedAnalysisType();
        const hasLog = getEffectiveHasLog(selectedType);
        const formData = new FormData();

        const analysisStartOffsetSec = parseFloat(offsetInput.value);
        if (isNaN(analysisStartOffsetSec) || analysisStartOffsetSec < 0) {
            alert('解析開始オフセットには 0 以上の数値を入力してください。');
            offsetInput.focus();
            return;
        }

        let analysisDurationSec = 0;
        if (isPpgOnlyMode(selectedType)) {
            analysisDurationSec = parseFloat(durationInput.value);
            if (isNaN(analysisDurationSec) || analysisDurationSec <= 0) {
                alert('解析時間には 0 より大きい数値を入力してください。');
                durationInput.focus();
                return;
            }
        }

        let intervalMin = 0;
        if (!hasLog && !isPpgOnlyMode(selectedType)) {
            intervalMin = parseInt(intervalInput.value, 10);
            if (isNaN(intervalMin) || intervalMin <= 0) {
                alert('区切り分数には 1 以上の整数を入力してください。');
                intervalInput.focus();
                return;
            }
        }

        formData.append('analysis_start_offset_sec', analysisStartOffsetSec);
        formData.append('analysis_duration_sec', analysisDurationSec);
        formData.append('has_log', hasLog);
        formData.append('interval_min', intervalMin);

        for (const file of fileInput.files) {
            formData.append('files', file);
        }

        formData.append('analysis_types[]', selectedType);

        resultDiv.innerHTML = '解析中...';

        try {
            const response = await fetch('/upload', {
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

            results.forEach(result => {
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
                    case 'ppg_hr_analysis':
                        displayPpgHrAnalysis(result);
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
            resultDiv.innerHTML = '';
            displayError({ message: `サーバーとの通信に失敗しました: ${error.message}` });
        }
    });
});