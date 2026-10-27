import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import mysql.connector
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth import (
    SESSION_COOKIE_NAME,
    hash_password,
    normalize_email,
    verify_password,
)
from app.main import app, get_current_user


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def csrf(self) -> str:
        response = self.client.get("/api/auth/csrf")
        self.assertEqual(response.status_code, 200)
        return response.json()["csrf_token"]

    def post_with_csrf(self, path: str, body: dict, token: str | None = None):
        csrf_token = token or self.csrf()
        return self.client.post(
            path,
            json=body,
            headers={"X-CSRF-Token": csrf_token},
        )

    def test_registration_hashes_password_and_never_returns_hash(self):
        captured = {}

        def create_user(name, email, password_hash, session_hash, expires_at):
            captured["name"] = name
            captured["email"] = email
            captured["password_hash"] = password_hash
            captured["session_hash"] = session_hash
            return {"id": 9, "name": name, "email": email}

        with patch("app.main.database.create_user_and_session", side_effect=create_user):
            response = self.post_with_csrf(
                "/api/auth/register",
                {
                    "name": "  Test User  ",
                    "email": " Test.User@Example.com ",
                    "password": "a-strong-test-password",
                    "confirm_password": "a-strong-test-password",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["name"], "Test User")
        self.assertEqual(captured["email"], normalize_email("Test.User@Example.com"))
        self.assertNotEqual(captured["password_hash"], "a-strong-test-password")
        self.assertTrue(verify_password(captured["password_hash"], "a-strong-test-password"))
        self.assertEqual(response.json(), {
            "user": {"id": 9, "name": "Test User", "email": "test.user@example.com"}
        })
        self.assertNotIn("password_hash", response.text)
        session_cookie = response.cookies.get(SESSION_COOKIE_NAME)
        self.assertTrue(session_cookie)
        self.assertTrue(response.headers["set-cookie"].lower().find("httponly") >= 0)
        self.assertNotIn(session_cookie, response.text)

    def test_duplicate_normalized_email_returns_conflict(self):
        duplicate = mysql.connector.IntegrityError(
            msg="duplicate", errno=1062
        )
        with patch(
            "app.main.database.create_user_and_session",
            side_effect=duplicate,
        ):
            response = self.post_with_csrf(
                "/api/auth/register",
                {
                    "name": "Another User",
                    "email": "TEST.USER@example.com",
                    "password": "a-strong-test-password",
                    "confirm_password": "a-strong-test-password",
                },
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "An account with this email already exists.")

    def test_registration_validates_password_confirmation_and_minimum(self):
        with patch("app.main.database.create_user_and_session") as create_user:
            mismatch = self.post_with_csrf(
                "/api/auth/register",
                {
                    "name": "Test",
                    "email": "test@example.com",
                    "password": "a-strong-test-password",
                    "confirm_password": "a-different-test-password",
                },
            )
            short = self.post_with_csrf(
                "/api/auth/register",
                {
                    "name": "Test",
                    "email": "test@example.com",
                    "password": "short",
                    "confirm_password": "short",
                },
            )
        self.assertEqual(mismatch.status_code, 422)
        self.assertEqual(short.status_code, 422)
        create_user.assert_not_called()

    def test_registration_requires_csrf_token(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Test",
                "email": "test@example.com",
                "password": "a-strong-test-password",
                "confirm_password": "a-strong-test-password",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_login_success_uses_normalized_email_and_sets_session_cookie(self):
        password_hash = hash_password("a-strong-test-password")
        with (
            patch(
                "app.main.database.get_user_by_email",
                return_value={
                    "id": 4,
                    "name": "Test",
                    "email": "test@example.com",
                    "password_hash": password_hash,
                },
            ) as lookup,
            patch("app.main.database.create_user_session") as create_session,
        ):
            response = self.post_with_csrf(
                "/api/auth/login",
                {"email": " TEST@EXAMPLE.COM ", "password": "a-strong-test-password"},
            )

        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with("test@example.com")
        create_session.assert_called_once()
        self.assertEqual(response.json()["user"]["id"], 4)
        self.assertNotIn("password_hash", response.text)
        self.assertTrue(response.cookies.get(SESSION_COOKIE_NAME))
        self.assertTrue(response.headers["set-cookie"].lower().find("httponly") >= 0)

    def test_login_failure_is_generic_for_unknown_user_and_wrong_password(self):
        with patch("app.main.database.get_user_by_email", return_value=None):
            unknown = self.post_with_csrf(
                "/api/auth/login",
                {"email": "nobody@example.com", "password": "a-strong-test-password"},
            )
        password_hash = hash_password("a-strong-test-password")
        with patch(
            "app.main.database.get_user_by_email",
            return_value={
                "id": 4,
                "name": "Test",
                "email": "test@example.com",
                "password_hash": password_hash,
            },
        ):
            wrong_password = self.post_with_csrf(
                "/api/auth/login",
                {"email": "test@example.com", "password": "a-wrong-test-password"},
            )
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown.json()["detail"], wrong_password.json()["detail"])

    def test_protected_api_endpoints_reject_unauthenticated_requests(self):
        for path in (
            "/api/auth/me",
            "/api/scans",
            "/api/scans/1",
            "/api/model/evaluation",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
        response = self.client.post(
            "/api/predict",
            json={"message": "A test message."},
            headers={"X-CSRF-Token": "invalid"},
        )
        self.assertEqual(response.status_code, 401)

    def test_logout_requires_authentication_before_csrf(self):
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 401)

    def test_expired_server_side_session_is_rejected(self):
        self.client.cookies.set(SESSION_COOKIE_NAME, "expired-session-token")
        with patch("app.auth.database.get_session_user", return_value=None):
            response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertIn("expired", response.json()["detail"].lower())

    def test_logout_revokes_session_and_clears_cookie(self):
        csrf = self.csrf()
        self.client.cookies.set(SESSION_COOKIE_NAME, "valid-session-token")
        user = {"id": 7, "name": "Test", "email": "test@example.com"}
        with (
            patch("app.auth.database.get_session_user", return_value=user),
            patch("app.main.database.delete_user_session") as delete_session,
        ):
            response = self.post_with_csrf(
                "/api/auth/logout", {}, token=csrf
            )
        self.assertEqual(response.status_code, 200)
        delete_session.assert_called_once()
        self.assertEqual(response.json(), {"status": "ok"})
        after_logout = self.client.get("/api/auth/me")
        self.assertEqual(after_logout.status_code, 401)

    def test_scan_history_uses_authenticated_user_scope(self):
        user = {"id": 31, "name": "First User", "email": "first@example.com"}
        app.dependency_overrides[get_current_user] = lambda: user
        with patch(
            "app.main.list_scan_results",
            return_value=([], 0),
        ) as list_scans:
            response = self.client.get("/api/scans?page=1&page_size=10")
        self.assertEqual(response.status_code, 200)
        list_scans.assert_called_once_with(
            31, 10, 0, None, "created_at", "desc"
        )

    def test_cross_user_scan_access_returns_not_found(self):
        user = {"id": 31, "name": "First User", "email": "first@example.com"}
        app.dependency_overrides[get_current_user] = lambda: user
        with patch("app.main.get_scan_result", return_value=None) as get_scan:
            response = self.client.get("/api/scans/77")
        self.assertEqual(response.status_code, 404)
        get_scan.assert_called_once_with(77, 31)

    def test_prediction_persists_with_authenticated_user_id(self):
        user = {"id": 31, "name": "First User", "email": "first@example.com"}
        app.dependency_overrides[get_current_user] = lambda: user
        csrf = self.csrf()
        with (
            patch(
                "app.main.predict_message",
                return_value={
                    "predicted_label": "Safe Email",
                    "risk_score": 0.2,
                    "explanation": "Model explanation.",
                },
            ),
            patch("app.main.save_scan_result", return_value=88) as save_scan,
        ):
            response = self.client.post(
                "/api/predict",
                json={"message": "Non-sensitive integration test message."},
                headers={"X-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scan_id"], 88)
        self.assertEqual(save_scan.call_args.args[0], 31)
        self.assertNotIn("user_id", response.json())

    def test_prediction_http_endpoint_runs_real_model_with_test_scoped_persistence(self):
        user = {"id": 31, "name": "First User", "email": "first@example.com"}
        app.dependency_overrides[get_current_user] = lambda: user
        csrf = self.csrf()
        with patch("app.main.save_scan_result", return_value=987) as save_scan:
            response = self.client.post(
                "/api/predict",
                json={"message": "Please review the agenda for our meeting."},
                headers={"X-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["scan_id"], 987)
        self.assertIn(result["predicted_label"], {"Safe Email", "Phishing Email"})
        self.assertGreaterEqual(result["risk_score"], 0)
        self.assertLessEqual(result["risk_score"], 1)
        self.assertTrue(result["explanation"])
        self.assertEqual(save_scan.call_args.args[0], 31)


if __name__ == "__main__":
    unittest.main()
