/* PPG＋ACC結果テーブルの行HTMLを組み立てる． */
(function registerPpgAccTableRows(global) {
    const renderers = global.VitBudsResultRenderers
        || (global.VitBudsResultRenderers = {});

    renderers.ppgAccSummaryRows = function renderPpgAccSummaryRows(
        rows,
        formatters,
        formatMetric
    ) {
        const formatValue = formatters.formatValue;
        const formatErrorMetric = value =>
            formatters.formatErrorMetric(value, formatMetric);

        return rows.map(row => `
            <tr>
                <td>${row.Task_Name ?? '―'}</td>
                <td class="metric-cell">${formatErrorMetric(row.MAE)}</td>
                <td class="metric-cell">${formatErrorMetric(row.RMSE)}</td>
                <td class="metric-cell">${formatValue(row.Bias, 4)}</td>
                <td>${row.Evaluation ?? '―'}</td>
                <td>${row.Valid_Pair_Count ?? 0}</td>
                <td>${formatValue(row.Valid_Pair_Rate, 1, ' %')}</td>
                <td class="quality-cell">${row.Fin_Total_Window_Count ?? 0}</td>
                <td class="quality-cell">${formatValue(row.Fin_Lost_Rate, 1, ' %')}</td>
                <td class="quality-cell">${formatValue(row.Fin_Motion_Artifact_Rate, 1, ' %')}</td>
                <td class="quality-cell">${formatValue(row.Fin_HR_Usable_Rate, 1, ' %')}</td>
                <td class="quality-cell">${row.Ear_Total_Window_Count ?? 0}</td>
                <td class="quality-cell">${formatValue(row.Ear_Lost_Rate, 1, ' %')}</td>
                <td class="quality-cell">${formatValue(row.Ear_Motion_Artifact_Rate, 1, ' %')}</td>
                <td class="quality-cell">${formatValue(row.Ear_HR_Usable_Rate, 1, ' %')}</td>
            </tr>
        `).join('');
    };

    renderers.ppgAccFrequencyRows = function renderPpgAccFrequencyRows(
        rows,
        formatters
    ) {
        const formatValue = formatters.formatValue;
        const formatPsdPeak = formatters.formatPsdPeak;

        return rows.map(row => `
            <tr>
                <td>${row.Task_Name ?? '―'}</td>
                <td>${formatPsdPeak(row.Fin_Task_PPG_PSD_Peak_Hz, row.Fin_Task_PPG_PSD_Peak_Value)}</td>
                <td>${formatPsdPeak(row.Fin_Task_ACC_PSD_Peak_Hz, row.Fin_Task_ACC_PSD_Peak_Value)}</td>
                <td>${formatValue(row.Fin_HR_Selected_Hz_Median, 3, ' Hz')}</td>
                <td>
                    PPG－ACC：${formatValue(row.Fin_Task_PPG_ACC_PSD_Diff_Hz, 3, ' Hz')}<br>
                    PPG－HR：${formatValue(row.Fin_Task_PPG_PSD_HR_Diff_Hz, 3, ' Hz')}
                </td>
                <td>${formatPsdPeak(row.Ear_Task_PPG_PSD_Peak_Hz, row.Ear_Task_PPG_PSD_Peak_Value)}</td>
                <td>${formatPsdPeak(row.Ear_Task_ACC_PSD_Peak_Hz, row.Ear_Task_ACC_PSD_Peak_Value)}</td>
                <td>${formatValue(row.Ear_HR_Selected_Hz_Median, 3, ' Hz')}</td>
                <td>
                    PPG－ACC：${formatValue(row.Ear_Task_PPG_ACC_PSD_Diff_Hz, 3, ' Hz')}<br>
                    PPG－HR：${formatValue(row.Ear_Task_PPG_PSD_HR_Diff_Hz, 3, ' Hz')}
                </td>
            </tr>
        `).join('');
    };
})(window);
