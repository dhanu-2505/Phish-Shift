import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib


BACKEND_DIR = Path(__file__).resolve().parents[1]
MODEL_ARTIFACT = BACKEND_DIR / "models" / "phishshift_text_model.joblib"
PHISHING_LABEL = "Phishing Email"


class ModelUnavailableError(RuntimeError):
    """Raised when the trained local classifier cannot be loaded."""


def canonicalize_message(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


@lru_cache(maxsize=1)
def load_model_bundle() -> dict[str, Any]:
    if not MODEL_ARTIFACT.is_file():
        raise ModelUnavailableError(
            "Trained model artifact is missing. Run backend/scripts/train_model.py."
        )
    try:
        bundle = joblib.load(MODEL_ARTIFACT)
    except (OSError, ValueError, EOFError, ImportError) as exc:
        raise ModelUnavailableError("Trained model artifact could not be loaded.") from exc
    if (
        not isinstance(bundle, dict)
        or "pipeline" not in bundle
        or not isinstance(bundle.get("metadata"), dict)
    ):
        raise ModelUnavailableError("Trained model artifact has an invalid format.")
    return bundle


def predict_message(text: str) -> dict[str, Any]:
    bundle = load_model_bundle()
    pipeline = bundle["pipeline"]
    classifier = pipeline.named_steps.get("classifier")
    vectorizer = pipeline.named_steps.get("tfidf")
    if classifier is None or vectorizer is None or not hasattr(classifier, "coef_"):
        raise ModelUnavailableError("Trained model artifact does not support explanations.")

    probabilities = pipeline.predict_proba([text])[0]
    classes = list(classifier.classes_)
    try:
        phishing_index = classes.index(PHISHING_LABEL)
    except ValueError as exc:
        raise ModelUnavailableError("Trained model has no phishing class.") from exc

    risk_score = float(probabilities[phishing_index])
    predicted_label = str(classes[int(probabilities.argmax())])
    feature_values = pipeline.named_steps["tfidf"].transform([text]).tocsr()
    feature_names = vectorizer.get_feature_names_out()
    coefficients = classifier.coef_[0]
    if phishing_index == 0:
        coefficients = -coefficients
    contributions = []
    for feature_index, value in zip(feature_values.indices, feature_values.data):
        contribution = float(value * coefficients[feature_index])
        if contribution > 0:
            contributions.append((contribution, str(feature_names[feature_index])))
    contributions.sort(reverse=True)
    top_terms = []
    seen_terms = set()
    for _, term in contributions:
        if term not in seen_terms:
            seen_terms.add(term)
            top_terms.append(term)
        if len(top_terms) == 3:
            break
    if top_terms:
        explanation = (
            "Model-weighted message terms associated with phishing: "
            + ", ".join(top_terms)
            + "."
        )
    else:
        explanation = (
            "No individual message term had a positive phishing weight; "
            "the label follows the model's overall class scores."
        )

    return {
        "predicted_label": predicted_label,
        "risk_score": risk_score,
        "explanation": explanation,
    }
