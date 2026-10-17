/* MLX／MAX評価結果の表示と共通指標整形を担当する． */
(function registerEvaluationRenderers(global) {
    const renderers = global.VitBudsResultRenderers
        || (global.VitBudsResultRenderers = {});
    const formatters = global.VitBudsResultFormatters
        || (global.VitBudsResultFormatters = {});

    function displayError(result, resultDiv) {
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

    function displayMlxEvaluation(result, resultDiv) {
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

    function displayMaxEvaluation(result, resultDiv) {
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

    renderers.error = displayError;
    renderers.mlxEvaluation = displayMlxEvaluation;
    renderers.maxEvaluation = displayMaxEvaluation;
    formatters.metrics = {
        formatMlxMetric,
        formatMaxMetric
    };
})(window);
