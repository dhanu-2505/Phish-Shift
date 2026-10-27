import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mysql.connector
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_ROOT / "data" / "Phishing_Email.csv"
ARTIFACT_PATH = PROJECT_ROOT / "backend" / "models" / "phishshift_text_model.joblib"
REPORT_PATH = PROJECT_ROOT / "reports" / "model_evaluation.json"
DATASET_URL = (
    "https://huggingface.co/datasets/zefang-liu/phishing-email-dataset/"
    "resolve/main/Phishing_Email.csv"
)
DATASET_SHA256 = "18ef4fff1acb8986f0ab01e83ede6025420c829656af5a377560fce17e153b97"
MODEL_NAME = "PhishShift TF-IDF Logistic Regression"
RANDOM_STATE = 42
TEST_SIZE = 0.2
LABELS = ("Safe Email", "Phishing Email")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset() -> tuple[list[str], list[str], dict[str, int], dict[str, int]]:
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(
            f"Dataset not found at {DATASET_PATH}. See data/README.md for the source."
        )
    actual_hash = sha256_file(DATASET_PATH)
    if actual_hash != DATASET_SHA256:
        raise ValueError(
            "Dataset SHA-256 does not match the documented source revision; "
            "refusing to train on unverified data."
        )

    frame = pd.read_csv(DATASET_PATH, usecols=["Email Text", "Email Type"])
    source_row_count = len(frame)
    missing_text_rows = int(frame["Email Text"].isna().sum())
    missing_label_rows = int(frame["Email Type"].isna().sum())
    source_label_counts = frame["Email Type"].value_counts().to_dict()
    valid = frame.dropna(subset=["Email Text", "Email Type"]).copy()
    valid["Email Text"] = valid["Email Text"].astype(str).str.strip()
    blank_text_rows = int(valid["Email Text"].eq("").sum())
    valid = valid.loc[valid["Email Text"].ne("")]
    observed_labels = set(valid["Email Type"].astype(str).unique())
    if observed_labels != set(LABELS):
        raise ValueError("Dataset labels differ from the documented two-class schema.")

    valid["_canonical_text"] = valid["Email Text"].map(
        lambda value: re.sub(r"\s+", " ", value).casefold()
    )
    label_counts_per_text = valid.groupby("_canonical_text")["Email Type"].nunique()
    conflicting_texts = set(label_counts_per_text[label_counts_per_text > 1].index)
    non_conflicting = valid.loc[~valid["_canonical_text"].isin(conflicting_texts)]
    duplicate_rows_collapsed = len(non_conflicting) - int(
        non_conflicting["_canonical_text"].nunique()
    )
    conflicting_rows_excluded = int(valid["_canonical_text"].isin(conflicting_texts).sum())
    valid = non_conflicting
    valid = valid.drop_duplicates(subset="_canonical_text", keep="first")

    texts = valid["Email Text"].tolist()
    labels = valid["Email Type"].astype(str).tolist()
    class_counts = {
        label: int(count)
        for label, count in valid["Email Type"].value_counts().items()
    }
    if min(class_counts.get(label, 0) for label in LABELS) < 2:
        raise ValueError("Each class needs at least two unique messages for a split.")
    dataset_counts = {
        "source_rows": source_row_count,
        "source_safe_rows": int(source_label_counts.get("Safe Email", 0)),
        "source_phishing_rows": int(source_label_counts.get("Phishing Email", 0)),
        "missing_text_rows": missing_text_rows,
        "missing_label_rows": missing_label_rows,
        "blank_text_rows": blank_text_rows,
        "conflicting_duplicate_groups": len(conflicting_texts),
        "conflicting_rows_excluded": conflicting_rows_excluded,
        "duplicate_rows_collapsed": duplicate_rows_collapsed,
        "usable_unique_rows": len(texts),
    }
    return texts, labels, class_counts, dataset_counts


def train_and_evaluate() -> tuple[dict, dict]:
    texts, labels, class_counts, dataset_counts = load_dataset()
    x_train, x_test, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=labels,
    )

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    strip_accents="unicode",
                    ngram_range=(1, 2),
                    min_df=2,
                    max_features=100_000,
                    sublinear_tf=True,
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    random_state=RANDOM_STATE,
                    solver="liblinear",
                ),
            ),
        ]
    )
    pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_test)
    matrix = confusion_matrix(y_test, predictions, labels=list(LABELS))
    true_negative, false_positive, false_negative, true_positive = (
        int(value) for value in matrix.ravel()
    )
    false_positive_rate = (
        false_positive / (false_positive + true_negative)
        if false_positive + true_negative
        else 0.0
    )
    metrics = {
        "precision": float(
            precision_score(y_test, predictions, pos_label="Phishing Email")
        ),
        "recall": float(recall_score(y_test, predictions, pos_label="Phishing Email")),
        "f1_score": float(
            f1_score(y_test, predictions, pos_label="Phishing Email")
        ),
        "false_positive_rate": float(false_positive_rate),
        "confusion_matrix_labels": list(LABELS),
        "confusion_matrix": matrix.tolist(),
        "false_positive_analysis": {
            "false_positives": false_positive,
            "true_negatives": true_negative,
            "false_positive_rate": float(false_positive_rate),
            "definition": "FP / (FP + TN), with Phishing Email as the positive class.",
        },
    }
    dataset_hash = sha256_file(DATASET_PATH)
    model_version = f"1.0.0-{dataset_hash[:12]}"
    metadata = {
        "model_name": MODEL_NAME,
        "model_version": model_version,
        "dataset_name": "Phishing Email Detection",
        "dataset_version": dataset_hash,
        "dataset_source": DATASET_URL,
        "dataset_license": "LGPL-3.0 (as declared by the Hugging Face dataset mirror)",
        "dataset_sha256": dataset_hash,
        "dataset_rows_after_deduplication": len(texts),
        "class_counts_after_deduplication": class_counts,
        "dataset_counts": dataset_counts,
        "training_rows": len(x_train),
        "test_rows": len(x_test),
        "test_size_fraction": TEST_SIZE,
        "random_state": RANDOM_STATE,
        "preprocessing": (
            "Drop incomplete rows; remove normalized duplicate texts and all "
            "messages with conflicting labels before a stratified split. "
            "Near-duplicate clustering is not applied; normalized exact "
            "duplicates cannot cross the split."
        ),
        "pipeline": (
            "TfidfVectorizer(word 1-2 grams, min_df=2, max_features=100000, "
            "sublinear_tf=True) + LogisticRegression(liblinear, max_iter=1000)."
        ),
        "positive_class": "Phishing Email",
        "sklearn_version": sklearn.__version__,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    bundle = {"pipeline": pipeline, "metadata": metadata}

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, ARTIFACT_PATH)
    report = {"metadata": metadata, "evaluation": metrics}
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata, metrics


def main() -> int:
    try:
        metadata, metrics = train_and_evaluate()
    except (FileNotFoundError, ValueError, KeyError, OSError) as exc:
        print(f"Training failed: {exc}", file=sys.stderr)
        return 1
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from app import database

    try:
        database.record_training_run(metadata, metrics)
    except (database.DatabaseConfigurationError, mysql.connector.Error) as exc:
        print(
            "Model artifacts were saved, but database metadata sync failed "
            f"({type(exc).__name__}).",
            file=sys.stderr,
        )
    else:
        print("Dataset, model-version, and evaluation metadata synced to MariaDB.")
    print(f"Model artifact: {ARTIFACT_PATH}")
    print(f"Evaluation report: {REPORT_PATH}")
    print(f"Dataset SHA-256: {metadata['dataset_sha256']}")
    print(f"Rows after deduplication: {metadata['dataset_rows_after_deduplication']}")
    print(f"Training rows: {metadata['training_rows']}")
    print(f"Test rows: {metadata['test_rows']}")
    print(f"Precision: {metrics['precision']:.6f}")
    print(f"Recall: {metrics['recall']:.6f}")
    print(f"F1-score: {metrics['f1_score']:.6f}")
    print(f"False-positive rate: {metrics['false_positive_rate']:.6f}")
    print(f"Confusion matrix [Safe, Phishing]: {metrics['confusion_matrix']}")
    print(f"False positives: {metrics['false_positive_analysis']['false_positives']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
