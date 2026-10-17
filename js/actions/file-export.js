/* PNG・CSVの保存処理を担当する． */
(function registerFileExport(global) {
    const actions = global.VitBudsFileActions
        || (global.VitBudsFileActions = {});

    actions.saveResultsAsPng = async function saveResultsAsPng(elementId) {
        const element = document.getElementById(elementId);

        if (!element) {
            alert(`エラー: ID "${elementId}" の要素が見つかりません．`);
            return;
        }

        const scrollAreas = Array.from(element.querySelectorAll('.table-scroll'));
        const scrollAreaWidths = scrollAreas.map(area => area.scrollWidth);
        const originalElementStyle = {
            width: element.style.width,
            maxWidth: element.style.maxWidth
        };
        const originalScrollStyles = scrollAreas.map(area => ({
            overflow: area.style.overflow,
            width: area.style.width,
            maxWidth: area.style.maxWidth
        }));

        try {
            scrollAreas.forEach((area, index) => {
                area.style.overflow = 'visible';
                area.style.width = `${scrollAreaWidths[index]}px`;
                area.style.maxWidth = 'none';
            });

            const captureWidth = Math.max(
                element.clientWidth,
                element.scrollWidth,
                ...scrollAreaWidths
            );
            element.style.width = `${captureWidth}px`;
            element.style.maxWidth = 'none';

            const canvas = await html2canvas(element, {
                scale: 2,
                useCORS: true,
                allowTaint: true,
                backgroundColor: '#ffffff',
                width: captureWidth,
                windowWidth: captureWidth,
                ignoreElements: elementToCheck => (
                    elementToCheck.tagName === 'BUTTON'
                    || elementToCheck.classList?.contains('screenshot-exclude')
                    || elementToCheck.hasAttribute?.('data-html2canvas-ignore')
                )
            });

            const a = document.createElement('a');
            a.href = canvas.toDataURL('image/png');
            a.download = `${elementId}_${new Date().toISOString().slice(0, 10)}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        } catch (error) {
            console.error('PNG保存中にエラーが発生しました:', error);
            alert(`PNG保存エラーが発生しました: ${error.message}`);
        } finally {
            element.style.width = originalElementStyle.width;
            element.style.maxWidth = originalElementStyle.maxWidth;
            scrollAreas.forEach((area, index) => {
                const original = originalScrollStyles[index];
                area.style.overflow = original.overflow;
                area.style.width = original.width;
                area.style.maxWidth = original.maxWidth;
            });
        }
    };

    actions.downloadCsvText = function downloadCsvText(filename, csvText) {
        const bom = '\uFEFF';
        const originalText = String(csvText ?? '');
        const csvWithBom = originalText.startsWith(bom) ? originalText : bom + originalText;
        const blob = new Blob([csvWithBom], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };
})(window);
