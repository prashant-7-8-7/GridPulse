"""Create a flat, secret-free AppSail ZIP. --vendor adds Linux CPython 3.11 dependencies."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def build(vendor=False):
    destination = ROOT / "dist/GridPulse_AppSail.zip"
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gridpulse-build-") as tmp:
        stage = Path(tmp)
        for name in ["app.py", "predict.py", "train_telemetry.csv", "sample_test_input.csv", "requirements-cloud.txt"]:
            shutil.copy2(ROOT / name, stage / name)
        for name in ["gridpulse", "static", "LICENSES"]:
            shutil.copytree(ROOT / name, stage / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (stage / "models").mkdir()
        for name in ["feature_medians.json", "metrics.json"]:
            if (ROOT / "models" / name).exists():
                shutil.copy2(ROOT / "models" / name, stage / "models" / name)
        if vendor:
            subprocess.run([sys.executable,"-m","pip","install","--target",str(stage),"--only-binary=:all:",
                            "--platform","manylinux_2_28_x86_64","--platform","manylinux_2_27_x86_64",
                            "--platform","manylinux2014_x86_64","--implementation","cp","--python-version","3.11",
                            "--abi","cp311","--no-compile","-r",str(ROOT/"requirements-cloud.txt")],check=True)
        with ZipFile(destination,"w",ZIP_DEFLATED) as archive:
            for file in sorted(stage.rglob("*")):
                if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                    archive.write(file,file.relative_to(stage).as_posix())
    print(f"Created {destination}")
    if not vendor:
        print("SOURCE ONLY: add --vendor before uploading to AppSail. Python dependencies are not included.")
    else:
        print("Linux x86-64 CPython 3.11 bundle. Configure QuickML env vars; startup: python3 -u app.py")
    return destination


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor",action="store_true")
    args=parser.parse_args()
    build(args.vendor)
