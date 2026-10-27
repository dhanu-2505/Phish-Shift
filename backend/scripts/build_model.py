import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from scripts.train_model import (
    DATASET_SHA256,
    DATASET_URL,
    ARTIFACT_PATH,
    sha256_file,
    train_and_evaluate,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
BUILD_REPORT_PATH = BACKEND_DIR / "reports" / "model_evaluation.json"


def download_verified_dataset(destination: Path) -> None:
    request = urllib.request.Request(
        DATASET_URL,
        headers={"User-Agent": "PhishShift-model-build/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with destination.open("wb") as target:
                shutil.copyfileobj(response, target)
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError("Could not download the documented training dataset.") from exc

    if sha256_file(destination) != DATASET_SHA256:
        destination.unlink(missing_ok=True)
        raise RuntimeError(
            "Downloaded dataset SHA-256 did not match the pinned source; "
            "refusing to build an unverified model."
        )


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="phishshift-model-") as directory:
            dataset_path = Path(directory) / "Phishing_Email.csv"
            download_verified_dataset(dataset_path)
            metadata, metrics = train_and_evaluate(
                dataset_path=dataset_path,
                report_path=BUILD_REPORT_PATH,
            )
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Model build failed: {exc}", file=sys.stderr)
        return 1

    print("Verified dataset and trained model artifact for deployment.")
    print(f"Dataset SHA-256: {metadata['dataset_sha256']}")
    print(f"Training rows: {metadata['training_rows']}")
    print(f"Test rows: {metadata['test_rows']}")
    print(f"F1-score: {metrics['f1_score']:.6f}")
    print(f"Model artifact: {ARTIFACT_PATH}")
    print(f"Evaluation report: {BUILD_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
