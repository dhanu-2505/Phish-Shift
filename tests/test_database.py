import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app import database
from app.main import database_health


class DatabaseSettingsTests(unittest.TestCase):
    def test_refuses_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(database, "load_dotenv"):
                with self.assertRaises(database.DatabaseConfigurationError):
                    database.get_database_settings()

    def test_refuses_database_name_other_than_phishshift_db(self):
        with patch.dict(
            os.environ,
            {
                "DB_NAME": "another_database",
                "DB_USER": "local_user",
                "DB_PASSWORD": "test-only",
            },
            clear=True,
        ):
            with patch.object(database, "load_dotenv"):
                with self.assertRaises(database.DatabaseConfigurationError):
                    database.get_database_settings()


class DatabaseHealthTests(unittest.TestCase):
    @patch("app.database.open_database_connection")
    def test_runs_constant_health_query_and_closes_connection(self, open_connection):
        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = (1,)
        open_connection.return_value = connection

        database.check_database_connection()

        connection.cursor.return_value.execute.assert_called_once_with("SELECT 1")
        connection.cursor.return_value.close.assert_called_once_with()
        connection.close.assert_called_once_with()

    @patch("app.main.check_database_connection")
    def test_health_endpoint_reports_success(self, check_connection):
        response = database_health()

        check_connection.assert_called_once_with()
        self.assertEqual(response, {"status": "ok", "database": "phishshift_db"})

    @patch("app.main.check_database_connection")
    def test_health_endpoint_does_not_expose_connection_error(self, check_connection):
        check_connection.side_effect = database.DatabaseConfigurationError(
            "private configuration detail"
        )

        response = database_health()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private configuration detail", response.body.decode())


class DatabaseInitializationTests(unittest.TestCase):
    @patch("app.database.open_database_connection")
    def test_creates_only_missing_tables(self, open_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = ("phishshift_db",)
        cursor.fetchall.return_value = [("scan_results",), ("model_versions",)]
        open_connection.return_value = connection

        created_tables = database.initialize_missing_tables()

        self.assertEqual(created_tables, ["model_evaluations"])
        self.assertEqual(
            cursor.execute.call_args_list,
            [
                unittest.mock.call("SELECT DATABASE()"),
                unittest.mock.call("SHOW TABLES"),
                unittest.mock.call(
                    database._schema_statements()["model_evaluations"]
                ),
            ],
        )
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()

    @patch("app.database.open_database_connection")
    def test_refuses_to_initialize_wrong_selected_database(self, open_connection):
        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = ("another_database",)
        open_connection.return_value = connection

        with self.assertRaises(database.DatabaseConfigurationError):
            database.initialize_missing_tables()

        connection.cursor.return_value.execute.assert_called_once_with(
            "SELECT DATABASE()"
        )
        connection.commit.assert_not_called()
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
