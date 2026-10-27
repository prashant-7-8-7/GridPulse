"""Exact competition dispatch signals, independent of the battery simulation."""
from datetime import datetime
import math


def transition(timestamp, demand_kw):
    if not math.isfinite(demand_kw) or demand_kw < 0:
        raise ValueError("Demand must be finite and nonnegative.")
    hour = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").hour
    peak = 18 <= hour <= 22
    high = demand_kw > 160
    return {
        "grid_mode": "renewable_storage" if high or peak else "main_grid",
        "grid_label": "Renewable Storage Mode" if high or peak else "Main Grid Mode",
        "critical_overload": demand_kw >= 200,
        "reason": "High demand + evening window" if high and peak else
                  "Demand > 160 kW" if high else "Evening window (18:00-22:00)" if peak else
                  "Demand <= 160 kW; outside evening window",
    }
