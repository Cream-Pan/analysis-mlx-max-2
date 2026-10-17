/* PPG＋ACC結果に使う数値・PSDの表示整形を担当する． */
(function registerPpgAccFormatters(global) {
    const formatters = global.VitBudsResultFormatters
        || (global.VitBudsResultFormatters = {});

    function formatValue(value, digits = 1, suffix = '') {
        if (value === null || value === undefined || value === '') {
            return '―';
        }

        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return '―';
        }

        return `${numericValue.toFixed(digits)}${suffix}`;
    }

    function formatErrorMetric(value, metricFormatter) {
        if (value === null || value === undefined || value === '') {
            return '―';
        }

        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return '―';
        }

        return metricFormatter(numericValue);
    }

    function formatPsdPeak(frequency, psdValue) {
        const frequencyText = formatValue(frequency, 3, ' Hz');
        if (psdValue === null || psdValue === undefined || psdValue === '') {
            return `${frequencyText}<br><small>PSD：―</small>`;
        }

        const numericPsd = Number(psdValue);
        const psdText = Number.isFinite(numericPsd)
            ? numericPsd.toExponential(3)
            : '―';

        return `${frequencyText}<br><small>PSD：${psdText}</small>`;
    }

    formatters.ppgAcc = {
        formatValue,
        formatErrorMetric,
        formatPsdPeak
    };
})(window);
