import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app import database
from app.main import database_health, get_frontend_origins, readiness_health


class DatabaseSettingsTests(unittest.TestCase):
    def test_refuses_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(database, "load_dotenv"):
                with self.assertRaises(database.DatabaseConfigurationError):
                    database.get_database_settings()

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "DB_NAME": "phishshift_db",
            "DB_HOST": "127.0.0.1",
            "DB_USER": "remote_user",
            "DB_PASSWORD": "configured-only-in-test",
            "DB_ALLOW_EMPTY_PASSWORD": "false",
        },
        clear=False,
    )
    def test_production_refuses_loopback_database_host(self):
        with self.assertRaisesRegex(
            database.DatabaseConfigurationError, "remote database hostname"
        ):
            database.get_database_settings()

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "DB_NAME": "phishshift_db",
            "DB_HOST": "service.localhost.",
            "DB_USER": "remote_user",
            "DB_PASSWORD": "configured-only-in-test",
            "DB_ALLOW_EMPTY_PASSWORD": "false",
        },
        clear=False,
    )
    def test_production_refuses_localhost_subdomains(self):
        with self.assertRaisesRegex(
            database.DatabaseConfigurationError, "remote database hostname"
        ):
            database.get_database_settings()

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "DB_NAME": "phishshift_db",
            "DB_HOST": "db.example.invalid",
            "DB_USER": "remote_user",
            "DB_PASSWORD": "",
            "DB_ALLOW_EMPTY_PASSWORD": "true",
        },
        clear=False,
    )
    def test_production_refuses_empty_database_password(self):
        with self.assertRaisesRegex(
            database.DatabaseConfigurationError, "non-empty password"
        ):
            database.get_database_settings()

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "DB_NAME": "phishshift_db",
            "DB_HOST": "db.example.invalid",
            "DB_USER": "remote_user",
            "DB_PASSWORD": "configured-only-in-test",
            "DB_ALLOW_EMPTY_PASSWORD": "false",
            "DB_SSL_CA": "",
        },
        clear=False,
    )
    def test_production_requires_database_ca_certificate(self):
        with self.assertRaisesRegex(
            database.DatabaseConfigurationError, "DB_SSL_CA"
        ):
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

    @patch("app.main.load_model_bundle")
    @patch("app.main.check_database_connection")
    def test_readiness_endpoint_checks_database_and_model(
        self, check_connection, load_model
    ):
        response = readiness_health()

        check_connection.assert_called_once_with()
        load_model.assert_called_once_with()
        self.assertEqual(response, {"status": "ok"})

    @patch("app.main.check_database_connection")
    def test_readiness_endpoint_returns_sanitized_database_failure(self, check_connection):
        check_connection.side_effect = database.DatabaseConfigurationError(
            "private configuration detail"
        )

        response = readiness_health()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private configuration detail", response.body.decode())


class ProductionCorsSettingsTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "FRONTEND_ORIGINS": "https://phishshift.example",
        },
        clear=False,
    )
    def test_accepts_exact_https_production_origin(self):
        self.assertEqual(
            get_frontend_origins(),
            ["https://phishshift.example"],
        )

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "FRONTEND_ORIGINS": "*",
        },
        clear=False,
    )
    def test_rejects_wildcard_production_origin(self):
        with self.assertRaisesRegex(RuntimeError, "exact HTTPS origins"):
            get_frontend_origins()

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "FRONTEND_ORIGINS": "https://phishshift.example/",
        },
        clear=False,
    )
    def test_rejects_production_origin_with_trailing_path(self):
        with self.assertRaisesRegex(RuntimeError, "exact HTTPS origins"):
            get_frontend_origins()


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
