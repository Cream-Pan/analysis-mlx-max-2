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
        const uniqueId = `ppg-prv-analysis-${Date.now()}`;
        resultEl.id = uniqueId;
        const escapeHtml = value => String(value ?? '—').replace(/[&<>"']/g, character => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[character]);
        const number = (value, digits = 2, suffix = '') =>
            value == null || !Number.isFinite(Number(value))
                ? '—' : `${Number(value).toFixed(digits)}${suffix}`;
        let html = `<h3>${escapeHtml(result.title || 'PPG脈波解析結果（PRV・タスク別）')}</h3>`;

        if (result.status === 'error') {
            resultEl.innerHTML = `${html}<p class="error-message">${escapeHtml(result.message)}</p>`;
            resultContainer.appendChild(resultEl);
            return;
        }
        if (!Array.isArray(result.data) || result.data.length === 0) {
            resultEl.innerHTML = `${html}<p>解析結果がありません</p>`;
            resultContainer.appendChild(resultEl);
            return;
        }

        html += '<p>タスク開始時刻を基準に30秒ごとに解析します．グラフは各30秒窓の値を表示し，表はタスクごとの平均です．平均は品質判定が「採用」または「注意付き採用」の窓から算出します．*_HR.csvではHR_BPM列を使い，それ以外のCSVではIR_ValueからPPG→HR変換を実行します．RMSSD，SDNN，pPPI50はIR_Valueから検出した脈波間隔で算出します．30秒未満の残余区間は平均とグラフの対象外です．</p>';
        const rowsByFile = new Map();
        result.data.forEach(row => {
            const name = row.filename || 'ファイル名なし';
            if (!rowsByFile.has(name)) rowsByFile.set(name, []);
            rowsByFile.get(name).push(row);
        });
        const summariesByFile = new Map();
        (Array.isArray(result.task_summary) ? result.task_summary : []).forEach(summary => {
            const name = summary.filename || 'ファイル名なし';
            if (!summariesByFile.has(name)) summariesByFile.set(name, []);
            summariesByFile.get(name).push(summary);
        });

        const graphMetrics = {
            hr_bpm: { label: 'HR', unit: 'bpm', digits: 1 },
            rmssd_ms: { label: 'RMSSD', unit: 'ms', digits: 1 },
            sdnn_ms: { label: 'SDNN', unit: 'ms', digits: 1 },
            pppi50_pct: { label: 'pPPI50', unit: '%', digits: 1 }
        };
        const hasThirtySecondRows = result.data.some(row => row.window_kind === '30秒');
        if (hasThirtySecondRows) {
            const metricOptions = Object.entries(graphMetrics).map(([key, metric]) =>
                `<option value="${key}"${key === 'hr_bpm' ? ' selected' : ''}>${escapeHtml(metric.label)}（${escapeHtml(metric.unit)}）</option>`
            ).join('');
            html += `<section class="ppg-prv-chart-section">
                <h4>30秒ごとの推移</h4>
                <p>HR，RMSSD，SDNN，pPPI50の30秒ごとの推移です．品質判定が「採用」または「注意付き採用」の窓を表示し，除外窓は欠損として扱います．ホイール／ピンチで拡大し，ドラッグまたは下のスクロールバーで左右に移動できます．</p>
                <div class="ppg-prv-chart-controls screenshot-exclude" data-html2canvas-ignore="true">
                    <label for="${uniqueId}-metric">表示項目</label>
                    <select id="${uniqueId}-metric">${metricOptions}</select>
                    <button type="button" class="ppg-prv-reset-zoom">表示範囲をリセット</button>
                </div>
                <div class="ppg-prv-chart-container">
                    <canvas id="${uniqueId}-chart" aria-label="30秒ごとの指標推移"></canvas>
                </div>
                <div class="chart-range-scrollbar screenshot-exclude" data-html2canvas-ignore="true"
                    role="scrollbar" aria-label="グラフの表示範囲を左右に移動"
                    aria-orientation="horizontal" aria-valuemin="0" aria-valuemax="100"
                    aria-valuenow="0" tabindex="0" hidden>
                    <div class="chart-range-scrollbar-track">
                        <div class="chart-range-scrollbar-thumb"></div>
                    </div>
                </div>
                <p class="ppg-prv-chart-empty" hidden></p>
            </section>`;
        }

        rowsByFile.forEach((rows, filename) => {
            const summaries = (summariesByFile.get(filename) || [])
                .sort((a, b) => String(a.start_time).localeCompare(String(b.start_time)));
            html += `<h4>${escapeHtml(filename)}</h4>
                <div class="table-responsive"><table class="ppg-prv-results">
                <thead><tr>
                    <th>タスク</th><th>開始</th><th>終了</th><th>平均対象窓<br>（有効／全30秒窓）</th>
                    <th>HR平均</th><th>RMSSD平均</th><th>SDNN平均</th><th>pPPI50平均</th>
                </tr></thead><tbody>`;

            const averageCell = (summary, metric, digits, suffix) => {
                const value = summary[`mean_${metric}`];
                const count = summary[`${metric}_count`] || 0;
                return `<td>${number(value, digits, suffix)}<br><small>n=${count}</small></td>`;
            };
            summaries.forEach(summary => {
                html += `<tr>
                    <td>${escapeHtml(summary.task)}</td>
                    <td>${escapeHtml(summary.start_time)}</td>
                    <td>${escapeHtml(summary.end_time)}</td>
                    <td>${summary.included_window_count}/${summary.window_count}</td>
                    ${averageCell(summary, 'hr_bpm', 1, ' bpm')}
                    ${averageCell(summary, 'rmssd_ms', 1, ' ms')}
                    ${averageCell(summary, 'sdnn_ms', 1, ' ms')}
                    ${averageCell(summary, 'pppi50_pct', 1, ' %')}
                </tr>`;
            });
            html += '</tbody></table></div>';
        });

        html += `<div class="result-actions screenshot-exclude" data-html2canvas-ignore="true">
            <button type="button" class="save-ppg-hr-png-btn">PNG保存</button></div>`;
        resultEl.innerHTML = html;
        resultContainer.appendChild(resultEl);
        const chartCanvas = resultEl.querySelector('#' + uniqueId + '-chart');
        const metricSelect = resultEl.querySelector('#' + uniqueId + '-metric');
        const resetZoomButton = resultEl.querySelector('.ppg-prv-reset-zoom');
        if (chartCanvas && metricSelect && global.Chart) {
            const colors = ['#2563eb', '#dc2626', '#059669', '#9333ea'];
            const emptyMessage = resultEl.querySelector('.ppg-prv-chart-empty');
            const taskSpans = result.data
                .map(row => ({
                    task: row.task || 'タスク名なし',
                    start: Date.parse(row.start_time),
                    end: Date.parse(row.end_time)
                }))
                .filter(span => Number.isFinite(span.start) && Number.isFinite(span.end) && span.end > span.start)
                .sort((a, b) => a.task.localeCompare(b.task) || a.start - b.start);
            const mergedTaskSpans = [];
            taskSpans.forEach(span => {
                const previous = mergedTaskSpans[mergedTaskSpans.length - 1];
                if (previous && previous.task === span.task && span.start <= previous.end + 1000) {
                    previous.end = Math.max(previous.end, span.end);
                } else {
                    mergedTaskSpans.push({ ...span });
                }
            });
            const zoomLimits = mergedTaskSpans.length > 0
                ? {
                    min: Math.min(...mergedTaskSpans.map(span => span.start)),
                    max: Math.max(...mergedTaskSpans.map(span => span.end))
                }
                : { min: 'original', max: 'original' };
            const annotations = Object.fromEntries(mergedTaskSpans.map((span, index) => [
                `task-${index}`,
                {
                    type: 'box',
                    xMin: span.start,
                    xMax: span.end,
                    backgroundColor: 'rgba(100, 100, 100, 0.08)',
                    borderWidth: 0,
                    label: {
                        display: true,
                    content: span.task
                    }
                }
            ]));
            const taskBoundaries = [...new Set(mergedTaskSpans
                .flatMap(span => [span.start, span.end])
                .filter(time => time > zoomLimits.min && time < zoomLimits.max))]
                .sort((a, b) => a - b);
            taskBoundaries.forEach((time, index) => {
                annotations[`task-boundary-${index}`] = {
                    type: 'line',
                    xMin: time,
                    xMax: time,
                    borderColor: 'rgba(55, 65, 81, 0.62)',
                    borderWidth: 1,
                    borderDash: [4, 3],
                    z: 1
                };
            });
            let rangeControls = null;
            const chart = new global.Chart(chartCanvas, {
                type: 'line',
                data: { datasets: [] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'nearest', intersect: false },
                    elements: { line: { tension: 0.15 } },
                    plugins: {
                        legend: { position: 'bottom' },
                        annotation: { annotations },
                        zoom: {
                            limits: { x: zoomLimits },
                            zoom: {
                                wheel: { enabled: true },
                                pinch: { enabled: true },
                                mode: 'x',
                                onZoomComplete: () => rangeControls?.sync()
                            },
                            pan: {
                                enabled: true,
                                mode: 'x',
                                onPanComplete: () => rangeControls?.sync()
                            }
                        },
                        tooltip: {
                            callbacks: {
                                title(items) {
                                    const point = items[0]?.raw;
                                    if (!point) return '';
                                    return [
                                        new Date(point.x).toLocaleString('ja-JP'),
                                        point.task + '／' + point.window_kind + '窓' + point.window_index
                                    ];
                                },
                                label(context) {
                                    const point = context.raw;
                                    const metric = graphMetrics[metricSelect.value];
                                    const quality = point.quality_status
                                        ? '（' + point.quality_status + '）' : '';
                                    return context.dataset.label + ': '
                                        + number(point.y, metric.digits, ' ' + metric.unit) + quality;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            type: 'time',
                            min: Number.isFinite(zoomLimits.min) ? zoomLimits.min : undefined,
                            max: Number.isFinite(zoomLimits.max) ? zoomLimits.max : undefined,
                            time: { unit: 'minute' },
                            title: { display: true, text: '時刻' },
                            ticks: {
                                autoSkip: true,
                                maxTicksLimit: 8,
                                callback(value) {
                                    return new Date(Number(value)).toLocaleString('ja-JP', {
                                        month: 'numeric', day: 'numeric',
                                        hour: '2-digit', minute: '2-digit'
                                    });
                                }
                            }
                        },
                        y: {
                            title: { display: true, text: '' },
                            beginAtZero: false
                        }
                    }
                }
            });
            rangeControls = global.VitBudsChartRangeControls?.attach({
                chart,
                domainMin: zoomLimits.min,
                domainMax: zoomLimits.max,
                scrollbar: resultEl.querySelector('.chart-range-scrollbar'),
                resetButton: resetZoomButton
            });
            const updateChart = () => {
                const metric = graphMetrics[metricSelect.value];
                chart.data.datasets = [...rowsByFile.entries()]
                    .map(([filename, rows], index) => {
                        const points = rows
                            .filter(row => row.window_kind === '30秒')
                            .sort((a, b) => String(a.start_time).localeCompare(String(b.start_time)))
                            .map(row => {
                                const value = Number(row[metricSelect.value]);
                                const isExcluded = row.quality_status === '除外' || row.status === 'error';
                                return {
                                    x: Date.parse(row.start_time),
                                    y: isExcluded || row[metricSelect.value] == null || !Number.isFinite(value)
                                        ? null : value,
                                    task: row.task || 'タスク名なし',
                                    window_kind: row.window_kind,
                                    window_index: row.window_index,
                                    quality_status: row.quality_status || row.status || ''
                                };
                            })
                            .filter(point => Number.isFinite(point.x));
                        return {
                            label: filename,
                            data: points,
                            parsing: false,
                            borderColor: colors[index % colors.length],
                            backgroundColor: colors[index % colors.length],
                            pointRadius: 2,
                            pointHoverRadius: 5,
                            spanGaps: false
                        };
                    })
                    .filter(dataset => dataset.data.length > 0);
                const hasValues = chart.data.datasets.some(dataset =>
                    dataset.data.some(point => point.y != null)
                );
                chart.options.scales.y.title.text = metric.label + '（' + metric.unit + '）';
                emptyMessage.hidden = hasValues;
                emptyMessage.textContent = hasValues
                    ? '' : '選択した項目に表示できる値がありません．';
                chartCanvas.hidden = !hasValues;
                chart.update();
            };
            metricSelect.addEventListener('change', updateChart);
            updateChart();
        } else if (chartCanvas) {
            chartCanvas.parentElement.innerHTML = '<p class="ppg-prv-chart-empty">グラフを表示できません．</p>';
        }
        resultEl.querySelector('.save-ppg-hr-png-btn')?.addEventListener(
            'click', () => saveResultsAsPng(uniqueId)
        );
    };
})(window);
