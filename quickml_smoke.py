"""Make one real QuickML call, with no local fallback. Run after configuring .env."""
import sys
import pandas as pd
from gridpulse.config import ROOT, backend
from predict import predict

if __name__ == "__main__":
    if backend() != "quickml":
        raise SystemExit("Set FORECAST_BACKEND=quickml in .env first. This check must use the cloud.")
    try:
        row = pd.read_csv(ROOT/"sample_test_input.csv").iloc[:1]
        result = predict(row)
        print(f"QuickML verified: {row.timestamp.iloc[0]} -> {float(result[0]):.6f} kW")
        print("This confirms one live inference request; it does not measure model accuracy.")
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"QuickML check failed: {exc}",file=sys.stderr)
        raise SystemExit(1)
