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

                const rowCount = Number(sheet.row_count) || Math.max(
                    ...sheet.series.map(series => series.points?.length || 0)
                );

                /*
                 * 1データあたり約3 pxとして横長にする．
                 * データ数が少ない場合も表示領域をCanvasで埋め，
                 * Canvas右側へ不要な空白を作らない．
                 */
                const availableChartWidth = Math.max(
                    320,
                    Math.floor(
                        (resultEl.getBoundingClientRect().width || 992) - 92
                    )
                );
                const chartWidth = Math.min(
                    60000,
                    Math.max(availableChartWidth, rowCount * 3)
                );

                /*
                 * ホイール縮小では，時間軸の表示範囲だけでなく，
                 * Canvas自体の横幅も縮小できるようにする．
                 * 最小幅は表示領域の幅，最大幅は従来の詳細表示幅とする．
                 */
                const minimumChartWidth = availableChartWidth;
                const maximumChartWidth = chartWidth;
                let currentChartWidth = chartWidth;

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
                scrollContainer.style.overflowX = 'auto';
                scrollContainer.style.overflowY = 'hidden';

                const chartInner = document.createElement('div');
                chartInner.className = 'file-chart-inner';
                chartInner.style.width = `${chartWidth}px`;
                chartInner.style.minWidth = `${chartWidth}px`;
                chartInner.style.height = '420px';

                const canvas = document.createElement('canvas');
                canvas.width = chartWidth;
                canvas.height = 420;
                canvas.style.display = 'block';

                chartInner.appendChild(canvas);
                scrollContainer.appendChild(chartInner);
                chartLayout.appendChild(fixedAxisContainer);
                chartLayout.appendChild(scrollContainer);
                resultEl.appendChild(chartLayout);

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

                const annotations = Object.fromEntries(
                    (sheet.tasks || []).map((task, index) => [
                        `task${index}`,
                        {
                            type: 'box',
                            xMin: new Date(task.start),
                            xMax: new Date(task.end),
                            backgroundColor: 'rgba(100,100,100,0.08)',
                            borderWidth: 0,
                            label: {
                                display: true,
                                content: task.name
                            }
                        }
                    ])
                );

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
                            responsive: false,
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
                                        mode: 'x'
                                    },
                                    pan: {
                                        enabled: true,
                                        mode: 'x'
                                    }
                                }
                            }
                        }
                    }
                );

                /*
                 * Chart.jsのズームは，x軸がすでにデータ全範囲を表示していると，
                 * それ以上の縮小ができない．しかし，Canvasが横長の場合は，
                 * ブラウザ上では全範囲を1画面で確認できない．
                 *
                 * そこで，x軸が全範囲へ戻った後のホイール縮小では，
                 * Canvasの横幅そのものを縮小する．最小幅まで縮小すると，
                 * StartからEndまでを横スクロールなしで1画面に表示できる．
                 */
                const chartHeight = 420;
                const widthZoomFactor = 1.25;

                function isDisplayingFullXRange() {
                    const xAxis = chartInstance.scales?.x;
                    if (!xAxis) {
                        return false;
                    }

                    const fullRange = Math.max(1, dataMax - dataMin);
                    const tolerance = Math.max(1, fullRange * 1e-8);

                    return (
                        Math.abs(Number(xAxis.min) - dataMin) <= tolerance &&
                        Math.abs(Number(xAxis.max) - dataMax) <= tolerance
                    );
                }

                function resizePreviewChartWidth(nextWidth, clientX) {
                    const viewportWidth = Math.max(
                        minimumChartWidth,
                        scrollContainer.clientWidth || minimumChartWidth
                    );

                    const clampedWidth = Math.max(
                        viewportWidth,
                        Math.min(
                            maximumChartWidth,
                            Math.round(nextWidth)
                        )
                    );

                    if (Math.abs(clampedWidth - currentChartWidth) < 1) {
                        return;
                    }

                    const containerRect =
                        scrollContainer.getBoundingClientRect();
                    const anchorInViewport = Number.isFinite(clientX)
                        ? Math.max(
                            0,
                            Math.min(
                                viewportWidth,
                                clientX - containerRect.left
                            )
                        )
                        : viewportWidth / 2;

                    const oldWidth = currentChartWidth;
                    const oldScrollLeft = scrollContainer.scrollLeft;
                    const anchorInContent =
                        oldScrollLeft + anchorInViewport;
                    const widthRatio = clampedWidth / oldWidth;

                    currentChartWidth = clampedWidth;
                    chartInner.style.width = `${clampedWidth}px`;
                    chartInner.style.minWidth = `${clampedWidth}px`;
                    canvas.style.width = `${clampedWidth}px`;

                    chartInstance.resize(
                        clampedWidth,
                        chartHeight
                    );

                    const nextScrollLeft =
                        anchorInContent * widthRatio - anchorInViewport;
                    const maxScrollLeft = Math.max(
                        0,
                        clampedWidth - viewportWidth
                    );

                    scrollContainer.scrollLeft = Math.max(
                        0,
                        Math.min(maxScrollLeft, nextScrollLeft)
                    );
                }

                canvas.addEventListener(
                    'wheel',
                    event => {
                        /*
                         * deltaY > 0：縮小
                         * x軸が全範囲なら，Canvas幅を縮める．
                         */
                        if (
                            event.deltaY > 0 &&
                            isDisplayingFullXRange() &&
                            currentChartWidth > minimumChartWidth + 1
                        ) {
                            event.preventDefault();
                            event.stopImmediatePropagation();

                            resizePreviewChartWidth(
                                currentChartWidth / widthZoomFactor,
                                event.clientX
                            );
                            return;
                        }

                        /*
                         * deltaY < 0：拡大
                         * Canvas幅が縮小済みなら，先に詳細表示幅へ戻す．
                         * 元の幅へ戻った後は，Chart.jsの通常ズームへ渡す．
                         */
                        if (
                            event.deltaY < 0 &&
                            isDisplayingFullXRange() &&
                            currentChartWidth < maximumChartWidth - 1
                        ) {
                            event.preventDefault();
                            event.stopImmediatePropagation();

                            resizePreviewChartWidth(
                                currentChartWidth * widthZoomFactor,
                                event.clientX
                            );
                        }
                    },
                    {
                        capture: true,
                        passive: false
                    }
                );

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

                                    chartInstance.update();
                                }
                            );

                        }
                    );
                }
            });
        });
    }

    global.VitBudsFilePreview = {
        display: displayFilePreview
    };
})(window);
