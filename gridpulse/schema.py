"""Validate telemetry and derive identical features for training and inference."""
import csv
import io
import numpy as np
import pandas as pd

WEATHER = ["ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"]
REQUIRED = ["timestamp", *WEATHER]
TARGET = "target_demand_kw"
LIMITS = {"ambient_temp_c": (-60, 70), "humidity_pct": (0, 100),
          "solar_irradiance_wm2": (0, 2000)}


def read_csv(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("CSV must be UTF-8 text no larger than 2 MB.")
    text = text.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
        if len(set(header)) != len(header):
            raise ValueError("CSV contains duplicate column names.")
        for index, row in enumerate(reader, 2):
            if row and len(row) != len(header):
                raise ValueError(f"CSV line {index} has the wrong number of fields.")
    except StopIteration:
        raise ValueError("CSV is empty.") from None
    try:
        return pd.read_csv(io.StringIO(text), keep_default_na=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError("CSV could not be parsed.") from exc


def validate(frame, medians, *, hourly_window=False):
    if not isinstance(frame, pd.DataFrame) or not 1 <= len(frame) <= 10000:
        raise ValueError("Provide between 1 and 10,000 telemetry rows.")
    if frame.columns.duplicated().any():
        raise ValueError("Duplicate column names are not allowed.")
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    clean = frame[REQUIRED].copy().reset_index(drop=True)
    raw_times = clean["timestamp"].astype(str)
    try:
        dates = pd.to_datetime(raw_times, format="%Y-%m-%d %H:%M:%S", errors="raise")
    except (ValueError, TypeError):
        raise ValueError("Timestamps must use YYYY-MM-DD HH:MM:SS (local grid time).") from None
    if not dates.dt.strftime("%Y-%m-%d %H:%M:%S").eq(raw_times).all():
        raise ValueError("Use exact timestamps: YYYY-MM-DD HH:MM:SS.")
    clean["timestamp"] = raw_times
    warnings = []
    for col in WEATHER:
        source = clean[col]
        blank = source.isna() | source.astype(str).str.strip().eq("")
        numeric = pd.to_numeric(source.mask(blank), errors="coerce")
        if (numeric.isna() & ~blank).any():
            raise ValueError(f"{col} contains nonnumeric text.")
        if np.isinf(numeric.to_numpy(dtype=float)).any():
            raise ValueError(f"{col} contains an infinite value.")
        if blank.any():
            value = float(medians[col])
            if not np.isfinite(value):
                raise ValueError(f"No valid training median for {col}.")
            numeric = numeric.fillna(value)
            warnings.append(f"Filled {int(blank.sum())} missing {col} value(s) with training median {value:.2f}.")
        low, high = LIMITS[col]
        if not numeric.between(low, high).all():
            raise ValueError(f"{col} must be between {low} and {high}.")
        clean[col] = numeric.astype(float)
    if hourly_window:
        if len(clean) != 24:
            raise ValueError("The dashboard needs exactly 24 hourly rows. predict.py accepts any batch size.")
        if (dates.dt.minute.ne(0) | dates.dt.second.ne(0)).any():
            raise ValueError("Forecast hours must start on the hour.")
        if not dates.diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
            raise ValueError("Use 24 unique, consecutive hourly timestamps in ascending order.")
    return clean, warnings


def features(clean):
    dates = pd.to_datetime(clean["timestamp"], format="%Y-%m-%d %H:%M:%S")
    out = clean[WEATHER].copy()
    hour = dates.dt.hour
    out["hour"] = hour.astype(float)
    out["day_of_week"] = dates.dt.dayofweek.astype(float)
    out["month"] = dates.dt.month.astype(float)
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["is_weekend"] = (dates.dt.dayofweek >= 5).astype(float)
    out["cooling_degree_24"] = np.maximum(clean["ambient_temp_c"] - 24, 0)
    out["heating_degree_18"] = np.maximum(18 - clean["ambient_temp_c"], 0)
    return out.astype(float)


def training_data(path):
    frame = read_csv(path.read_text(encoding="utf-8-sig"))
    if TARGET not in frame:
        raise ValueError("Training CSV is missing target_demand_kw.")
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    medians = {c: float(pd.to_numeric(frame[c], errors="raise").median()) for c in WEATHER}
    clean, _ = validate(frame, medians)
    if clean["timestamp"].duplicated().any():
        raise ValueError("Training timestamps must be unique.")
    target = pd.to_numeric(frame[TARGET], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(target).all() or (target < 0).any():
        raise ValueError("Training targets must be finite and nonnegative.")
    return clean, target, medians
