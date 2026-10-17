/* PPG HR比較結果の表示を担当する． */
(function registerPpgComparisonRenderer(global) {
    const renderers = global.VitBudsResultRenderers
        || (global.VitBudsResultRenderers = {});

    renderers.ppgComparison = function renderPpgComparison(
        result,
        resultContainer,
        formatMaxMetric,
        saveResultsAsPng
    ) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        const uniqueId = `ppg-analysis-${Date.now()}`;
        resultEl.id = uniqueId;
        let html = `<h3>${result.title}</h3>`;

        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
            resultEl.innerHTML = html;
            resultContainer.appendChild(resultEl);
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
                <button class="save-ppg-analysis-png-btn">PNG保存</button>
            </div>
        `;
        resultEl.innerHTML = html;
        resultContainer.appendChild(resultEl);
        resultEl.querySelector('.save-ppg-analysis-png-btn')?.addEventListener(
            'click',
            () => saveResultsAsPng(uniqueId)
        );
    };
})(window);
