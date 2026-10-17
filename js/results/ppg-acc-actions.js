/* PPG＋ACC結果のPNG・CSVボタンを接続する． */
(function registerPpgAccResultActions(global) {
    const actions = global.VitBudsResultActions
        || (global.VitBudsResultActions = {});

    actions.bindPpgAcc = function bindPpgAcc(
        resultElement,
        result,
        uniqueId,
        saveResultsAsPng,
        downloadCsvText
    ) {
        const screenshotButton = resultElement.querySelector(
            '.save-ppg-acc-png-btn'
        );
        screenshotButton?.addEventListener(
            'click',
            () => saveResultsAsPng(uniqueId)
        );

        const summaryButton = resultElement.querySelector(
            '.download-ppg-acc-summary-btn'
        );
        if (summaryButton && result.summary_download) {
            summaryButton.addEventListener('click', () => {
                downloadCsvText(
                    result.summary_download.filename,
                    result.summary_download.csv_text
                );
            });
        }

        const detailButton = resultElement.querySelector(
            '.download-ppg-acc-detail-btn'
        );
        if (detailButton && result.detail_download) {
            detailButton.addEventListener('click', () => {
                downloadCsvText(
                    result.detail_download.filename,
                    result.detail_download.csv_text
                );
            });
        }
    };
})(window);
