"""Measure predictions against timestamp-matched labelled data, without using labels as inputs."""
import argparse
import json
from pathlib import Path
import numpy as np
from gridpulse.config import backend
from gridpulse.schema import read_csv, TARGET
from predict import predict


def evaluate(input_path, target_path, output_path):
    frame=read_csv(input_path.read_text(encoding="utf-8-sig"))
    labels=read_csv(target_path.read_text(encoding="utf-8-sig"))
    if labels.columns.tolist() != ["timestamp",TARGET] or len(labels)!=len(frame) or labels.timestamp.tolist()!=frame.timestamp.tolist():
        raise ValueError("Targets must have timestamp,target_demand_kw and match every input timestamp in order.")
    truth=labels[TARGET].to_numpy(dtype=float)
    if not np.isfinite(truth).all() or (truth<0).any():
        raise ValueError("Evaluation targets must be finite and nonnegative.")
    prediction=predict(frame)
    report={"backend":backend(),"rows":len(frame),"rmse_kw":float(np.sqrt(np.mean((prediction-truth)**2))),
            "mae_kw":float(np.mean(np.abs(prediction-truth))),
            "note":"This is held-out accuracy only if the endpoint was NOT trained on these target rows."}
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--targets",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    evaluate(args.input,args.targets,args.output)
