/* CSV／Excelの列グラフ表示を担当する． */
(function registerFilePreview(global) {
    function drawFixedYAxis(chart, axisCanvas, axisTitle) {
        const yScale = chart.scales?.y;
        if (!yScale || !axisCanvas) {
            return;
        }

        const cssWidth = 92;
        const cssHeight = chart.height;
        const devicePixelRatio = window.devicePixelRatio || 1;

        axisCanvas.style.width = `${cssWidth}px`;
        axisCanvas.style.height = `${cssHeight}px`;
        axisCanvas.width = Math.round(cssWidth * devicePixelRatio);
        axisCanvas.height = Math.round(cssHeight * devicePixelRatio);

        const context = axisCanvas.getContext('2d');
        context.setTransform(
            devicePixelRatio,
            0,
            0,
            devicePixelRatio,
            0,
            0
        );

        context.clearRect(0, 0, cssWidth, cssHeight);
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, cssWidth, cssHeight);

        const chartArea = chart.chartArea;
        const axisX = cssWidth - 1;

        context.strokeStyle = '#666';
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(axisX, chartArea.top);
        context.lineTo(axisX, chartArea.bottom);
        context.stroke();

        context.font = "12px 'Segoe UI', sans-serif";
        context.fillStyle = '#666';
        context.textAlign = 'right';
        context.textBaseline = 'middle';

        yScale.ticks.forEach((tick, index) => {
            const y = yScale.getPixelForTick(index);
            if (y < chartArea.top || y > chartArea.bottom) {
                return;
            }

            context.strokeStyle = '#666';
            context.beginPath();
            context.moveTo(axisX - 5, y);
            context.lineTo(axisX, y);
            context.stroke();

            const label = tick.label ?? tick.value;
            context.fillText(String(label), axisX - 8, y);
        });

        if (axisTitle) {
            context.save();
            context.translate(
                14,
                (chartArea.top + chartArea.bottom) / 2
            );
            context.rotate(-Math.PI / 2);
            context.textAlign = 'center';
            context.textBaseline = 'middle';
            context.font = "bold 12px 'Segoe UI', sans-serif";
            context.fillStyle = '#333';
            context.fillText(axisTitle, 0, 0);
            context.restore();
        }
    }

    function displayFilePreview(result, resultDiv) {
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
                let columnSelector = null;
                if (sheet.series && sheet.series.length > 0) {
                    if (sheet.sheet_name) {
                        const sheetTitle = document.createElement('h5');
                        sheetTitle.className = 'file-chart-sheet-title';
                        sheetTitle.textContent =
                            `シート: ${sheet.sheet_name}`;
                        resultEl.appendChild(sheetTitle);
                    }

                    // 表示列切替チェックボックス
                    columnSelector = document.createElement('div');
                    columnSelector.className = 'column-selector';

                    const selectorTitle = document.createElement('b');
                    selectorTitle.textContent = '表示列: ';
                    columnSelector.appendChild(selectorTitle);

                    sheet.series.forEach((series, index) => {

                        const label = document.createElement('label');

                        const checkbox = document.createElement('input');

                        checkbox.type = 'checkbox';
                        checkbox.checked = true;

                        checkbox.dataset.datasetIndex = index;

                        const columnName =
                            sheet.columns?.[series.column_number - 1]
                            ?? `${series.column_number}列目`;

                        label.appendChild(checkbox);

                        label.appendChild(
                            document.createTextNode(
                                columnName
                            )
                        );

                        columnSelector.appendChild(label);
                    });

                    resultEl.appendChild(columnSelector);
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

                const availableChartWidth = Math.max(
                    320,
                    Math.floor(
                        (resultEl.getBoundingClientRect().width || 992) - 92
                    )
                );

                const chartLayout = document.createElement('div');
                chartLayout.className = 'file-chart-layout';
                chartLayout.style.display = 'flex';
                chartLayout.style.alignItems = 'stretch';
                chartLayout.style.width = '100%';
                chartLayout.style.maxWidth = '100%';

                const fixedAxisContainer = document.createElement('div');
                fixedAxisContainer.className = 'file-chart-fixed-y-axis';
                fixedAxisContainer.style.flex = '0 0 92px';
                fixedAxisContainer.style.width = '92px';
                fixedAxisContainer.style.height = '420px';
                fixedAxisContainer.style.background = '#fff';
                fixedAxisContainer.style.position = 'relative';
                fixedAxisContainer.style.zIndex = '2';

                const fixedAxisCanvas = document.createElement('canvas');
                fixedAxisCanvas.width = 92;
                fixedAxisCanvas.height = 420;
                fixedAxisContainer.appendChild(fixedAxisCanvas);

                const scrollContainer = document.createElement('div');
                scrollContainer.className = 'file-chart-scroll';
                scrollContainer.style.flex = '1 1 auto';
                scrollContainer.style.minWidth = '0';
                scrollContainer.style.overflowX = 'hidden';
                scrollContainer.style.overflowY = 'hidden';

                const chartInner = document.createElement('div');
                chartInner.className = 'file-chart-inner';
                chartInner.style.width = '100%';
                chartInner.style.minWidth = '0';
                chartInner.style.height = '420px';

                const canvas = document.createElement('canvas');
                canvas.width = availableChartWidth;
                canvas.height = 420;
                canvas.style.display = 'block';
                canvas.style.width = '100%';
                canvas.style.height = '100%';

                chartInner.appendChild(canvas);
                scrollContainer.appendChild(chartInner);
                const chartControls = document.createElement('div');
                chartControls.className = 'file-chart-controls screenshot-exclude';
                chartControls.setAttribute('data-html2canvas-ignore', 'true');
                const resetZoomButton = document.createElement('button');
                resetZoomButton.type = 'button';
                resetZoomButton.className = 'file-chart-reset-zoom';
                resetZoomButton.textContent = '表示範囲をリセット';
                chartControls.appendChild(resetZoomButton);
                const interactionHelp = document.createElement('span');
                interactionHelp.textContent = 'ホイール／ピンチで拡大，ドラッグまたは下のバーで横移動できます．';
                chartControls.appendChild(interactionHelp);
                const regressionLabel = document.createElement('label');
                regressionLabel.className = 'file-regression-control';
                const regressionToggle = document.createElement('input');
                regressionToggle.type = 'checkbox';
                regressionToggle.checked = false;
                regressionLabel.appendChild(regressionToggle);
                regressionLabel.appendChild(
                    document.createTextNode('回帰式を表示')
                );
                chartControls.appendChild(regressionLabel);
                resultEl.appendChild(chartControls);

                chartLayout.appendChild(fixedAxisContainer);
                chartLayout.appendChild(scrollContainer);
                resultEl.appendChild(chartLayout);

                const regressionSummary = document.createElement('div');
                regressionSummary.className = 'file-regression-summary';
                regressionSummary.hidden = true;
                regressionSummary.setAttribute('aria-live', 'polite');
                resultEl.appendChild(regressionSummary);

                const rangeScrollbar = document.createElement('div');
                rangeScrollbar.className = 'chart-range-scrollbar screenshot-exclude';
                rangeScrollbar.setAttribute('data-html2canvas-ignore', 'true');
                rangeScrollbar.setAttribute('role', 'scrollbar');
                rangeScrollbar.setAttribute('aria-label', 'グラフの表示範囲を左右に移動');
                rangeScrollbar.setAttribute('aria-orientation', 'horizontal');
                rangeScrollbar.setAttribute('aria-valuemin', '0');
                rangeScrollbar.setAttribute('aria-valuemax', '100');
                rangeScrollbar.setAttribute('aria-valuenow', '0');
                rangeScrollbar.tabIndex = 0;
                rangeScrollbar.hidden = true;
                rangeScrollbar.innerHTML = '<div class="chart-range-scrollbar-track"><div class="chart-range-scrollbar-thumb"></div></div>';
                resultEl.appendChild(rangeScrollbar);

                const isTimeAxis = sheet.x_type === 'datetime';
                const hasLogRange = Boolean(
                    sheet.range_start && sheet.range_end
                );

                const logTickMap = new Map(
                    (sheet.axis_ticks || []).map(tick => [
                        new Date(tick.value).getTime(),
                        tick.label
                    ])
                );
                const logTickValues = Array.from(logTickMap.keys());

                const datasets = sheet.series.map((series, seriesIndex) => {
                    const color =
                        chartColors[seriesIndex % chartColors.length];
                    const columnName =
                        sheet.columns?.[series.column_number - 1]
                        ?? `${series.column_number}列目`;

                    return {
                        label: columnName,
                        data: series.points.map(point => ({
                            x: isTimeAxis
                                ? new Date(point.x)
                                : Number(point.x),
                            y: point.y
                        })),
                        borderColor: color,
                        backgroundColor: color,
                        borderWidth: 1,
                        pointRadius: 0,
                        pointHoverRadius: 3,
                        spanGaps: false
                    };
                });

                let dataMin = Number.POSITIVE_INFINITY;
                let rawDataMax = Number.NEGATIVE_INFINITY;

                datasets.forEach(dataset => {
                    dataset.data.forEach(point => {
                        const xValue = isTimeAxis
                            ? point.x.getTime()
                            : Number(point.x);

                        if (!Number.isFinite(xValue)) {
                            return;
                        }

                        dataMin = Math.min(dataMin, xValue);
                        rawDataMax = Math.max(rawDataMax, xValue);
                    });
                });

                if (
                    !Number.isFinite(dataMin) ||
                    !Number.isFinite(rawDataMax)
                ) {
                    const emptyMessage = document.createElement('p');
                    emptyMessage.textContent =
                        '時間軸として利用できるデータがありません．';
                    resultEl.appendChild(emptyMessage);
                    chartLayout.remove();
                    return;
                }

                const dataMax = rawDataMax === dataMin
                    ? dataMin + 1
                    : rawDataMax;

                const yAxisTitle =
                    sheet.preview_scale === 'normalize'
                        ? '正規化値（0～1）'
                        : (
                            sheet.columns?.[
                                sheet.series[0].column_number - 1
                            ]
                            ?? '値'
                        );

                const xScale = {
                    type: isTimeAxis ? 'time' : 'linear',
                    min: dataMin,
                    max: dataMax,
                    bounds: 'data',
                    offset: false,
                    title: {
                        display: true,
                        text:
                            sheet.x_type === 'datetime'
                                ? '時刻'
                                : sheet.x_type === 'sampling'
                                    ? 'sampling_time'
                                    : '行番号'
                    },
                    ticks: {
                        maxTicksLimit: 20
                    }
                };

                if (isTimeAxis) {
                    /*
                     * 横長Canvasでは，Chart.jsが表示可能な目盛数を増やそうとして，
                     * 数十分のデータでも millisecond 単位を選ぶ場合がある．
                     * そのままでは10万件を超える目盛生成となり，
                     * "too far apart with stepSize of 1 millisecond" が発生する．
                     *
                     * データの時間幅に応じて，安全な最小時間単位を指定する．
                     * ログありの場合の実際の表示目盛は，後段の
                     * afterBuildTicksでログ時刻だけへ置き換えるため，
                     * ここでの指定は自動目盛生成の暴走防止にのみ使用する．
                     */
                    const timeRangeMs = Math.max(1, dataMax - dataMin);
                    let minimumTimeUnit = 'day';

                    if (timeRangeMs <= 60 * 1000) {
                        minimumTimeUnit = 'millisecond';
                    } else if (timeRangeMs <= 6 * 60 * 60 * 1000) {
                        minimumTimeUnit = 'second';
                    } else if (timeRangeMs <= 14 * 24 * 60 * 60 * 1000) {
                        minimumTimeUnit = 'minute';
                    } else if (timeRangeMs <= 2 * 365 * 24 * 60 * 60 * 1000) {
                        minimumTimeUnit = 'hour';
                    }

                    xScale.time = {
                        minUnit: minimumTimeUnit,
                        displayFormats: {
                            millisecond: 'HH:mm:ss.SSS',
                            second: 'HH:mm:ss',
                            minute: 'HH:mm',
                            hour: 'HH:mm',
                            day: 'yyyy-MM-dd'
                        },
                        tooltipFormat: 'yyyy-MM-dd HH:mm:ss.SSS'
                    };
                }

                /*
                 * ログありの場合は，Chart.jsが自動生成する目盛を使わず，
                 * 実際のプロット範囲内にあるログ時刻だけをx軸へ表示する．
                 */
                if (
                    hasLogRange &&
                    isTimeAxis &&
                    logTickValues.length > 0
                ) {
                    xScale.afterBuildTicks = axis => {
                        axis.ticks = logTickValues
                            .filter(value => (
                                value >= axis.min && value <= axis.max
                            ))
                            .map(value => ({ value }));
                    };
                    xScale.ticks = {
                        autoSkip: false,
                        maxTicksLimit: Math.max(20, logTickValues.length),
                        maxRotation: 45,
                        minRotation: 0,
                        callback: value =>
                            logTickMap.get(Number(value)) ?? ''
                    };
                }

                const taskRows = isTimeAxis ? (sheet.tasks || []) : [];
                const annotations = Object.fromEntries(
                    taskRows.map((task, index) => [
                        `task${index}`,
                        {
                            type: 'box',
                            xMin: new Date(task.start).getTime(),
                            xMax: new Date(task.end).getTime(),
                            backgroundColor: 'rgba(100, 100, 100, 0.08)',
                            borderWidth: 0,
                            label: {
                                display: true,
                            content: task.name
                            }
                        }
                    ])
                );
                const taskBoundaries = [...new Set(taskRows
                    .flatMap(task => [
                        new Date(task.start).getTime(),
                        new Date(task.end).getTime()
                    ])
                    .filter(value => Number.isFinite(value) && value > dataMin && value < dataMax))]
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

                const fixedYAxisPlugin = {
                    id: `fixedYAxis-${fileIndex}-${sheetIndex}`,
                    afterDraw(chart) {
                        drawFixedYAxis(
                            chart,
                            fixedAxisCanvas,
                            yAxisTitle
                        );
                    }
                };

                let rangeControls = null;
                const chartInstance = new Chart(
                    canvas.getContext('2d'),
                    {
                        type: 'line',
                        data: {
                            datasets
                        },
                        plugins: [
                            fixedYAxisPlugin
                        ],
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: false,
                            parsing: false,
                            normalized: true,
                            layout: {
                                padding: {
                                    left: 0,
                                    right: 0
                                }
                            },
                            interaction: {
                                mode: 'nearest',
                                intersect: false
                            },
                            scales: {
                                x: xScale,
                                y: {
                                    display: true,
                                    title: {
                                        display: false
                                    },
                                    ticks: {
                                        display: false
                                    },
                                    border: {
                                        display: false
                                    },
                                    grid: {
                                        display: true,
                                        drawTicks: false
                                    },
                                    afterFit(axis) {
                                        axis.width = 0;
                                    }
                                }
                            },
                            plugins: {
                                annotation: {
                                    annotations
                                },
                                zoom: {
                                    limits: {
                                        x: {
                                            min: dataMin,
                                            max: dataMax
                                        }
                                    },
                                    zoom: {
                                        wheel: {
                                            enabled: true
                                        },
                                        pinch: {
                                            enabled: true
                                        },
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
                                    filter: item => !item.dataset?.isRegression,
                                    callbacks: {
                                        title(items) {
                                            const point = items[0]?.raw;
                                            if (!point) return '';
                                            const coordinate = isTimeAxis
                                                ? new Date(point.x).toLocaleString('ja-JP')
                                                : `${sheet.x_type === 'sampling' ? 'sampling_time' : '行番号'}: ${point.x}`;
                                            return [
                                                file.filename,
                                                ...(sheet.sheet_name ? [`シート: ${sheet.sheet_name}`] : []),
                                                coordinate
                                            ];
                                        },
                                        label(context) {
                                            const rawValue = context.raw?.y;
                                            const value = Number(rawValue);
                                            const formatted = rawValue != null && Number.isFinite(value)
                                                ? value.toLocaleString('ja-JP', { maximumFractionDigits: 5 })
                                                : '—';
                                            return `${context.dataset.label}: ${formatted}`;
                                        }
                                    }
                                },
                                legend: {
                                    labels: {
                                        filter: (item, chartData) =>
                                            !chartData.datasets[
                                                item.datasetIndex
                                            ]?.isRegression
                                    }
                                }
                            }
                        }
                    }
                );

                const rawDatasetCount = datasets.length;
                const regressionSegments = hasLogRange
                    ? taskRows
                        .map(task => ({
                            name: String(task.name || 'タスク'),
                            start: new Date(task.start).getTime(),
                            end: new Date(task.end).getTime(),
                            origin: new Date(task.start).getTime()
                        }))
                        .filter(segment => (
                            Number.isFinite(segment.start)
                            && Number.isFinite(segment.end)
                            && segment.end > segment.start
                        ))
                    : [{
                        name: '全データ',
                        start: Number.NEGATIVE_INFINITY,
                        end: Number.POSITIVE_INFINITY,
                        origin: isTimeAxis ? dataMin : 0
                    }];

                const regressionXAxisDescription = isTimeAxis
                    ? hasLogRange
                        ? 'x：各タスク開始からの経過時間（分）'
                        : 'x：記録開始からの経過時間（分）'
                    : sheet.x_type === 'sampling'
                        ? 'x：sampling_time'
                        : 'x：行番号';

                const formatRegressionNumber = value => {
                    if (!Number.isFinite(value)) return '—';
                    if (value === 0) return '0';
                    return Number(value.toPrecision(6)).toString();
                };

                const calculateLinearFit = (dataset, segment) => {
                    const points = dataset.data.flatMap(point => {
                        const rawX = isTimeAxis
                            ? point.x instanceof Date
                                ? point.x.getTime()
                                : new Date(point.x).getTime()
                            : Number(point.x);
                        const rawY = point.y;
                        if (
                            !Number.isFinite(rawX)
                            || rawX < segment.start
                            || rawX > segment.end
                            || rawY === null
                            || rawY === undefined
                            || rawY === ''
                        ) {
                            return [];
                        }

                        const y = Number(rawY);
                        if (!Number.isFinite(y)) return [];
                        return [{
                            rawX,
                            x: isTimeAxis
                                ? (rawX - segment.origin) / 60000
                                : rawX,
                            y
                        }];
                    });

                    if (points.length < 2) {
                        return {
                            count: points.length,
                            error: `有効点が${points.length}件です（2件以上必要）`
                        };
                    }

                    const meanX = points.reduce((sum, point) => sum + point.x, 0)
                        / points.length;
                    const meanY = points.reduce((sum, point) => sum + point.y, 0)
                        / points.length;
                    const varianceX = points.reduce(
                        (sum, point) => sum + (point.x - meanX) ** 2,
                        0
                    );

                    if (!(varianceX > 0)) {
                        return {
                            count: points.length,
                            error: 'xの値に変化がありません'
                        };
                    }

                    const covariance = points.reduce(
                        (sum, point) => sum
                            + (point.x - meanX) * (point.y - meanY),
                        0
                    );
                    const slope = covariance / varianceX;
                    const intercept = meanY - slope * meanX;
                    const varianceY = points.reduce(
                        (sum, point) => sum + (point.y - meanY) ** 2,
                        0
                    );
                    const residualSumSquares = points.reduce(
                        (sum, point) => sum
                            + (point.y - (slope * point.x + intercept)) ** 2,
                        0
                    );
                    const rSquared = varianceY > 0
                        ? Math.max(0, Math.min(
                            1,
                            1 - residualSumSquares / varianceY
                        ))
                        : null;
                    const minX = points.reduce(
                        (minimum, point) => Math.min(minimum, point.x),
                        Number.POSITIVE_INFINITY
                    );
                    const maxX = points.reduce(
                        (maximum, point) => Math.max(maximum, point.x),
                        Number.NEGATIVE_INFINITY
                    );
                    const toChartX = value => isTimeAxis
                        ? new Date(segment.origin + value * 60000)
                        : value;

                    return {
                        count: points.length,
                        slope,
                        intercept,
                        rSquared,
                        line: [minX, maxX].map(x => ({
                            x: toChartX(x),
                            y: slope * x + intercept
                        }))
                    };
                };

                const updateRegressionDisplay = () => {
                    chartInstance.data.datasets.splice(rawDatasetCount);
                    regressionSummary.replaceChildren();
                    regressionSummary.hidden = !regressionToggle.checked;

                    if (!regressionToggle.checked) {
                        chartInstance.update('none');
                        return;
                    }

                    const axisDescription = document.createElement('p');
                    axisDescription.className = 'file-regression-axis';
                    axisDescription.textContent = regressionXAxisDescription;
                    regressionSummary.appendChild(axisDescription);

                    const activeDatasetIndices = datasets
                        .map((_, index) => index)
                        .filter(index => chartInstance.isDatasetVisible(index));

                    if (activeDatasetIndices.length === 0) {
                        const note = document.createElement('p');
                        note.className = 'file-regression-note';
                        note.textContent = '回帰式を表示する列を選択してください．';
                        regressionSummary.appendChild(note);
                        chartInstance.update('none');
                        return;
                    }

                    if (hasLogRange && regressionSegments.length === 0) {
                        const note = document.createElement('p');
                        note.className = 'file-regression-note';
                        note.textContent = 'ログにタスク区間がないため，回帰式を算出できません．';
                        regressionSummary.appendChild(note);
                        chartInstance.update('none');
                        return;
                    }

                    regressionSegments.forEach(segment => {
                        const section = document.createElement('section');
                        section.className = 'file-regression-task';
                        const heading = document.createElement('h6');
                        heading.textContent = segment.name;
                        section.appendChild(heading);

                        activeDatasetIndices.forEach(datasetIndex => {
                            const sourceDataset = chartInstance
                                .data.datasets[datasetIndex];
                            const fit = calculateLinearFit(
                                sourceDataset,
                                segment
                            );
                            const equation = document.createElement('p');
                            equation.className = fit.line
                                ? 'file-regression-equation'
                                : 'file-regression-note';
                            equation.style.borderLeftColor =
                                sourceDataset.borderColor;

                            if (!fit.line) {
                                equation.textContent =
                                    `${sourceDataset.label}：算出不可（${fit.error}）`;
                                section.appendChild(equation);
                                return;
                            }

                            const interceptText = fit.intercept < 0
                                ? `− ${formatRegressionNumber(Math.abs(fit.intercept))}`
                                : `+ ${formatRegressionNumber(fit.intercept)}`;
                            const rSquaredText = fit.rSquared === null
                                ? '—'
                                : formatRegressionNumber(fit.rSquared);
                            equation.textContent = [
                                `${sourceDataset.label}：y = ${formatRegressionNumber(fit.slope)}x ${interceptText}`,
                                `R² = ${rSquaredText}`,
                                `n = ${fit.count}`
                            ].join('，');
                            section.appendChild(equation);

                            chartInstance.data.datasets.push({
                                label: hasLogRange
                                    ? `${sourceDataset.label} 回帰線（${segment.name}）`
                                    : `${sourceDataset.label} 回帰線`,
                                data: fit.line,
                                borderColor: sourceDataset.borderColor,
                                backgroundColor: sourceDataset.borderColor,
                                borderWidth: 2,
                                borderDash: [6, 4],
                                pointRadius: 0,
                                pointHoverRadius: 0,
                                pointHitRadius: 0,
                                fill: false,
                                spanGaps: true,
                                isRegression: true
                            });
                        });

                        regressionSummary.appendChild(section);
                    });

                    chartInstance.update('none');
                };

                rangeControls = global.VitBudsChartRangeControls?.attach({
                    chart: chartInstance,
                    domainMin: dataMin,
                    domainMax: dataMax,
                    scrollbar: rangeScrollbar,
                    resetButton: resetZoomButton,
                    formatValue: value => isTimeAxis
                        ? new Date(value).toLocaleString('ja-JP')
                        : `${sheet.x_type === 'sampling' ? 'sampling_time' : '行番号'} ${Number(value).toLocaleString('ja-JP')}`
                });

                // 列表示ON/OFF
                if (columnSelector) {
                    const columnCheckboxes =
                        columnSelector.querySelectorAll(
                            'input[type="checkbox"]'
                        );

                    columnCheckboxes.forEach(
                        checkbox => {

                            checkbox.addEventListener(
                                'change',
                                () => {

                                    const index =
                                        Number(
                                            checkbox.dataset.datasetIndex
                                        );

                                    chartInstance.data.datasets[index]
                                        .hidden =
                                        !checkbox.checked;

                                    updateRegressionDisplay();
                                }
                            );

                        }
                    );
                }

                regressionToggle.addEventListener(
                    'change',
                    updateRegressionDisplay
                );
            });
        });
    }

    global.VitBudsFilePreview = {
        display: displayFilePreview
    };
})(window);
