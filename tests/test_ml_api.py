import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app import database
from app.main import (
    PredictionRequest,
    database_health,
    model_health,
    predict,
)
from app.model import MODEL_ARTIFACT, ModelUnavailableError, predict_message
from train_model import load_dataset


class DatasetTrainingTests(unittest.TestCase):
    def test_trained_artifact_exists_and_contains_expected_pipeline(self):
        self.assertTrue(MODEL_ARTIFACT.is_file(), "Run the documented training script.")
        result = predict_message("Please review the meeting agenda.")

        self.assertIn(result["predicted_label"], {"Safe Email", "Phishing Email"})
        self.assertGreaterEqual(result["risk_score"], 0.0)
        self.assertLessEqual(result["risk_score"], 1.0)
        self.assertTrue(result["explanation"])

    def test_dataset_cleaning_prevents_exact_normalized_duplicate_leakage(self):
        texts, labels, class_counts, counts = load_dataset()
        canonical = [re.sub(r"\s+", " ", text).strip().casefold() for text in texts]
        self.assertEqual(len(texts), 17513)
        self.assertEqual(len(canonical), len(set(canonical)))
        self.assertEqual(len(labels), len(texts))
        self.assertEqual(sum(class_counts.values()), len(texts))
        self.assertEqual(counts["source_rows"], 18650)
        self.assertEqual(counts["missing_text_rows"], 16)
        self.assertEqual(counts["missing_label_rows"], 0)
        self.assertEqual(counts["blank_text_rows"], 3)
        self.assertGreater(counts["duplicate_rows_collapsed"], 0)
        self.assertGreaterEqual(counts["conflicting_duplicate_groups"], 0)


class PredictionValidationTests(unittest.TestCase):
    def test_rejects_blank_message(self):
        with self.assertRaises(ValidationError):
            PredictionRequest(message=" \t\n ")

    def test_rejects_message_over_limit(self):
        with self.assertRaises(ValidationError):
            PredictionRequest(message="x" * 20001)


class DatabasePersistenceTests(unittest.TestCase):
    @patch("app.database.open_database_connection")
    def test_scan_insert_is_parameterized_and_returns_id(self, open_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.lastrowid = 42
        open_connection.return_value = connection
        message = "private test message"

        scan_id = database.save_scan_result(
            23,
            message,
            "Safe Email",
            0.125,
            "Model-weighted message terms associated with phishing: example.",
            "user",
        )

        self.assertEqual(scan_id, 42)
        args, kwargs = cursor.execute.call_args
        self.assertIn("%s", args[0])
        self.assertEqual(
            args[1],
            (
                23,
                message,
                "Safe Email",
                0.125,
                "Model-weighted message terms associated with phishing: example.",
                "user",
            ),
        )
        self.assertEqual(kwargs, {})
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()

    @patch("app.database.open_database_connection")
    def test_history_query_is_parameterized_and_omits_message_text(self, open_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = (1,)
        cursor.fetchall.return_value = [
            (7, "Safe Email", 0.12, "2026-10-26T10:00:00", "user")
        ]
        open_connection.return_value = connection

        scans, total = database.list_scan_results(user_id=23, limit=10, offset=20)

        self.assertEqual(total, 1)
        self.assertEqual(scans[0]["scan_id"], 7)
        self.assertNotIn("message_text", scans[0])
        query, parameters = cursor.execute.call_args_list[1].args
        self.assertIn("LIMIT %s OFFSET %s", query)
        self.assertNotIn("message_text", query)
        self.assertEqual(parameters, (23, 10, 20))
        connection.close.assert_called_once_with()

    @patch("app.database.open_database_connection")
    def test_detail_query_is_parameterized_and_omits_message_text(self, open_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = (
            7,
            "Safe Email",
            0.12,
            "Model explanation",
            "2026-10-26T10:00:00",
            "user",
        )
        open_connection.return_value = connection

        scan = database.get_scan_result(7, user_id=23)

        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE id = %s", query)
        self.assertNotIn("message_text", query)
        self.assertEqual(parameters, (7, 23))
        self.assertNotIn("message_text", scan)
        connection.close.assert_called_once_with()

    @patch("app.database.open_database_connection")
    def test_history_filters_and_sorts_with_parameterized_inputs(self, open_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = (1,)
        cursor.fetchall.return_value = []
        open_connection.return_value = connection

        scans, total = database.list_scan_results(
            user_id=23,
            limit=10,
            offset=0,
            label="Phishing Email",
            sort_by="risk_score",
            sort_order="asc",
        )

        self.assertEqual((scans, total), ([], 1))
        self.assertEqual(
            cursor.execute.call_args_list[0].args[1],
            (23, "Phishing Email"),
        )
        detail_query, parameters = cursor.execute.call_args_list[1].args
        self.assertIn("ORDER BY risk_score ASC, id ASC", detail_query)
        self.assertNotIn("Phishing Email", detail_query)
        self.assertEqual(parameters, (23, "Phishing Email", 10, 0))
        connection.close.assert_called_once_with()

    @patch("app.database.open_database_connection")
    def test_scan_history_rejects_unsupported_sort_columns(self, open_connection):
        with self.assertRaises(ValueError):
            database.list_scan_results(23, 10, 0, sort_by="message_text")
        open_connection.assert_not_called()

    @patch("app.database.open_database_connection")
    def test_user_dashboard_summary_returns_real_aggregates(self, open_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = (4, 1, 3)
        cursor.fetchall.return_value = [
            (9, "Phishing Email", 0.83, "2026-10-26T10:00:00", "user")
        ]
        open_connection.return_value = connection

        summary = database.get_user_scan_summary(23)

        self.assertEqual(summary["total_scans"], 4)
        self.assertEqual(summary["phishing_scans"], 1)
        self.assertEqual(summary["safe_scans"], 3)
        self.assertEqual(summary["recent_scans"][0]["scan_id"], 9)
        self.assertNotIn("message_text", summary["recent_scans"][0])
        self.assertEqual(cursor.execute.call_args_list[0].args[1], (
            "Phishing Email",
            "Safe Email",
            23,
        ))

    @patch("app.database.open_database_connection")
    def test_training_metadata_is_saved_with_idempotent_parameterized_upserts(self, open_connection):
        connection = MagicMock()
        open_connection.return_value = connection
        metadata = {
            "dataset_counts": {
                "source_rows": 10,
                "source_safe_rows": 5,
                "source_phishing_rows": 5,
                "missing_text_rows": 0,
                "missing_label_rows": 0,
                "blank_text_rows": 0,
                "conflicting_duplicate_groups": 0,
                "conflicting_rows_excluded": 0,
                "duplicate_rows_collapsed": 1,
                "usable_unique_rows": 9,
            },
            "class_counts_after_deduplication": {
                "Safe Email": 5,
                "Phishing Email": 4,
            },
            "dataset_sha256": "a" * 64,
            "dataset_name": "Documented test dataset",
            "dataset_source": "https://example.invalid/dataset",
            "dataset_license": "test license",
            "training_rows": 7,
            "test_rows": 2,
            "random_state": 42,
            "test_size_fraction": 0.2,
            "trained_at_utc": "2026-10-26T10:00:00+00:00",
            "model_name": "Test model",
            "model_version": "test-version",
            "dataset_version": "a" * 64,
        }
        metrics = {
            "precision": 0.8,
            "recall": 0.75,
            "f1_score": 0.77,
            "false_positive_rate": 0.1,
        }

        database.record_training_run(metadata, metrics)

        self.assertEqual(connection.cursor.return_value.execute.call_count, 3)
        for query, parameters in (
            call.args for call in connection.cursor.return_value.execute.call_args_list
        ):
            self.assertIn("ON DUPLICATE KEY UPDATE", query)
            self.assertIn("%s", query)
            self.assertTrue(parameters)
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()


class PredictionApiTests(unittest.TestCase):
    @patch("app.main.save_scan_result", return_value=17)
    @patch("app.main.predict_message")
    def test_prediction_response_is_saved_and_returns_model_output(
        self, prediction, save_result
    ):
        prediction.return_value = {
            "predicted_label": "Safe Email",
            "risk_score": 0.12,
            "explanation": "Model-weighted message terms: review.",
        }
        request = PredictionRequest(message="Please review the agenda.")

        response = predict(request, current_user={"id": 7, "name": "Test", "email": "test@example.com"})

        self.assertEqual(
            response,
            {
                "scan_id": 17,
                "predicted_label": "Safe Email",
                "risk_score": 0.12,
                "explanation": "Model-weighted message terms: review.",
            },
        )
        save_result.assert_called_once_with(
            7,
            request.message,
            "Safe Email",
            0.12,
            "Model-weighted message terms: review.",
            "user",
        )

    @patch("app.main.save_scan_result", side_effect=database.DatabaseConfigurationError("unavailable"))
    @patch("app.main.predict_message")
    def test_prediction_is_not_reported_successful_when_persistence_fails(
        self, prediction, _save_result
    ):
        prediction.return_value = {
            "predicted_label": "Safe Email",
            "risk_score": 0.12,
            "explanation": "Model-weighted message terms: review.",
        }
        with self.assertRaises(HTTPException) as context:
            predict(
                PredictionRequest(message="Please review the agenda."),
                current_user={"id": 7, "name": "Test", "email": "test@example.com"},
            )
        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(context.exception.detail, "Prediction history could not be saved.")

    @patch("app.main.load_model_bundle", side_effect=ModelUnavailableError("missing"))
    def test_model_health_reports_missing_artifact(self, _load_bundle):
        response = model_health()

        self.assertEqual(response.status_code, 503)

    @patch("app.main.check_database_connection")
    def test_existing_database_health_endpoint_remains_working(self, check_connection):
        response = database_health()

        check_connection.assert_called_once_with()
        self.assertEqual(response, {"status": "ok", "database": "phishshift_db"})


if __name__ == "__main__":
    unittest.main()
