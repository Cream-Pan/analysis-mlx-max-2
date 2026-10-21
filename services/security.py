"""Small, dependency-free security policies shared by the app and tests."""

STATIC_ASSETS = frozenset({
    "app.js",
    "config.json",
    "style.css",
    "js/actions/file-export.js",
    "js/charts/file-preview.js",
    "js/results/evaluations.js",
    "js/results/ppg-acc-actions.js",
    "js/results/ppg-acc-analysis.js",
    "js/results/ppg-acc-formatters.js",
    "js/results/ppg-acc-table-rows.js",
    "js/results/ppg-comparison.js",
    "js/results/ppg-hr-analysis.js",
    "js/results/ppg-to-hr.js",
    "vendor/chartjs/chart.umd.min.js",
    "vendor/chartjs-adapter-date-fns/chartjs-adapter-date-fns.bundle.min.js",
    "vendor/chartjs-plugin-annotation/chartjs-plugin-annotation.min.js",
    "vendor/chartjs-plugin-zoom/chartjs-plugin-zoom.min.js",
    "vendor/html2canvas/html2canvas.min.js",
})


def parse_cors_origins(value):
    """Parse an explicit comma-separated CORS origin allowlist."""
    origins = tuple(dict.fromkeys(
        origin.strip()
        for origin in (value or "").split(",")
        if origin.strip()
    ))
    if "*" in origins:
        raise ValueError(
            "VITBUDS_CORS_ORIGINS must list explicit origins; '*' is not allowed"
        )
    return origins


def is_allowed_upload_origin(origin, same_origin, allowed_origins):
    """Allow non-browser requests, same-origin requests, and explicit origins."""
    if not origin:
        return True
    return origin == same_origin or origin in allowed_origins
