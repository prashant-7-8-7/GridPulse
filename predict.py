"""HackSphere evaluation contract + real --input/--output CSV interface."""
import argparse
from pathlib import Path
import sys
import pandas as pd
from gridpulse.forecasting import forecast
from gridpulse.schema import read_csv


def predict(input_df: pd.DataFrame):
    """Return one numeric prediction per row, without sorting or changing row order."""
    return forecast(input_df)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        frame = read_csv(args.input.read_text(encoding="utf-8-sig"))
        values = predict(frame)
        result = pd.DataFrame({"timestamp": frame["timestamp"].to_numpy(), "target_demand_kw": values})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(args.output, index=False, float_format="%.6f")
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Prediction failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {len(result)} predictions to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
