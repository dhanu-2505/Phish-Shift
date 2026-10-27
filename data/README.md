# Phishing email dataset

The training file `Phishing_Email.csv` is the `Phishing Email Detection`
dataset mirrored by Hugging Face at:

- Dataset page: https://huggingface.co/datasets/zefang-liu/phishing-email-dataset
- Download: https://huggingface.co/datasets/zefang-liu/phishing-email-dataset/resolve/main/Phishing_Email.csv
- Original Kaggle source: https://www.kaggle.com/datasets/subhajournal/phishingemails
- Dataset card declares LGPL-3.0: https://huggingface.co/datasets/zefang-liu/phishing-email-dataset/raw/main/README.md

The mirror's dataset card identifies itself as a direct copy of the Kaggle
dataset and attributes it to the Kaggle user Cyber Cop. The declared license
and upstream attribution should be reviewed before redistribution.

The downloaded CSV is pinned by SHA-256 in
`backend/scripts/train_model.py`. Training checks this hash and refuses to use
a different file. The file contains email text and may include personal or
sensitive content; it is kept locally and message contents must not be printed
in logs or committed publicly.

Training drops rows missing either text or label, removes normalized duplicate
messages, and removes all messages whose duplicate copies have conflicting
labels before splitting. A fixed-seed stratified 80/20 split is then used.
The held-out set is used only for final metrics. See `reports/model_evaluation.json`
for the measured evaluation from the generated model artifact.

The CSV also contains an unnamed source-index column; training ignores it and
reads only `Email Text` and `Email Type`. The training report records source
row count, missing and blank values, normalized duplicate rows, excluded
conflicting-label groups, retained class counts, train/test counts, checksum,
and training timestamp. The complete dataset is not imported into MariaDB;
only aggregate provenance is stored in `dataset_metadata`, `model_versions`,
and `model_evaluations`. Training messages are never written to `scan_results`.

Exact normalized duplicates and conflicting-label copies are removed before
the stratified split, so exact copies cannot cross the split. Near-duplicate
clustering is not performed; treat these as held-out results on the cleaned
corpus, not an estimate of real-world generalization.

## Optional retraining

To reproduce training from the verified local CSV, run from the backend
directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.train_model
```

This uses seed 42 and does not use saved website scans. Website predictions
have no verified ground-truth labels and must not be used as training examples.
Future retraining on additional data requires an appropriately licensed
dataset with independently verified labels, a pinned source and checksum, a
separate held-out test set, and evaluation before replacing the current model.
