/* PPGからHRへの変換結果表示を担当する． */
(function registerPpgToHrRenderer(global) {
    const renderers = global.VitBudsResultRenderers
        || (global.VitBudsResultRenderers = {});

    renderers.ppgToHr = function renderPpgToHr(
        result,
        resultContainer,
        downloadCsvText
    ) {
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
            resultContainer.appendChild(resultEl);
            return;
        }

        const fs = result.summary?.fs ?? 'N/A';
        const overallCorr = result.summary?.overall_corr;
        const corrText = overallCorr === null || overallCorr === undefined
            ? 'N/A'
            : Number(overallCorr).toFixed(4);

        html += `
            <table>
                <thead>
                    <tr><th>項目</th><th>値</th></tr>
                </thead>
                <tbody>
                    <tr><td>Fs</td><td>${fs} Hz</td></tr>
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
        resultContainer.appendChild(resultEl);

        const hrDownloadButton = resultEl.querySelector('.download-hr-csv-btn');
        if (hrDownloadButton && result.download) {
            hrDownloadButton.addEventListener('click', () => {
                downloadCsvText(
                    result.download.filename,
                    result.download.csv_text
                );
            });
        }
    };
})(window);
