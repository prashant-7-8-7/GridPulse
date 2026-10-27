"""Compare small regressors on a chronological holdout, then refit all training rows."""
import json
import os
import time
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.base import clone
from gridpulse.config import ROOT
from gridpulse.schema import WEATHER, features, training_data, validate, read_csv


def train():
    started = time.perf_counter()
    clean, target, full_medians = training_data(ROOT / "train_telemetry.csv")
    split = int(len(clean) * .8)
    # Fit missing-value statistics on the fitting partition for validation.
    raw = read_csv((ROOT / "train_telemetry.csv").read_text(encoding="utf-8-sig"))
    raw = raw.sort_values("timestamp", kind="stable").reset_index(drop=True)
    medians = {c: float(pd.to_numeric(raw.iloc[:split][c], errors="raise").median()) for c in WEATHER}
    fitting, _ = validate(raw.iloc[:split], medians)
    validation, _ = validate(raw.iloc[split:], medians)
    x_train, x_val = features(fitting), features(validation)
    candidates = {
        "Ridge": make_pipeline(StandardScaler(), Ridge(alpha=10)),
        "Gradient boosting": GradientBoostingRegressor(n_estimators=250, max_depth=2,
                              learning_rate=.05, loss="squared_error", random_state=42),
        "Histogram gradient boosting": HistGradientBoostingRegressor(max_iter=220,
                              max_leaf_nodes=15, l2_regularization=2, random_state=42),
    }
    hours = pd.to_datetime(fitting.timestamp).dt.hour
    means = pd.Series(target[:split]).groupby(hours).mean()
    naive = pd.to_datetime(validation.timestamp).dt.hour.map(means).fillna(target[:split].mean())
    baseline = float(np.sqrt(mean_squared_error(target[split:], naive)))
    scores = []
    for name, model in candidates.items():
        model.fit(x_train, target[:split])
        prediction = np.maximum(0, model.predict(x_val))
        scores.append({"model": name, "rmse_kw": float(np.sqrt(mean_squared_error(target[split:], prediction))),
                       "mae_kw": float(mean_absolute_error(target[split:], prediction)),
                       "r2": float(r2_score(target[split:], prediction))})
    best = min(scores, key=lambda score: score["rmse_kw"])
    final = clone(candidates[best["model"]]).fit(features(clean), target)
    report = {"backend": "local", "selected_model": best["model"], "rows": len(clean),
              "fitting_rows": split, "validation_rows": len(clean)-split,
              "validation_start": validation.timestamp.iloc[0], "validation_end": validation.timestamp.iloc[-1],
              "split_method": "Chronological first 80% fit / last 20% validation; best model refit on all 4000 supplied training rows.",
              "rmse_kw": best["rmse_kw"], "mae_kw": best["mae_kw"], "r2": best["r2"],
              "hour_mean_baseline_rmse_kw": baseline, "candidates": scores,
              "feature_columns": list(features(clean).columns),
              "training_seconds": round(time.perf_counter()-started, 3),
              "note": "Local validation only. Sample test inputs have no targets; hidden-test and QuickML accuracy are unmeasured."}
    (ROOT / "models").mkdir(exist_ok=True)
    joblib.dump({"model": final, "medians": full_medians, "report": report}, ROOT / "models/local_model.joblib")
    (ROOT / "models/metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "models/feature_medians.json").write_text(json.dumps(full_medians, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    train()
