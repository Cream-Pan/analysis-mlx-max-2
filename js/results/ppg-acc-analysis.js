/* PPG＋ACC解析結果全体の表示を担当する． */
(function registerPpgAccRenderer(global) {
    const renderers = global.VitBudsResultRenderers
        || (global.VitBudsResultRenderers = {});

    renderers.ppgAccAnalysis = function renderPpgAccAnalysis(
        result,
        resultContainer,
        formatMetric,
        saveResultsAsPng,
        downloadCsvText
    ) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        const uniqueId = `ppg-acc-analysis-${Date.now()}-`
            + Math.random().toString(36).slice(2, 7);
        resultEl.id = uniqueId;

        let html = `<h3>${result.title || 'PPG＋ACC解析結果'}</h3>`;
        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
            resultEl.innerHTML = html;
            resultContainer.appendChild(resultEl);
            return;
        }

        const rows = Array.isArray(result.data) ? result.data : [];
        const formatters = global.VitBudsResultFormatters.ppgAcc;

        html += `
            <p>
                Fin：<b>${result.fin_filename || '不明'}</b>（${result.fin_fs ?? '―'} Hz）<br>
                耳たぶ：<b>${result.ear_filename || '不明'}</b>（${result.ear_fs ?? '―'} Hz）
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
                            <th class="quality-column">Fin全窓数</th>
                            <th class="quality-column">Fin Lost率</th>
                            <th class="quality-column">Fin Motion Artifact率</th>
                            <th class="quality-column">Fin HR利用可能率</th>
                            <th class="quality-column">耳たぶ全窓数</th>
                            <th class="quality-column">耳たぶ Lost率</th>
                            <th class="quality-column">耳たぶ Motion Artifact率</th>
                            <th class="quality-column">耳たぶ HR利用可能率</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        html += renderers.ppgAccSummaryRows(rows, formatters, formatMetric);
        if (rows.length === 0) {
            html += '<tr><td colspan="15">表示できる解析結果がありません．</td></tr>';
        }

        html += `
                    </tbody>
                </table>
            </div>
            <h4>タスク別PSD・周波数比較</h4>
            <p style="font-size: 0.9em; color: #555;">
                PSDは0.8～3.0 Hzを対象に，10 s Hann窓・5 s間隔のWelch法で算出しています．
                HR採用周波数は，各タスク内でHR推定に成功した10 s窓の中央値です．
            </p>
            <div class="table-scroll">
                <table class="ppg-acc-table">
                    <thead>
                        <tr>
                            <th>タスク名</th>
                            <th>Fin PPG最大PSD</th>
                            <th>Fin ACC最大PSD</th>
                            <th>Fin HR採用周波数中央値</th>
                            <th>Fin 周波数差</th>
                            <th>耳たぶ PPG最大PSD</th>
                            <th>耳たぶ ACC最大PSD</th>
                            <th>耳たぶ HR採用周波数中央値</th>
                            <th>耳たぶ 周波数差</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        html += renderers.ppgAccFrequencyRows(rows, formatters);
        if (rows.length === 0) {
            html += '<tr><td colspan="9">表示できるPSD結果がありません．</td></tr>';
        }

        html += `
                    </tbody>
                </table>
            </div>
            <div class="result-actions screenshot-exclude" data-html2canvas-ignore="true">
                <button class="save-ppg-acc-png-btn">PNG保存</button>
                ${result.summary_download ? `
                    <button class="download-ppg-acc-summary-btn">タスク別結果CSVダウンロード</button>
                ` : ''}
                ${result.detail_download ? `
                    <button class="download-ppg-acc-detail-btn">窓詳細CSVダウンロード</button>
                ` : ''}
            </div>
        `;

        resultEl.innerHTML = html;
        resultContainer.appendChild(resultEl);
        global.VitBudsResultActions.bindPpgAcc(
            resultEl,
            result,
            uniqueId,
            saveResultsAsPng,
            downloadCsvText
        );
    };
})(window);
