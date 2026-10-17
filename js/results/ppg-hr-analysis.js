/* PPG脈波解析結果の表示を担当する． */
(function registerPpgHrRenderer(global) {
    const renderers = global.VitBudsResultRenderers
        || (global.VitBudsResultRenderers = {});

    renderers.ppgHrAnalysis = function renderPpgHrAnalysis(
        result,
        resultContainer,
        saveResultsAsPng
    ) {
        const resultEl = document.createElement('div');
        resultEl.className = 'result-item';
        const uniqueId = `ppg-hr-analysis-${Date.now()}`;
        resultEl.id = uniqueId;
        const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[character]);

        let html = `<h3>${result.title || 'PPG脈波解析結果'}</h3>`;

        if (result.status === 'error') {
            html += `<p style="color: red; font-weight: bold;">エラー: ${result.message}</p>`;
            resultEl.innerHTML = html;
            resultContainer.appendChild(resultEl);
            return;
        }

        if (!result.data || result.data.length === 0) {
            html += `<p style="color: orange; font-weight: bold;">解析結果がありません</p>`;
            resultEl.innerHTML = html;
            resultContainer.appendChild(resultEl);
            return;
        }

        const rowsByFile = new Map();
        result.data.forEach(row => {
            const filename = row.filename || 'ファイル名なし';
            if (!rowsByFile.has(filename)) {
                rowsByFile.set(filename, []);
            }
            rowsByFile.get(filename).push(row);
        });

        rowsByFile.forEach((rows, filename) => {
            html += `
                <h4>${escapeHtml(filename)}</h4>
                <table>
                    <thead>
                        <tr>
                            <th>タスク／区間</th>
                            <th>状態</th>
                            <th>解析開始</th>
                            <th>解析終了</th>
                            <th>有効間隔数</th>
                            <th>データ品質</th>
                            <th>LF</th>
                            <th>HF</th>
                            <th>LF/HF</th>
                            <th>NN50</th>
                            <th>PNN50</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            rows.forEach(row => {
                const lf = row.lf_power == null ? 'N/A' : Number(row.lf_power).toFixed(4);
                const hf = row.hf_power == null ? 'N/A' : Number(row.hf_power).toFixed(4);
                const lfHf = row.lf_hf == null ? 'N/A' : Number(row.lf_hf).toFixed(4);
                const pnn50 = row.pnn50 == null ? 'N/A' : `${Number(row.pnn50).toFixed(2)} %`;
                const validIntervalPct = row.valid_interval_pct == null
                    ? 'N/A'
                    : `${Number(row.valid_interval_pct).toFixed(1)} %`;
                const sampleRate = row.sample_rate_hz == null
                    ? 'N/A'
                    : `${Number(row.sample_rate_hz).toFixed(2)} Hz`;
                const qualityDetails = [
                    `サンプル数 ${row.sample_count ?? 'N/A'}`,
                    `Fs ${sampleRate}`,
                    `有効間隔率 ${validIntervalPct}`,
                    `時刻ギャップ ${row.sample_gap_count ?? 'N/A'}`
                ].join('，');
                const frequencyNote = row.frequency_status
                    && row.frequency_status !== '計算済み'
                    ? `<br>${escapeHtml(row.frequency_status)}`
                    : '';
                const status = row.status === 'error'
                    ? `解析不可：${row.message || '指標を計算できませんでした'}`
                    : '完了';

                html += `
                    <tr>
                        <td>${escapeHtml(row.task || '-')}</td>
                        <td>${escapeHtml(status)}</td>
                        <td>${escapeHtml(row.start_time)}</td>
                        <td>${escapeHtml(row.end_time)}</td>
                        <td>${row.nn_count ?? 'N/A'}</td>
                        <td>${escapeHtml(qualityDetails)}${frequencyNote}</td>
                        <td>${lf}</td>
                        <td>${hf}</td>
                        <td>${lfHf}</td>
                        <td>${row.nn50 ?? 'N/A'}</td>
                        <td>${pnn50}</td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;
        });

        html += `
                    </tbody>
                </table>
                <div class="result-actions screenshot-exclude" data-html2canvas-ignore="true">
                    <button type="button" class="save-ppg-hr-png-btn">PNG保存</button>
                </div>
        `;

        resultEl.innerHTML = html;
        resultContainer.appendChild(resultEl);

        resultEl.querySelector('.save-ppg-hr-png-btn')?.addEventListener(
            'click',
            () => saveResultsAsPng(uniqueId)
        );
    };
})(window);
