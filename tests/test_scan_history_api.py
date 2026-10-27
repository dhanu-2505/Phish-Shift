import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.main import model_evaluation, scan_detail, scan_history


class ScanHistoryApiTests(unittest.TestCase):
    @patch("app.main.list_scan_results")
    def test_history_returns_paged_metadata_without_message_content(self, list_scans):
        list_scans.return_value = (
            [
                {
                    "scan_id": 8,
                    "predicted_label": "Safe Email",
                    "risk_score": 0.12,
                    "created_at": "2026-10-26T08:00:00",
                    "record_kind": "user",
                }
            ],
            21,
        )

        response = scan_history(
            page=2,
            page_size=10,
            label=None,
            sort_by="created_at",
            sort_order="desc",
            current_user={"id": 12, "name": "Test", "email": "test@example.com"},
        )

        list_scans.assert_called_once_with(
            12, 10, 10, None, "created_at", "desc"
        )
        self.assertEqual(response["total"], 21)
        self.assertEqual(response["total_pages"], 3)
        self.assertEqual(response["items"][0]["scan_id"], 8)
        self.assertNotIn("message_text", response["items"][0])

    @patch("app.main.list_scan_results")
    def test_history_database_error_is_sanitized(self, list_scans):
        from app.database import DatabaseConfigurationError

        list_scans.side_effect = DatabaseConfigurationError("private configuration")

        response = scan_history(
            page=1,
            page_size=10,
            label=None,
            sort_by="created_at",
            sort_order="desc",
            current_user={"id": 12, "name": "Test", "email": "test@example.com"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private configuration", response.body.decode())

    @patch("app.main.get_scan_result")
    def test_detail_returns_only_scan_result_fields(self, get_scan):
        get_scan.return_value = {
            "scan_id": 4,
            "predicted_label": "Phishing Email",
            "risk_score": 0.91,
            "explanation": "Model-weighted terms.",
            "created_at": "2026-10-26T08:00:00",
            "record_kind": "user",
        }

        response = scan_detail(
            4,
            current_user={"id": 12, "name": "Test", "email": "test@example.com"},
        )

        get_scan.assert_called_once_with(4, 12)
        self.assertEqual(response["scan_id"], 4)
        self.assertNotIn("message_text", response)

    @patch("app.main.get_scan_result", return_value=None)
    def test_missing_detail_returns_not_found(self, _get_scan):
        with self.assertRaises(HTTPException) as context:
            scan_detail(
                404,
                current_user={"id": 12, "name": "Test", "email": "test@example.com"},
            )
        self.assertEqual(context.exception.status_code, 404)

    def test_evaluation_endpoint_exposes_held_out_metrics(self):
        response = model_evaluation(current_user={"id": 12, "name": "Test", "email": "test@example.com"})

        self.assertIn("f1_score", response)
        self.assertIn("confusion_matrix", response)
        self.assertIn("false_positive_rate", response)
        self.assertNotIn("message_text", response)


if __name__ == "__main__":
    unittest.main()
