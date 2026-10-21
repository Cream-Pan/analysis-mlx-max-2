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

        html += '<p>タスク開始時刻を基準に1分ごとに解析します．60秒未満の残余区間はスペクトルHRのみを表示します．品質基準は暫定値です．安静との差は算出しません．</p>';
        const rowsByFile = new Map();
        result.data.forEach(row => {
            const name = row.filename || 'ファイル名なし';
            if (!rowsByFile.has(name)) rowsByFile.set(name, []);
            rowsByFile.get(name).push(row);
        });

        const graphMetrics = {
            rmssd_ms: { label: 'RMSSD', unit: 'ms', digits: 1 },
            pppi50_pct: { label: 'pPPI50', unit: '%', digits: 1 },
            mean_hr_bpm: { label: 'PPI由来HR', unit: 'bpm', digits: 1 },
            spectral_hr_bpm: { label: 'スペクトルHR', unit: 'bpm', digits: 1 },
            mean_ppi_ms: { label: '平均PPI', unit: 'ms', digits: 1 },
            accel_rms_g: { label: 'ACC RMS', unit: 'g', digits: 4 }
        };
        const hasMinuteRows = result.data.some(row => row.window_kind === '1分');
        if (hasMinuteRows) {
            const metricOptions = Object.entries(graphMetrics).map(([key, metric]) =>
                `<option value="${key}"${key === 'rmssd_ms' ? ' selected' : ''}>${escapeHtml(metric.label)}（${escapeHtml(metric.unit)}）</option>`
            ).join('');
            html += `<section class="ppg-prv-chart-section">
                <h4>1分ごとの推移</h4>
                <p>品質判定が「採用」または「注意付き採用」の1分窓を表示します．除外窓は欠損として扱います．ホイール／ピンチで拡大し，ドラッグまたは下のスクロールバーで左右に移動できます．</p>
                <div class="ppg-prv-chart-controls screenshot-exclude" data-html2canvas-ignore="true">
                    <label for="${uniqueId}-metric">表示項目</label>
                    <select id="${uniqueId}-metric">${metricOptions}</select>
                    <button type="button" class="ppg-prv-reset-zoom">表示範囲をリセット</button>
                </div>
                <div class="ppg-prv-chart-container">
                    <canvas id="${uniqueId}-chart" aria-label="1分ごとの指標推移"></canvas>
                </div>
                <div class="ppg-prv-scrollbar screenshot-exclude" data-html2canvas-ignore="true"
                    role="scrollbar" aria-label="グラフの表示時刻を左右に移動"
                    aria-orientation="horizontal" aria-valuemin="0" aria-valuemax="100"
                    aria-valuenow="0" tabindex="0" hidden>
                    <div class="ppg-prv-scrollbar-track">
                        <div class="ppg-prv-scrollbar-thumb"></div>
                    </div>
                </div>
                <p class="ppg-prv-chart-empty" hidden></p>
            </section>`;
        }

        rowsByFile.forEach((rows, filename) => {
            rows.sort((a, b) => String(a.start_time).localeCompare(String(b.start_time))
                || (a.window_kind === '1分' ? -1 : 1));
            html += `<h4>${escapeHtml(filename)}</h4>
                <div class="table-responsive"><table class="ppg-prv-results">
                <thead><tr>
                    <th>タスク／窓</th><th>品質判定</th><th>開始</th><th>終了</th>
                    <th>有効PPG窓</th><th>有効PPI</th><th>スペクトルHR</th>
                    <th>平均PPI</th><th>PPI由来HR</th><th>RMSSD</th><th>pPPI50</th>
                    <th>ACC RMS</th><th>ACC主周波数</th><th>PPG–ACC重複</th><th>低体動窓</th>
                    <th>HR急変警告</th>
                    <th>左右差（右−左）</th><th>LF</th><th>HF</th><th>LF/HF・備考</th>
                </tr></thead><tbody>`;

            rows.forEach(row => {
                const validPpg = row.valid_spectral_window_count == null
                    ? '—' : `${row.valid_spectral_window_count}/${row.spectral_window_count ?? 0} (${number(row.valid_spectral_pct, 1, ' %')})`;
                const validPpi = number(row.valid_ppi_pct, 1, ' %');
                const delta = row.right_minus_left
                    ? `HR ${number(row.right_minus_left.mean_hr_bpm, 2)} bpm<br>`
                        + `PPI ${number(row.right_minus_left.mean_ppi_ms, 1)} ms<br>`
                        + `RMSSD ${number(row.right_minus_left.rmssd_ms, 1)} ms<br>`
                        + `pPPI50 ${number(row.right_minus_left.pppi50_pct, 1, ' %')}`
                    : '—';
                const status = row.quality_status || row.status || '—';
                const note = [row.frequency_status, row.message]
                    .filter(Boolean).join('；');
                html += `<tr>
                    <td>${escapeHtml(row.task)}<br>${escapeHtml(row.window_kind)} ${row.window_index ?? ''}</td>
                    <td>${escapeHtml(status)}</td>
                    <td>${escapeHtml(row.start_time)}</td><td>${escapeHtml(row.end_time)}</td>
                    <td>${validPpg}</td><td>${validPpi}</td>
                    <td>${number(row.spectral_hr_bpm, 1, ' bpm')}</td>
                    <td>${number(row.mean_ppi_ms, 1, ' ms')}</td>
                    <td>${number(row.mean_hr_bpm, 1, ' bpm')}</td>
                    <td>${number(row.rmssd_ms, 1, ' ms')}</td>
                    <td>${number(row.pppi50_pct, 1, ' %')}</td>
                    <td>${number(row.accel_rms_g, 4, ' g')}</td>
                    <td>${number(row.accel_dominant_hz, 2, ' Hz')}</td>
                    <td>${number(row.ppg_acc_overlap_pct, 1, ' %')}</td>
                    <td>${number(row.low_motion_pct, 1, ' %')}</td>
                    <td>${row.hr_continuity_warning ? `あり（${row.hr_jump_count ?? 0}回）` : 'なし'}</td>
                    <td>${delta}</td>
                    <td>${number(row.lf_power, 5)}</td><td>${number(row.hf_power, 5)}</td>
                    <td>${number(row.lf_hf, 3)}<br>${escapeHtml(note)}</td>
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
            const colors = ['#2563eb', '#dc2626', '#059669', '#9333ea', '#d97706', '#0891b2'];
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
                        content: span.task,
                        position: 'start',
                        color: '#4b5563',
                        backgroundColor: 'rgba(255, 255, 255, 0.72)',
                        font: { size: 11, weight: '600' },
                        padding: 3
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
            let syncScrollbar = () => {};
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
                                onZoomComplete: () => syncScrollbar()
                            },
                            pan: {
                                enabled: true,
                                mode: 'x',
                                onPanComplete: () => syncScrollbar()
                            }
                        },
                        tooltip: {
                            callbacks: {
                                title(items) {
                                    const point = items[0]?.raw;
                                    return point
                                        ? point.task + '／' + point.window_kind + '窓' + point.window_index
                                        : '';
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
            const scrollbar = resultEl.querySelector('.ppg-prv-scrollbar');
            const scrollbarTrack = scrollbar?.querySelector('.ppg-prv-scrollbar-track');
            const scrollbarThumb = scrollbar?.querySelector('.ppg-prv-scrollbar-thumb');
            const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
            const readVisibleRange = () => ({
                min: Number(chart.scales.x.min),
                max: Number(chart.scales.x.max)
            });
            syncScrollbar = () => {
                if (!scrollbar || !scrollbarTrack || !scrollbarThumb
                    || !Number.isFinite(zoomLimits.min) || !Number.isFinite(zoomLimits.max)) return;
                const { min, max } = readVisibleRange();
                const total = zoomLimits.max - zoomLimits.min;
                if (!Number.isFinite(min) || !Number.isFinite(max) || total <= 0) return;
                const visible = clamp(max - min, 0, total);
                const ratio = visible / total;
                const thumbWidth = clamp(ratio * 100, 6, 100);
                const availableRange = Math.max(0, total - visible);
                const position = availableRange > 0
                    ? clamp((min - zoomLimits.min) / availableRange, 0, 1) : 0;
                scrollbarThumb.style.width = `${thumbWidth}%`;
                scrollbarThumb.style.left = `${position * (100 - thumbWidth)}%`;
                scrollbar.hidden = ratio >= 0.9999;
                scrollbar.setAttribute('aria-valuenow', String(Math.round(position * 100)));
                scrollbar.setAttribute('aria-valuetext',
                    `${new Date(min).toLocaleString('ja-JP')} から ${new Date(max).toLocaleString('ja-JP')}`);
            };
            const setVisibleStart = requestedMin => {
                const { min, max } = readVisibleRange();
                const total = zoomLimits.max - zoomLimits.min;
                const visible = clamp(max - min, 0, total);
                if (!Number.isFinite(total) || total <= 0 || visible >= total) return;
                const nextMin = clamp(requestedMin, zoomLimits.min, zoomLimits.max - visible);
                chart.options.scales.x.min = nextMin;
                chart.options.scales.x.max = nextMin + visible;
                chart.update('none');
                syncScrollbar();
            };
            let dragState = null;
            scrollbarThumb?.addEventListener('pointerdown', event => {
                event.preventDefault();
                const { min } = readVisibleRange();
                dragState = { pointerId: event.pointerId, startX: event.clientX, startMin: min };
                scrollbarThumb.setPointerCapture(event.pointerId);
            });
            scrollbarThumb?.addEventListener('pointermove', event => {
                if (!dragState || dragState.pointerId !== event.pointerId || !scrollbarTrack) return;
                const { min, max } = readVisibleRange();
                const total = zoomLimits.max - zoomLimits.min;
                const visible = clamp(max - min, 0, total);
                const travel = Math.max(0, total - visible);
                const trackWidth = scrollbarTrack.getBoundingClientRect().width;
                const thumbWidth = scrollbarThumb.getBoundingClientRect().width;
                const travelPixels = Math.max(1, trackWidth - thumbWidth);
                setVisibleStart(dragState.startMin
                    + (event.clientX - dragState.startX) / travelPixels * travel);
            });
            const endScrollbarDrag = event => {
                if (dragState?.pointerId === event.pointerId) dragState = null;
            };
            scrollbarThumb?.addEventListener('pointerup', endScrollbarDrag);
            scrollbarThumb?.addEventListener('pointercancel', endScrollbarDrag);
            scrollbarTrack?.addEventListener('pointerdown', event => {
                if (event.target === scrollbarThumb || scrollbarThumb?.contains(event.target)) return;
                const rect = scrollbarTrack.getBoundingClientRect();
                const thumbWidth = scrollbarThumb?.getBoundingClientRect().width || 0;
                const travelPixels = Math.max(1, rect.width - thumbWidth);
                const fraction = clamp((event.clientX - rect.left - thumbWidth / 2) / travelPixels, 0, 1);
                const { min, max } = readVisibleRange();
                const visible = clamp(max - min, 0, zoomLimits.max - zoomLimits.min);
                setVisibleStart(zoomLimits.min + fraction * (zoomLimits.max - zoomLimits.min - visible));
            });
            scrollbar?.addEventListener('keydown', event => {
                const { min, max } = readVisibleRange();
                const visible = Math.max(0, max - min);
                let nextMin;
                if (event.key === 'ArrowLeft') nextMin = min - visible * 0.1;
                else if (event.key === 'ArrowRight') nextMin = min + visible * 0.1;
                else if (event.key === 'PageUp') nextMin = min - visible * 0.8;
                else if (event.key === 'PageDown') nextMin = min + visible * 0.8;
                else if (event.key === 'Home') nextMin = zoomLimits.min;
                else if (event.key === 'End') nextMin = zoomLimits.max - visible;
                else return;
                event.preventDefault();
                setVisibleStart(nextMin);
            });
            const updateChart = () => {
                const metric = graphMetrics[metricSelect.value];
                chart.data.datasets = [...rowsByFile.entries()]
                    .map(([filename, rows], index) => {
                        const points = rows
                            .filter(row => row.window_kind === '1分')
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
            resetZoomButton?.addEventListener('click', () => {
                chart.resetZoom();
                if (Number.isFinite(zoomLimits.min) && Number.isFinite(zoomLimits.max)) {
                    chart.options.scales.x.min = zoomLimits.min;
                    chart.options.scales.x.max = zoomLimits.max;
                } else {
                    delete chart.options.scales.x.min;
                    delete chart.options.scales.x.max;
                }
                chart.update('none');
                syncScrollbar();
            });
            updateChart();
        } else if (chartCanvas) {
            chartCanvas.parentElement.innerHTML = '<p class="ppg-prv-chart-empty">グラフを表示できません．</p>';
        }
        resultEl.querySelector('.save-ppg-hr-png-btn')?.addEventListener(
            'click', () => saveResultsAsPng(uniqueId)
        );
    };
})(window);
