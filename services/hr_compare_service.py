import pandas as pd
import numpy as np

from sklearn.metrics import mean_squared_error, mean_absolute_error

def evaluate_hr_pair(df_true, df_dev, start_t, end_t):
    try:
        t_sub = df_true.loc[start_t:end_t]
        d_sub = df_dev.loc[start_t:end_t]

        if t_sub.empty or d_sub.empty:
            return {
                "raw_mae": None,
                "raw_rmse": None,
                "raw_count": 0,
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": "データ不足"
            }

        combined_idx = t_sub.index.union(d_sub.index)

        interp_true = (
            t_sub[['HR']]
            .reindex(combined_idx)
            .interpolate(method='time')
            .reindex(d_sub.index)
        )

        comp = pd.DataFrame({
            'true': interp_true['HR'],
            'dev': d_sub['HR']
        }).dropna()

        if comp.empty:
            return {
                "raw_mae": None,
                "raw_rmse": None,
                "raw_count": 0,
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": "同期データなし"
            }

        raw_mae = float(mean_absolute_error(comp['true'], comp['dev']))
        raw_rmse = float(np.sqrt(mean_squared_error(comp['true'], comp['dev'])))

        resampled = comp.resample('1min', origin=start_t).mean().dropna()
        if resampled.empty:
            return {
                "raw_mae": raw_mae,
                "raw_rmse": raw_rmse,
                "raw_count": len(comp),
                "resampled_mae": None,
                "resampled_rmse": None,
                "resampled_count": 0,
                "error": None
            }

        resampled_mae = float(mean_absolute_error(resampled['true'], resampled['dev']))
        resampled_rmse = float(np.sqrt(mean_squared_error(resampled['true'], resampled['dev'])))

        return {
            "raw_mae": raw_mae,
            "raw_rmse": raw_rmse,
            "raw_count": len(comp),
            "resampled_mae": resampled_mae,
            "resampled_rmse": resampled_rmse,
            "resampled_count": len(resampled),
            "error": None
        }

    except Exception as e:
        return {
            "raw_mae": None,
            "raw_rmse": None,
            "raw_count": 0,
            "resampled_mae": None,
            "resampled_rmse": None,
            "resampled_count": 0,
            "error": str(e)
        }