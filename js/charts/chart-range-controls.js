/* 時系列グラフの表示範囲リセットと横スクロール操作を共通化する． */
(function registerChartRangeControls(global) {
    function attach({ chart, domainMin, domainMax, scrollbar, resetButton, formatValue }) {
        const min = Number(domainMin);
        const max = Number(domainMax);
        const hasDomain = Number.isFinite(min)
            && Number.isFinite(max)
            && max > min;
        const track = scrollbar?.querySelector('.chart-range-scrollbar-track');
        const thumb = scrollbar?.querySelector('.chart-range-scrollbar-thumb');
        const clamp = (value, lower, upper) => Math.min(upper, Math.max(lower, value));
        const describeValue = formatValue
            || (value => new Date(value).toLocaleString('ja-JP'));

        function readVisibleRange() {
            return {
                min: Number(chart.scales?.x?.min),
                max: Number(chart.scales?.x?.max)
            };
        }

        function sync() {
            if (!scrollbar || !track || !thumb || !hasDomain) {
                if (scrollbar) scrollbar.hidden = true;
                return;
            }
            const visibleRange = readVisibleRange();
            const total = max - min;
            if (!Number.isFinite(visibleRange.min)
                || !Number.isFinite(visibleRange.max)
                || total <= 0) {
                scrollbar.hidden = true;
                return;
            }

            const visible = clamp(visibleRange.max - visibleRange.min, 0, total);
            const ratio = visible / total;
            const thumbWidth = clamp(ratio * 100, 6, 100);
            const availableRange = Math.max(0, total - visible);
            const position = availableRange > 0
                ? clamp((visibleRange.min - min) / availableRange, 0, 1)
                : 0;
            thumb.style.width = `${thumbWidth}%`;
            thumb.style.left = `${position * (100 - thumbWidth)}%`;
            scrollbar.hidden = ratio >= 0.9999;
            scrollbar.setAttribute('aria-valuenow', String(Math.round(position * 100)));
            scrollbar.setAttribute('aria-valuetext',
                `${describeValue(visibleRange.min)} から ${describeValue(visibleRange.max)}`);
        }

        function setVisibleStart(requestedMin) {
            if (!hasDomain) return;
            const visibleRange = readVisibleRange();
            const total = max - min;
            const visible = clamp(visibleRange.max - visibleRange.min, 0, total);
            if (!Number.isFinite(visible) || visible >= total) return;
            const nextMin = clamp(requestedMin, min, max - visible);
            chart.options.scales.x.min = nextMin;
            chart.options.scales.x.max = nextMin + visible;
            chart.update('none');
            sync();
        }

        function reset() {
            chart.resetZoom?.();
            if (hasDomain) {
                chart.options.scales.x.min = min;
                chart.options.scales.x.max = max;
            } else {
                delete chart.options.scales.x.min;
                delete chart.options.scales.x.max;
            }
            chart.update('none');
            sync();
        }

        let dragState = null;
        thumb?.addEventListener('pointerdown', event => {
            event.preventDefault();
            const visibleRange = readVisibleRange();
            dragState = {
                pointerId: event.pointerId,
                startX: event.clientX,
                startMin: visibleRange.min
            };
            thumb.setPointerCapture(event.pointerId);
        });
        thumb?.addEventListener('pointermove', event => {
            if (!dragState || dragState.pointerId !== event.pointerId || !track) return;
            const visibleRange = readVisibleRange();
            const total = max - min;
            const visible = clamp(visibleRange.max - visibleRange.min, 0, total);
            const travel = Math.max(0, total - visible);
            const trackWidth = track.getBoundingClientRect().width;
            const thumbWidth = thumb.getBoundingClientRect().width;
            const travelPixels = Math.max(1, trackWidth - thumbWidth);
            setVisibleStart(dragState.startMin
                + (event.clientX - dragState.startX) / travelPixels * travel);
        });
        const endDrag = event => {
            if (dragState?.pointerId === event.pointerId) dragState = null;
        };
        thumb?.addEventListener('pointerup', endDrag);
        thumb?.addEventListener('pointercancel', endDrag);
        track?.addEventListener('pointerdown', event => {
            if (event.target === thumb || thumb?.contains(event.target)) return;
            const rect = track.getBoundingClientRect();
            const thumbWidth = thumb?.getBoundingClientRect().width || 0;
            const travelPixels = Math.max(1, rect.width - thumbWidth);
            const fraction = clamp((event.clientX - rect.left - thumbWidth / 2) / travelPixels, 0, 1);
            const visibleRange = readVisibleRange();
            const visible = clamp(visibleRange.max - visibleRange.min, 0, max - min);
            setVisibleStart(min + fraction * (max - min - visible));
        });
        scrollbar?.addEventListener('keydown', event => {
            const visibleRange = readVisibleRange();
            const visible = Math.max(0, visibleRange.max - visibleRange.min);
            let nextMin;
            if (event.key === 'ArrowLeft') nextMin = visibleRange.min - visible * 0.1;
            else if (event.key === 'ArrowRight') nextMin = visibleRange.min + visible * 0.1;
            else if (event.key === 'PageUp') nextMin = visibleRange.min - visible * 0.8;
            else if (event.key === 'PageDown') nextMin = visibleRange.min + visible * 0.8;
            else if (event.key === 'Home') nextMin = min;
            else if (event.key === 'End') nextMin = max - visible;
            else return;
            event.preventDefault();
            setVisibleStart(nextMin);
        });
        resetButton?.addEventListener('click', reset);
        sync();

        return { sync, reset };
    }

    global.VitBudsChartRangeControls = { attach };
})(window);
