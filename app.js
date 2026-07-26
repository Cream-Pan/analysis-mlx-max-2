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
    const previewColumnsWrapper = document.getElementById('preview-columns-wrapper');
    const previewColumnsInput = document.getElementById('previewColumns');
    const previewAxis = document.getElementById('previewAxis');
    const previewScale = document.getElementById('previewScale');
    const previewAxisWrapper = document.getElementById('preview-axis-wrapper');
    const previewScaleWrapper = document.getElementById('preview-scale-wrapper');
    const submitButton = uploadForm.querySelector('button[type="submit"]');
    

    // logfile-wrapper が未設定でも最低限落ちないようにする
    const logWrapper =
        document.getElementById('logfile-wrapper') ||
        logCheckbox?.closest('.controls');

    let config = null;

    const PPG_ONLY_MODES = new Set(['ppg_to_hr']);
    const LOG_REQUIRED_MODES = new Set(['ppg_acc_analysis']);

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

    function isLogRequiredMode(type = getSelectedAnalysisType()) {
        return LOG_REQUIRED_MODES.has(type);
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

    function parsePreviewColumns() {
        const rawValue = previewColumnsInput?.value?.trim() ?? '';

        if (!rawValue) {
            return [];
        }

        const tokens = rawValue
            .split(/[,\s，]+/)
            .map(value => value.trim())
            .filter(Boolean);

        const columnNumbers = tokens.map(value => Number(value));

        const hasInvalidValue = columnNumbers.some(
            value => !Number.isInteger(value) || value <= 0
        );

        if (hasInvalidValue) {
            return null;
        }

        return [...new Set(columnNumbers)].sort((a, b) => a - b);
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

        const hideLogOption =
            isPpgOnlyMode(type);

        const requireLog =
            isLogRequiredMode(type);

        if (hideLogOption && logCheckbox) {
            logCheckbox.checked = false;
        }

        if (requireLog && logCheckbox) {
            logCheckbox.checked = true;
        }

        if (logCheckbox) {
            logCheckbox.disabled = requireLog;
        }

        setVisible(
            logWrapper,
            !hideLogOption
        );
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

        if (
            isPpgOnlyMode(type) ||
            type === 'show_files'
        ) {
            setVisible(intervalWrapper, false);
            return;
        }

        setVisible(intervalWrapper, !logCheckbox.checked);
    }

    function updateAnalysisOffsetVisibility() {
        const type = getSelectedAnalysisType();
        const hasLog = getEffectiveHasLog(type);

        const visible =
            (type === 'ppg_analysis' && !hasLog) ||
            type === 'ppg_hr_analysis';

        setVisible(offsetWrapper, visible);
        setVisible(durationWrapper, visible);
    }

    function updatePreviewColumnsVisibility(){
        const type = getSelectedAnalysisType();
        const visible = type === 'show_files';

        setVisible(
            previewColumnsWrapper,
            visible
        );

        setVisible(
            previewAxisWrapper,
            visible
        );

        setVisible(
            previewScaleWrapper,
            visible
        );
    }

    function syncUiState() {
        updateLogUiVisibility();
        updateIntervalInputVisibility();
        updateAnalysisOffsetVisibility();
        updatePreviewColumnsVisibility();
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

    async function saveResultsAsPng(elementId) {
        const element = document.getElementById(elementId);

        if (!element) {
            alert(
                `エラー: ID "${elementId}" の要素が見つかりません．`
            );
            return;
        }

        const scrollAreas = Array.from(
            element.querySelectorAll('.table-scroll')
        );

        const scrollAreaWidths = scrollAreas.map(
            area => area.scrollWidth
        );

        const originalElementStyle = {
            width: element.style.width,
            maxWidth: element.style.maxWidth
        };

        const originalScrollStyles = scrollAreas.map(area => ({
            overflow: area.style.overflow,
            width: area.style.width,
            maxWidth: area.style.maxWidth
        }));

        try {
            scrollAreas.forEach((area, index) => {
                area.style.overflow = 'visible';
                area.style.width =
                    `${scrollAreaWidths[index]}px`;
                area.style.maxWidth = 'none';
            });

            const captureWidth = Math.max(
                element.clientWidth,
                element.scrollWidth,
                ...scrollAreaWidths
            );

            element.style.width = `${captureWidth}px`;
            element.style.maxWidth = 'none';

            const canvas = await html2canvas(
                element,
                {
                    scale: 2,
                    useCORS: true,
                    allowTaint: true,
                    backgroundColor: '#ffffff',
                    width: captureWidth,
                    windowWidth: captureWidth,

                    ignoreElements: elementToCheck => {
                        return (
                            elementToCheck.tagName === 'BUTTON'
                            || elementToCheck.classList?.contains(
                                'screenshot-exclude'
                            )
                            || elementToCheck.hasAttribute?.(
                                'data-html2canvas-ignore'
                            )
                        );
                    }
                }
            );

            const dataURL = canvas.toDataURL('image/png');

            const a = document.createElement('a');
            a.href = dataURL;
            a.download =
                `${elementId}_${new Date()
                    .toISOString()
                    .slice(0, 10)}.png`;

            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

        } catch (error) {
            console.error(
                'PNG保存中にエラーが発生しました:',
                error
            );

            alert(
                `PNG保存エラーが発生しました: ${error.message}`
            );

        } finally {
            element.style.width =
                originalElementStyle.width;

            element.style.maxWidth =
                originalElementStyle.maxWidth;

            scrollAreas.forEach((area, index) => {
                const original =
                    originalScrollStyles[index];

                area.style.overflow =
                    original.overflow;

                area.style.width =
                    original.width;

                area.style.maxWidth =
                    original.maxWidth;
            });
        }
    }

    function downloadCsvText(filename, csvText) {
        const bom = '\uFEFF';
        const originalText = String(csvText ?? '');

        const csvWithBom = originalText.startsWith(bom)
            ? originalText
            : bom + originalText;

        const blob = new Blob(
            [csvWithBom],
            {
                type: 'text/csv;charset=utf-8;'
            }
        );

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

        let html = `<h3>${result.title}</h3>`;

        if (result.status === 'error') {
            html += `
                <p style="color: red; font-weight: bold;">
                    エラー: ${result.message}
                </p>
            `;

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
                <thead>
                    <tr>
                        <th>項目</th>
                        <th>値</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Fs</td>
                        <td>${fs} Hz</td>
                    </tr>
                    <tr>
                        <td>全体相関係数（IR vs RED）</td>
                        <td>${corrText}</td>
                    </tr>
                </tbody>
            </table>

            <div style="text-align: right; margin-top: 10px;">
                <button class="download-hr-csv-btn">
                    HR CSVダウンロード
                </button>
            </div>
        `;

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);

        const hrDownloadButton = resultEl.querySelector(
            '.download-hr-csv-btn'
        );

        if (hrDownloadButton && result.download) {
            hrDownloadButton.addEventListener('click', () => {
                downloadCsvText(
                    result.download.filename,
                    result.download.csv_text
                );
            });
        }
    }

    function formatPpgAccValue(
        value,
        digits = 1,
        suffix = ''
    ) {
        if (
            value === null
            || value === undefined
            || value === ''
        ) {
            return '―';
        }

        const numericValue = Number(value);

        if (!Number.isFinite(numericValue)) {
            return '―';
        }

        return `${numericValue.toFixed(digits)}${suffix}`;
    }


    /*
    * PPG解析と同じ色分けを使用する．
    * 5 bpm以下は緑，5 bpm超は赤．
    */
    function formatPpgAccErrorMetric(value) {
        if (
            value === null
            || value === undefined
            || value === ''
        ) {
            return '―';
        }

        const numericValue = Number(value);

        if (!Number.isFinite(numericValue)) {
            return '―';
        }

        return formatMaxMetric(numericValue);
    }


    function displayPpgAccAnalysis(result) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';

        const uniqueId =
            `ppg-acc-analysis-${Date.now()}-`
            + Math.random().toString(36).slice(2, 7);

        resultEl.id = uniqueId;

        let html = `
            <h3>
                ${result.title || 'PPG＋ACC解析結果'}
            </h3>
        `;

        if (result.status === 'error') {
            html += `
                <p style="color: red; font-weight: bold;">
                    エラー: ${result.message}
                </p>
            `;

            resultEl.innerHTML = html;
            resultDiv.appendChild(resultEl);
            return;
        }

        const rows = Array.isArray(result.data)
            ? result.data
            : [];

        html += `
            <p>
                Fin：
                <b>${result.fin_filename || '不明'}</b>
                （${result.fin_fs ?? '―'} Hz）
                <br>

                耳たぶ：
                <b>${result.ear_filename || '不明'}</b>
                （${result.ear_fs ?? '―'} Hz）
            </p>

            <div class="table-scroll">
                <table class="ppg-acc-table">
                    <thead>
                        <tr>
                            <th>タスク名</th>

                            <th class="metric-column">MAE</th>
                            <th class="metric-column">RMSE</th>
                            <th class="metric-column">Bias</th>
                            <th>評価判定</th>

                            <th>有効ペア窓数</th>
                            <th>有効ペア窓率</th>

                            <th class="quality-column">
                                Fin全窓数
                            </th>
                            <th class="quality-column">
                                Fin Lost率
                            </th>
                            <th class="quality-column">
                                Fin Motion Artifact率
                            </th>
                            <th class="quality-column">
                                Fin HR利用可能率
                            </th>

                            <th class="quality-column">
                                耳たぶ全窓数
                            </th>
                            <th class="quality-column">
                                耳たぶ Lost率
                            </th>
                            <th class="quality-column">
                                耳たぶ Motion Artifact率
                            </th>
                            <th class="quality-column">
                                耳たぶ HR利用可能率
                            </th>
                        </tr>
                    </thead>

                    <tbody>
        `;

        rows.forEach(row => {
            html += `
                <tr>
                    <td>
                        ${row.Task_Name ?? '―'}
                    </td>

                    <td class="metric-cell">
                        ${formatPpgAccErrorMetric(
                            row.MAE
                        )}
                    </td>

                    <td class="metric-cell">
                        ${formatPpgAccErrorMetric(
                            row.RMSE
                        )}
                    </td>

                    <td class="metric-cell">
                        ${formatPpgAccValue(
                            row.Bias,
                            4
                        )}
                    </td>

                    <td>
                        ${row.Evaluation ?? '―'}
                    </td>

                    <td>
                        ${row.Valid_Pair_Count ?? 0}
                    </td>

                    <td>
                        ${formatPpgAccValue(
                            row.Valid_Pair_Rate,
                            1,
                            ' %'
                        )}
                    </td>

                    <td class="quality-cell">
                        ${
                            row.Fin_Total_Window_Count
                            ?? 0
                        }
                    </td>

                    <td class="quality-cell">
                        ${formatPpgAccValue(
                            row.Fin_Lost_Rate,
                            1,
                            ' %'
                        )}
                    </td>

                    <td class="quality-cell">
                        ${formatPpgAccValue(
                            row.Fin_Motion_Artifact_Rate,
                            1,
                            ' %'
                        )}
                    </td>

                    <td class="quality-cell">
                        ${formatPpgAccValue(
                            row.Fin_HR_Usable_Rate,
                            1,
                            ' %'
                        )}
                    </td>

                    <td class="quality-cell">
                        ${
                            row.Ear_Total_Window_Count
                            ?? 0
                        }
                    </td>

                    <td class="quality-cell">
                        ${formatPpgAccValue(
                            row.Ear_Lost_Rate,
                            1,
                            ' %'
                        )}
                    </td>

                    <td class="quality-cell">
                        ${formatPpgAccValue(
                            row.Ear_Motion_Artifact_Rate,
                            1,
                            ' %'
                        )}
                    </td>

                    <td class="quality-cell">
                        ${formatPpgAccValue(
                            row.Ear_HR_Usable_Rate,
                            1,
                            ' %'
                        )}
                    </td>
                </tr>
            `;
        });

        if (rows.length === 0) {
            html += `
                <tr>
                    <td colspan="15">
                        表示できる解析結果がありません．
                    </td>
                </tr>
            `;
        }

        html += `
                    </tbody>
                </table>
            </div>

            <div
                class="result-actions screenshot-exclude"
                data-html2canvas-ignore="true"
            >
                <button class="save-ppg-acc-png-btn">PNG保存</button>

                ${
                    result.detail_download
                        ? `
                            <button
                                class="download-ppg-acc-detail-btn"
                            >
                                窓詳細CSVダウンロード
                            </button>
                        `
                        : ''
                }
            </div>
        `;

        resultEl.innerHTML = html;
        resultDiv.appendChild(resultEl);

        const screenshotButton = resultEl.querySelector(
            '.save-ppg-acc-png-btn'
        );

        screenshotButton?.addEventListener(
            'click',
            () => {
                saveResultsAsPng(uniqueId);
            }
        );

        const detailButton = resultEl.querySelector(
            '.download-ppg-acc-detail-btn'
        );

        if (
            detailButton
            && result.detail_download
        ) {
            detailButton.addEventListener(
                'click',
                () => {
                    downloadCsvText(
                        result.detail_download.filename,
                        result.detail_download.csv_text
                    );
                }
            );
        }
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
            <div class="result-actions screenshot-exclude" data-html2canvas-ignore="true">
                <button onclick="saveResultsAsPng('${uniqueId}')">PNG保存</button>
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

        const title = document.createElement('h3');
        title.textContent = 'ファイル列グラフ';
        resultEl.appendChild(title);

        resultDiv.appendChild(resultEl);

        if (result.status === 'error' || !Array.isArray(result.data)) {
            const errorMessage = document.createElement('p');
            errorMessage.style.color = 'red';
            errorMessage.style.fontWeight = 'bold';
            errorMessage.textContent =
                `エラー: ${result.message || 'データを表示できません'}`;

            resultEl.appendChild(errorMessage);
            return;
        }

        const chartColors = [
            '#3366cc',
            '#dc3912',
            '#109618',
            '#ff9900',
            '#990099',
            '#0099c6',
            '#dd4477',
            '#66aa00'
        ];

        result.data.forEach((file, fileIndex) => {
            const fileTitle = document.createElement('h4');
            fileTitle.textContent = file.filename;
            resultEl.appendChild(fileTitle);

            if (file.type === 'error') {
                const errorMessage = document.createElement('p');
                errorMessage.style.color = 'red';
                errorMessage.textContent =
                    file.message || 'ファイルを読み込めませんでした．';

                resultEl.appendChild(errorMessage);
                return;
            }

            if (!Array.isArray(file.sheets) || file.sheets.length === 0) {
                const emptyMessage = document.createElement('p');
                emptyMessage.textContent = '表示できるデータがありません．';
                resultEl.appendChild(emptyMessage);
                return;
            }

            file.sheets.forEach((sheet, sheetIndex) => {
                if (sheet.sheet_name) {
                    const sheetTitle = document.createElement('h5');
                    sheetTitle.className = 'file-chart-sheet-title';
                    sheetTitle.textContent = `シート: ${sheet.sheet_name}`;
                    resultEl.appendChild(sheetTitle);
                }

                if (Array.isArray(sheet.errors)) {
                    sheet.errors.forEach(errorText => {
                        const warning = document.createElement('p');
                        warning.className = 'file-chart-warning';
                        warning.textContent = errorText;
                        resultEl.appendChild(warning);
                    });
                }

                if (
                    !Array.isArray(sheet.series) ||
                    sheet.series.length === 0
                ) {
                    const emptyMessage = document.createElement('p');
                    emptyMessage.textContent =
                        '指定した列にプロット可能な数値データがありません．';

                    resultEl.appendChild(emptyMessage);
                    return;
                }

                const rowCount = Number(sheet.row_count) || Math.max(
                    ...sheet.series.map(series => series.values?.length || 0)
                );

                /*
                * 1 データあたり約 3 px とし，データ数に応じて横長にする．
                * 極端に巨大なキャンバスを防ぐため，上限は 60000 px とする．
                */
                const chartWidth = Math.min(
                    60000,
                    Math.max(900, rowCount * 3)
                );

                const scrollContainer = document.createElement('div');
                scrollContainer.className = 'file-chart-scroll';

                const chartInner = document.createElement('div');
                chartInner.className = 'file-chart-inner';
                chartInner.style.width = `${chartWidth}px`;

                const canvas = document.createElement('canvas');
                canvas.width = chartWidth;
                canvas.height = 420;

                chartInner.appendChild(canvas);
                scrollContainer.appendChild(chartInner);
                resultEl.appendChild(scrollContainer);

                const datasets = sheet.series.map((series, seriesIndex) => {
                    const color =
                        chartColors[seriesIndex % chartColors.length];

                    return {
                        label: `${series.column_number}列目`,
                        data:
                        series.points.map(
                            point=>({
                                x:point.x,
                                y:point.y
                            })
                        ),
                        borderColor: color,
                        backgroundColor: color,
                        borderWidth: 1,
                        pointRadius: 0,
                        pointHoverRadius: 3,
                        spanGaps: false
                    };
                });

                new Chart(canvas.getContext('2d'), {
                    type: 'line',

                    data: {
                        datasets
                    },

                    options: {
                        responsive: false,
                        maintainAspectRatio: false,
                        animation: false,
                        parsing: false,
                        normalized: true,

                        interaction: {
                            mode: 'nearest',
                            intersect: false
                        },

                        scales: {
                            x: {
                                type: 'linear',
                                title: {
                                    display: true,
                                    text:
                                    (sheet.tasks.length > 0 && previewAxis.value==="time")
                                    ?
                                    "時間[s]"
                                    :
                                    "行番号"
                                },
                                ticks: {
                                    maxTicksLimit: 20
                                }
                            },

                            y: {
                                title: {
                                    display: true,
                                    text: '値'
                                }
                            }
                        },

                        plugins: {
                            annotation:{
                                annotations:
                                    sheet.tasks
                                    ?
                                    Object.fromEntries(
                                        sheet.tasks.map(
                                            (task,i)=>[
                                                `task${i}`,
                                                {
                                                    type:"box",

                                                    xMin:task.start,
                                                    xMax:task.end,

                                                    backgroundColor:
                                                    "rgba(100,100,100,0.08)",

                                                    label:{
                                                        display:true,
                                                        content:
                                                        task.name
                                                    }
                                                }
                                            ]
                                        )
                                    )
                                    :
                                    {}

                            },

                            zoom:{
                                zoom:{
                                    wheel:{
                                    enabled:true
                                    },
                                    pinch:{
                                    enabled:true
                                    },
                                    mode:"x"
                                },
                                pan:{
                                enabled:true,
                                mode:"x"
                                }
                            }
                        }
                    }
                });
            });
        });
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

        let previewColumns = [];

        if (selectedType === 'show_files') {
            previewColumns = parsePreviewColumns();

            if (previewColumns === null) {
                alert(
                    '列番号には，1 以上の整数を入力してください．\n' +
                    '複数列を指定する場合は，例のように 1,3,5 と入力してください．'
                );

                previewColumnsInput.focus();
                return;
            }

            if (previewColumns.length === 0) {
                alert('プロットする列番号を 1 つ以上指定してください．');

                previewColumnsInput.focus();
                return;
            }
        }

        const usesAnalysisRange =
            (selectedType === 'ppg_analysis' && !hasLog) ||
            selectedType === 'ppg_hr_analysis';

        let analysisStartOffsetSec = 0;
        let analysisDurationSec = 0;

        if (usesAnalysisRange) {
            analysisStartOffsetSec = parseFloat(offsetInput.value);

            if (isNaN(analysisStartOffsetSec) || analysisStartOffsetSec < 0) {
                alert('解析開始オフセットには 0 以上の数値を入力してください．');
                offsetInput.focus();
                return;
            }

            analysisDurationSec = parseFloat(durationInput.value);

            if (isNaN(analysisDurationSec) || analysisDurationSec <= 0) {
                alert('解析時間には 0 より大きい数値を入力してください．');
                durationInput.focus();
                return;
            }
        }

        let intervalMin = 0;
        if (!hasLog && !isPpgOnlyMode(selectedType) && selectedType !== 'show_files') {
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

        previewColumns.forEach(columnNumber => {
            formData.append(
                'preview_columns[]',
                String(columnNumber)
            );
        });

        if(selectedType === "show_files"){
            formData.append(
                "preview_axis",
                previewAxis.value
            );
            formData.append(
                "preview_scale",
                previewScale.value
            );
        }

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
                    case 'ppg_acc_analysis':
                        displayPpgAccAnalysis(result);
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