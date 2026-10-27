"""Export the same inference features for training inside Zoho QuickML."""
import json
from gridpulse.config import ROOT
from gridpulse.schema import features, training_data, TARGET


def prepare():
    clean, target, medians = training_data(ROOT / "train_telemetry.csv")
    frame = features(clean)
    frame[TARGET] = target
    directory = ROOT / "quickml_data"
    directory.mkdir(exist_ok=True)
    split = int(len(frame)*.8)
    frame.to_csv(directory / "train_features_all.csv", index=False)
    frame.iloc[:split].to_csv(directory / "train_features_fit.csv", index=False)
    frame.iloc[split:].drop(columns=TARGET).to_csv(directory / "validation_features.csv", index=False)
    clean.iloc[split:].to_csv(directory / "validation_telemetry.csv", index=False)
    labels = clean.iloc[split:][["timestamp"]].copy()
    labels[TARGET] = target[split:]
    labels.to_csv(directory / "validation_targets.csv", index=False)
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "models/feature_medians.json").write_text(json.dumps(medians, indent=2), encoding="utf-8")
    print("Created quickml_data/*.csv. Target: target_demand_kw. Inference mode: engineered.")
    print("Validate using fit/validation files; publish a final model trained on train_features_all.csv.")


if __name__ == "__main__":
    prepare()
