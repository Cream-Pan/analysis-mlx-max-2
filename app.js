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
    const previewScale = document.getElementById('previewScale');
    const previewScaleWrapper = document.getElementById('preview-scale-wrapper');
    const previewRegressionInput = document.getElementById('previewRegression');
    const previewRegressionWrapper = document.getElementById('preview-regression-wrapper');
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
        return getInputSpec(type)?.log_policy !== 'unused' && !!logCheckbox?.checked;
    }

    function getInputSpec(type = getSelectedAnalysisType()) {
        return config?.input_specs?.[type] ?? null;
    }

    function getConfigValue(path) {
        return String(path ?? '').split('.').reduce(
            (value, key) => value?.[key], config
        );
    }

    function getSpecColumns(spec) {
        const columns = spec?.columns_ref
            ? getConfigValue(spec.columns_ref)
            : [];
        return Array.isArray(columns)
            ? columns.map(String)
            : Object.values(columns ?? {}).map(String);
    }

    function getRequiredFiles(type, hasLog) {
        return (getInputSpec(type)?.fixed_files ?? []).map(file => file.name);
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

        const spec = getInputSpec(type);
        if (!spec) {
            return { ok: false, message: '入力仕様が設定されていない解析です．' };
        }

        const requiredFiles = getRequiredFiles(type, getEffectiveHasLog(type));
        const selectedNames = getSelectedFileNames();

        const missingFiles = requiredFiles.filter(required =>
            !selectedNames.includes(required)
        );

        if (missingFiles.length > 0) {
            return {
                ok: false,
                message: `必要なファイルが不足しています：${missingFiles.join(' , ')}`
            };
        }

        for (const rule of spec.file_rules ?? []) {
            const candidates = selectedNames.filter(name => {
                const lower = normalizeFileName(name);
                const extensions = (rule.extensions ?? []).map(value => value.toLowerCase());
                if (extensions.length && !extensions.some(ext => lower.endsWith(ext))) return false;
                if (rule.suffix && !lower.endsWith(rule.suffix.toLowerCase())) return false;
                if ((rule.contains_all ?? []).some(value => !lower.includes(value.toLowerCase()))) return false;
                if (rule.contains_any?.length && !rule.contains_any.some(value => lower.includes(value.toLowerCase()))) return false;
                if ((rule.exclude_contains ?? []).some(value => lower.includes(value.toLowerCase()))) return false;
                return true;
            });
            const minimum = Number(rule.min_count ?? 0);
            if (candidates.length < minimum) {
                const columns = getSpecColumns(rule);
                const note = columns.length ? `（必要列：${columns.join('，')}）` : '';
                return {
                    ok: false,
                    message: `${rule.label ?? '入力ファイル'}が不足しています．${minimum} 個以上選択してください${note}`
                };
            }
            if (rule.max_count != null && rule.selection === 'filename' && candidates.length > Number(rule.max_count)) {
                return {
                    ok: false,
                    message: `${rule.label ?? '入力ファイル'}は ${rule.max_count} 個まで選択してください．`
                };
            }
        }

        const hasLog = getEffectiveHasLog(type);
        if (spec.log_policy === 'required' && !hasLog) {
            return { ok: false, message: 'この解析ではログファイルの使用が必要です．' };
        }
        if (hasLog) {
            const logFiles = selectedNames.filter(name =>
                name.toLowerCase().endsWith('_log.csv') || name.toLowerCase() === 'log.csv'
            );
            if (logFiles.length === 0) {
                return { ok: false, message: 'ログファイル（*_log.csv）を選択してください．' };
            }
            if (logFiles.length > 1) {
                return { ok: false, message: 'ログファイルは 1 つだけ選択してください．' };
            }
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

        const spec = getInputSpec(type);
        if (!spec) {
            requiredMsg.textContent = '入力仕様が設定されていません';
            return;
        }

        const lines = [];
        const fixedFiles = (spec.fixed_files ?? []).map(file => {
            const columns = getSpecColumns(file);
            const requirement = columns.length
                ? `（列：${columns.join('，')}）`
                : file.min_columns
                    ? `（${file.min_columns} 列以上）`
                    : '';
            return `${file.name}${requirement}`;
        });
        lines.push(`固定ファイル：${fixedFiles.length ? fixedFiles.join('，') : 'なし'}`);
        for (const rule of spec.file_rules ?? []) {
            const columns = getSpecColumns(rule);
            const countText = `${rule.min_count ?? 0} 個以上` +
                (rule.max_count != null ? `，最大 ${rule.max_count} 個` : '');
            lines.push(`${rule.label}：${countText}${columns.length ? `（列：${columns.join('，')}）` : ''}`);
        }
        if (spec.log_policy === 'required') {
            const columns = getConfigValue(spec.log_columns_ref) ?? [];
            lines.push(`ログファイル：必須（*_log.csv，${columns.join('，')} 列）`);
        } else if (spec.log_policy === 'optional') {
            const columns = getConfigValue(spec.log_columns_ref) ?? [];
            lines.push(`ログファイル：任意（使用時は *_log.csv，${columns.join('，')} 列）`);
        } else {
            lines.push('ログファイル：使用しません');
        }
        requiredMsg.textContent = `${spec.description ?? ''}${spec.description ? ' ' : ''}${lines.join('　')}`;
    }

    function updateLogUiVisibility() {
        const type = getSelectedAnalysisType();

        const spec = getInputSpec(type);
        const hideLogOption = spec?.log_policy === 'unused';

        const requireLog = spec?.log_policy === 'required';

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
        window.VitBudsResultRenderers.ppgHrAnalysis(
            result,
            resultDiv,
            saveResultsAsPng
        );
    }

    function updateIntervalInputVisibility() {
        const type = getSelectedAnalysisType();
        const hasLog = getEffectiveHasLog(type);

        if (
            isPpgOnlyMode(type) ||
            type === 'show_files' ||
            (type === 'ppg_hr_analysis' && hasLog)
        ) {
            setVisible(intervalWrapper, false);
            return;
        }

        setVisible(intervalWrapper, !logCheckbox.checked);
    }

    function updateAnalysisOffsetVisibility() {
        const type = getSelectedAnalysisType();
        const hasLog = getEffectiveHasLog(type);

        if (type === 'ppg_analysis' && !hasLog && !durationInput.value) {
            durationInput.value = '60';
        }

        const visible =
            (type === 'ppg_analysis' && !hasLog) ||
            (type === 'ppg_hr_analysis' && !hasLog);

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
            previewScaleWrapper,
            visible
        );

        setVisible(
            previewRegressionWrapper,
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

    function saveResultsAsPng(elementId) {
        return window.VitBudsFileActions.saveResultsAsPng(elementId);
    }

    function downloadCsvText(filename, csvText) {
        window.VitBudsFileActions.downloadCsvText(filename, csvText);
    }

    // -----------------------------
    // 表示系
    // -----------------------------
    function displayPpgToHrResult(result) {
        window.VitBudsResultRenderers.ppgToHr(
            result,
            resultDiv,
            downloadCsvText
        );
    }

    function displayPpgAccAnalysis(result) {
        window.VitBudsResultRenderers.ppgAccAnalysis(
            result,
            resultDiv,
            formatMaxMetric,
            saveResultsAsPng,
            downloadCsvText
        );
    }


    function displayPpgAnalysis(result) {
        window.VitBudsResultRenderers.ppgComparison(
            result,
            resultDiv,
            formatMaxMetric,
            saveResultsAsPng
        );
    }

    function displayError(result) {
        window.VitBudsResultRenderers.error(result, resultDiv);
    }

    function formatMaxMetric(value) {
        return window.VitBudsResultFormatters.metrics.formatMaxMetric(value);
    }

    function displayFilePreview(result, showRegression = false) {
        window.VitBudsFilePreview.display(
            result,
            resultDiv,
            showRegression
        );
    }

    function displayMlxEvaluation(result) {
        window.VitBudsResultRenderers.mlxEvaluation(result, resultDiv);
    }

    function displayMaxEvaluation(result) {
        window.VitBudsResultRenderers.maxEvaluation(result, resultDiv);
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
        const showRegression = selectedType === 'show_files'
            && Boolean(previewRegressionInput?.checked);
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
            (selectedType === 'ppg_hr_analysis' && !hasLog);

        let analysisStartOffsetSec = 0;
        let analysisDurationSec = 0;

        if (usesAnalysisRange) {
            analysisStartOffsetSec = parseFloat(offsetInput.value);

            if (isNaN(analysisStartOffsetSec) || analysisStartOffsetSec < 0) {
                alert('解析開始オフセットには 0 以上の数値を入力してください．');
                offsetInput.focus();
                return;
            }

            const durationText = durationInput.value.trim();
            if (selectedType === 'ppg_hr_analysis' && durationText === '') {
                analysisDurationSec = 0;
            } else {
                analysisDurationSec = parseFloat(durationText);
                if (isNaN(analysisDurationSec) || analysisDurationSec <= 0) {
                    alert('解析時間には 0 より大きい数値を入力してください．');
                    durationInput.focus();
                    return;
                }
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

        if (selectedType === 'show_files') {
            formData.append(
                'preview_scale',
                previewScale?.value ?? 'same'
            );
        }

        previewColumns.forEach(columnNumber => {
            formData.append(
                'preview_columns[]',
                String(columnNumber)
            );
        });

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
                        displayFilePreview(result, showRegression);
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
