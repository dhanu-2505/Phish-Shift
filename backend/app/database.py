import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"
SCHEMA_FILE = BACKEND_DIR / "sql" / "init_db.sql"
EXPECTED_DATABASE = "phishshift_db"
EXPECTED_TABLES = frozenset(
    {"scan_results", "model_evaluations", "model_versions"}
)
AUTH_TABLES = frozenset({"users", "auth_sessions"})


class DatabaseConfigurationError(ValueError):
    """Raised when local database settings are missing or unsafe."""


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    ssl_ca: str | None


def get_database_settings() -> DatabaseSettings:
    load_dotenv(ENV_FILE, override=False)

    app_environment = os.getenv("APP_ENV", "development").strip().lower()
    database = os.getenv("DB_NAME", EXPECTED_DATABASE).strip()
    if database != EXPECTED_DATABASE:
        raise DatabaseConfigurationError(
            f"DB_NAME must be {EXPECTED_DATABASE!r}; refusing to use another database."
        )

    host = os.getenv("DB_HOST", "127.0.0.1").strip()
    if not host:
        raise DatabaseConfigurationError("Set DB_HOST in the backend environment.")
    if app_environment == "production":
        try:
            address = ipaddress.ip_address(host)
            is_loopback = address.is_loopback or (
                address.ipv4_mapped is not None
                and address.ipv4_mapped.is_loopback
            )
        except ValueError:
            normalized_host = host.casefold().rstrip(".")
            is_loopback = (
                normalized_host == "localhost"
                or normalized_host.endswith(".localhost")
            )
        if is_loopback:
            raise DatabaseConfigurationError(
                "Production DB_HOST must be a remote database hostname or address."
            )

    user = os.getenv("DB_USER", "").strip()
    password = os.getenv("DB_PASSWORD", "")
    allow_empty_password = os.getenv("DB_ALLOW_EMPTY_PASSWORD", "").strip().lower()
    if not user:
        raise DatabaseConfigurationError(
            "Set DB_USER in backend/.env using your local MariaDB username."
        )
    if not password and allow_empty_password != "true":
        raise DatabaseConfigurationError(
            "Set DB_PASSWORD in backend/.env, or explicitly set "
            "DB_ALLOW_EMPTY_PASSWORD=true if the account has no password."
        )
    if app_environment == "production" and (
        not password or allow_empty_password == "true"
    ):
        raise DatabaseConfigurationError(
            "Production database accounts must use a non-empty password."
        )
    ssl_ca = os.getenv("DB_SSL_CA", "").strip()
    if app_environment == "production" and not ssl_ca:
        raise DatabaseConfigurationError(
            "Set DB_SSL_CA to the trusted CA certificate file for the production database."
        )
    if ssl_ca and not Path(ssl_ca).is_file():
        raise DatabaseConfigurationError(
            "DB_SSL_CA must point to an existing CA certificate file."
        )

    try:
        port = int(os.getenv("DB_PORT", "3306"))
    except ValueError as exc:
        raise DatabaseConfigurationError("DB_PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("DB_PORT must be between 1 and 65535.")

    return DatabaseSettings(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        ssl_ca=ssl_ca or None,
    )


def open_database_connection():
    settings = get_database_settings()
    connection_options = {
        "host": settings.host,
        "port": settings.port,
        "database": settings.database,
        "user": settings.user,
        "password": settings.password,
        "connection_timeout": 5,
    }
    if settings.ssl_ca:
        connection_options.update(
            {
                "ssl_ca": settings.ssl_ca,
                "ssl_verify_cert": True,
                "ssl_verify_identity": True,
            }
        )
    return mysql.connector.connect(
        **connection_options,
    )


def check_database_connection() -> None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        if result is None or result[0] != 1:
            raise RuntimeError("Database health query returned an unexpected result.")
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def save_scan_result(
    user_id: int,
    message_text: str,
    predicted_label: str,
    risk_score: float,
    explanation: str,
    record_kind: str = "user",
) -> int:
    if record_kind not in {"user", "verification", "demo"}:
        raise ValueError("Unsupported scan record kind.")
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO scan_results
                (user_id, message_text, predicted_label, risk_score, explanation, record_kind)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, message_text, predicted_label, risk_score, explanation, record_kind),
        )
        scan_id = cursor.lastrowid
        connection.commit()
        if scan_id is None:
            raise RuntimeError("Database did not return an id for the saved scan.")
        return int(scan_id)
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def list_scan_results(
    user_id: int,
    limit: int,
    offset: int,
    label: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict], int]:
    sort_columns = {"created_at": "created_at", "risk_score": "risk_score"}
    sort_directions = {"asc": "ASC", "desc": "DESC"}
    if sort_by not in sort_columns or sort_order not in sort_directions:
        raise ValueError("Unsupported scan history sort option.")

    where_clause = "user_id = %s"
    filter_parameters: list[object] = [user_id]
    if label is not None:
        where_clause += " AND predicted_label = %s"
        filter_parameters.append(label)

    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM scan_results WHERE {where_clause}", tuple(filter_parameters))
        count_row = cursor.fetchone()
        if count_row is None:
            raise RuntimeError("Database did not return the scan count.")

        cursor.execute(
            f"""
            SELECT id, predicted_label, risk_score, created_at, record_kind
            FROM scan_results
            WHERE {where_clause}
            ORDER BY {sort_columns[sort_by]} {sort_directions[sort_order]}, id {sort_directions[sort_order]}
            LIMIT %s OFFSET %s
            """,
            (*filter_parameters, limit, offset),
        )
        scans = [
            {
                "scan_id": int(row[0]),
                "predicted_label": str(row[1]),
                "risk_score": float(row[2]),
                "created_at": row[3].isoformat()
                if hasattr(row[3], "isoformat")
                else str(row[3]),
                "record_kind": str(row[4]),
            }
            for row in cursor.fetchall()
        ]
        return scans, int(count_row[0])
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def get_user_scan_summary(user_id: int) -> dict:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(predicted_label = %s), 0),
                COALESCE(SUM(predicted_label = %s), 0)
            FROM scan_results
            WHERE user_id = %s
            """,
            ("Phishing Email", "Safe Email", user_id),
        )
        counts = cursor.fetchone()
        if counts is None:
            raise RuntimeError("Database did not return dashboard scan counts.")
        cursor.execute(
            """
            SELECT id, predicted_label, risk_score, created_at, record_kind
            FROM scan_results
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, 5),
        )
        recent_scans = [
            {
                "scan_id": int(row[0]),
                "predicted_label": str(row[1]),
                "risk_score": float(row[2]),
                "created_at": row[3].isoformat()
                if hasattr(row[3], "isoformat")
                else str(row[3]),
                "record_kind": str(row[4]),
            }
            for row in cursor.fetchall()
        ]
        return {
            "total_scans": int(counts[0]),
            "phishing_scans": int(counts[1]),
            "safe_scans": int(counts[2]),
            "recent_scans": recent_scans,
        }
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def get_scan_result(scan_id: int, user_id: int) -> dict | None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, predicted_label, risk_score, explanation, created_at, record_kind
            FROM scan_results
            WHERE id = %s AND user_id = %s
            """,
            (scan_id, user_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "scan_id": int(row[0]),
            "predicted_label": str(row[1]),
            "risk_score": float(row[2]),
            "explanation": str(row[3]),
            "created_at": row[4].isoformat()
            if hasattr(row[4], "isoformat")
            else str(row[4]),
            "record_kind": str(row[5]),
        }
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def migrate_auth_schema() -> None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE()")
        selected_database = cursor.fetchone()
        if selected_database is None or selected_database[0] != EXPECTED_DATABASE:
            raise DatabaseConfigurationError(
                f"Connected database must be {EXPECTED_DATABASE!r}; no migration run."
            )
        database_name = selected_database[0]
        cursor.execute("SHOW TABLES")
        existing_tables = {row[0] for row in cursor.fetchall()}
        if not EXPECTED_TABLES.issubset(existing_tables):
            raise DatabaseConfigurationError(
                "Required PhishShift tables are missing; refusing auth migration."
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS `users` (
                `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                `name` VARCHAR(100) NOT NULL,
                `email_normalized` VARCHAR(254) NOT NULL,
                `password_hash` VARCHAR(255) NOT NULL,
                `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                PRIMARY KEY (`id`),
                UNIQUE KEY `uq_users_email_normalized` (`email_normalized`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS `auth_sessions` (
                `session_hash` CHAR(64) NOT NULL,
                `user_id` BIGINT UNSIGNED NOT NULL,
                `expires_at` DATETIME(6) NOT NULL,
                `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                PRIMARY KEY (`session_hash`),
                KEY `idx_auth_sessions_user_id` (`user_id`),
                KEY `idx_auth_sessions_expires_at` (`expires_at`),
                CONSTRAINT `fk_auth_sessions_user`
                    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )

        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (database_name, "scan_results"),
        )
        scan_columns = {row[0] for row in cursor.fetchall()}
        if "user_id" not in scan_columns:
            cursor.execute(
                "ALTER TABLE `scan_results` "
                "ADD COLUMN `user_id` BIGINT UNSIGNED NULL AFTER `id`"
            )

        cursor.execute(
            """
            SELECT INDEX_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (database_name, "scan_results"),
        )
        scan_indexes = {row[0] for row in cursor.fetchall()}
        if "idx_scan_results_user_created" not in scan_indexes:
            cursor.execute(
                "ALTER TABLE `scan_results` "
                "ADD KEY `idx_scan_results_user_created` (`user_id`, `created_at`)"
            )

        cursor.execute(
            """
            SELECT CONSTRAINT_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
              AND REFERENCED_TABLE_NAME = %s
            """,
            (database_name, "scan_results", "user_id", "users"),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                """
                ALTER TABLE `scan_results`
                ADD CONSTRAINT `fk_scan_results_user`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
                ON DELETE SET NULL
                """
            )
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def migrate_project_metadata_schema() -> None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE()")
        selected_database = cursor.fetchone()
        if selected_database is None or selected_database[0] != EXPECTED_DATABASE:
            raise DatabaseConfigurationError(
                f"Connected database must be {EXPECTED_DATABASE!r}; no migration run."
            )
        database_name = selected_database[0]
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS `dataset_metadata` (
                `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                `dataset_sha256` CHAR(64) NOT NULL,
                `dataset_name` VARCHAR(255) NOT NULL,
                `dataset_source` TEXT NOT NULL,
                `dataset_license` VARCHAR(255) NOT NULL,
                `source_rows` INT UNSIGNED NOT NULL,
                `source_safe_rows` INT UNSIGNED NOT NULL DEFAULT 0,
                `source_phishing_rows` INT UNSIGNED NOT NULL DEFAULT 0,
                `missing_text_rows` INT UNSIGNED NOT NULL,
                `missing_label_rows` INT UNSIGNED NOT NULL,
                `blank_text_rows` INT UNSIGNED NOT NULL,
                `conflicting_duplicate_groups` INT UNSIGNED NOT NULL,
                `conflicting_rows_excluded` INT UNSIGNED NOT NULL,
                `duplicate_rows_collapsed` INT UNSIGNED NOT NULL,
                `usable_unique_rows` INT UNSIGNED NOT NULL,
                `safe_rows` INT UNSIGNED NOT NULL,
                `phishing_rows` INT UNSIGNED NOT NULL,
                `training_rows` INT UNSIGNED NOT NULL,
                `test_rows` INT UNSIGNED NOT NULL,
                `random_state` INT UNSIGNED NOT NULL,
                `test_size_fraction` DECIMAL(5, 4) NOT NULL,
                `training_status` VARCHAR(32) NOT NULL,
                `artifact_path` VARCHAR(1024) NULL,
                `trained_at` DATETIME(6) NULL,
                `recorded_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                    ON UPDATE CURRENT_TIMESTAMP(6),
                PRIMARY KEY (`id`),
                UNIQUE KEY `uq_dataset_metadata_sha256` (`dataset_sha256`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (database_name, "dataset_metadata"),
        )
        dataset_columns = {row[0] for row in cursor.fetchall()}
        if "source_safe_rows" not in dataset_columns:
            cursor.execute(
                "ALTER TABLE `dataset_metadata` ADD COLUMN "
                "`source_safe_rows` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `source_rows`"
            )
        if "source_phishing_rows" not in dataset_columns:
            cursor.execute(
                "ALTER TABLE `dataset_metadata` ADD COLUMN "
                "`source_phishing_rows` INT UNSIGNED NOT NULL DEFAULT 0 "
                "AFTER `source_safe_rows`"
            )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            """,
            (database_name, "model_evaluations", "uq_model_evaluations_name_version"),
        )
        if not cursor.fetchone()[0]:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT model_name, model_version
                    FROM model_evaluations
                    GROUP BY model_name, model_version
                    HAVING COUNT(*) > 1
                ) AS duplicate_evaluations
                """
            )
            if cursor.fetchone()[0]:
                raise DatabaseConfigurationError(
                    "Duplicate model evaluation versions prevent adding a safe unique key."
                )
            cursor.execute(
                "ALTER TABLE `model_evaluations` "
                "ADD UNIQUE KEY `uq_model_evaluations_name_version` "
                "(`model_name`, `model_version`)"
            )

        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (database_name, "scan_results"),
        )
        scan_columns = {row[0] for row in cursor.fetchall()}
        if "record_kind" not in scan_columns:
            cursor.execute(
                "ALTER TABLE `scan_results` "
                "ADD COLUMN `record_kind` VARCHAR(16) NOT NULL DEFAULT 'legacy' "
                "AFTER `explanation`"
            )
        cursor.execute(
            """
            UPDATE scan_results
            SET record_kind = %s
            WHERE user_id IS NULL AND record_kind = %s
            """,
            ("legacy", "user"),
        )
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def record_training_run(metadata: dict, metrics: dict) -> None:
    counts = metadata["dataset_counts"]
    class_counts = metadata["class_counts_after_deduplication"]
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO dataset_metadata (
                dataset_sha256, dataset_name, dataset_source, dataset_license,
                source_rows, source_safe_rows, source_phishing_rows,
                missing_text_rows, missing_label_rows, blank_text_rows,
                conflicting_duplicate_groups, conflicting_rows_excluded,
                duplicate_rows_collapsed, usable_unique_rows, safe_rows, phishing_rows,
                training_rows, test_rows, random_state, test_size_fraction,
                training_status, artifact_path, trained_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                dataset_name = VALUES(dataset_name),
                dataset_source = VALUES(dataset_source),
                dataset_license = VALUES(dataset_license),
                source_rows = VALUES(source_rows),
                source_safe_rows = VALUES(source_safe_rows),
                source_phishing_rows = VALUES(source_phishing_rows),
                missing_text_rows = VALUES(missing_text_rows),
                missing_label_rows = VALUES(missing_label_rows),
                blank_text_rows = VALUES(blank_text_rows),
                conflicting_duplicate_groups = VALUES(conflicting_duplicate_groups),
                conflicting_rows_excluded = VALUES(conflicting_rows_excluded),
                duplicate_rows_collapsed = VALUES(duplicate_rows_collapsed),
                usable_unique_rows = VALUES(usable_unique_rows),
                safe_rows = VALUES(safe_rows),
                phishing_rows = VALUES(phishing_rows),
                training_rows = VALUES(training_rows),
                test_rows = VALUES(test_rows),
                random_state = VALUES(random_state),
                test_size_fraction = VALUES(test_size_fraction),
                training_status = VALUES(training_status),
                artifact_path = VALUES(artifact_path),
                trained_at = VALUES(trained_at)
            """,
            (
                metadata["dataset_sha256"],
                metadata["dataset_name"],
                metadata["dataset_source"],
                metadata["dataset_license"],
                counts["source_rows"],
                counts["source_safe_rows"],
                counts["source_phishing_rows"],
                counts["missing_text_rows"],
                counts["missing_label_rows"],
                counts["blank_text_rows"],
                counts["conflicting_duplicate_groups"],
                counts["conflicting_rows_excluded"],
                counts["duplicate_rows_collapsed"],
                counts["usable_unique_rows"],
                class_counts["Safe Email"],
                class_counts["Phishing Email"],
                metadata["training_rows"],
                metadata["test_rows"],
                metadata["random_state"],
                metadata["test_size_fraction"],
                "trained",
                "backend/models/phishshift_text_model.joblib",
                metadata["trained_at_utc"].replace("T", " ").replace("+00:00", ""),
            ),
        )
        cursor.execute(
            """
            INSERT INTO model_versions (
                model_name, model_version, artifact_path, training_dataset_name,
                training_dataset_version, training_dataset_source
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                artifact_path = VALUES(artifact_path),
                training_dataset_name = VALUES(training_dataset_name),
                training_dataset_version = VALUES(training_dataset_version),
                training_dataset_source = VALUES(training_dataset_source)
            """,
            (
                metadata["model_name"],
                metadata["model_version"],
                "backend/models/phishshift_text_model.joblib",
                metadata["dataset_name"],
                metadata["dataset_version"],
                metadata["dataset_source"],
            ),
        )
        cursor.execute(
            """
            INSERT INTO model_evaluations (
                model_name, model_version, dataset_name, dataset_version, dataset_source,
                precision_score, recall_score, f1_score, false_positive_rate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                dataset_name = VALUES(dataset_name),
                dataset_version = VALUES(dataset_version),
                dataset_source = VALUES(dataset_source),
                precision_score = VALUES(precision_score),
                recall_score = VALUES(recall_score),
                f1_score = VALUES(f1_score),
                false_positive_rate = VALUES(false_positive_rate)
            """,
            (
                metadata["model_name"],
                metadata["model_version"],
                metadata["dataset_name"],
                metadata["dataset_version"],
                metadata["dataset_source"],
                metrics["precision"],
                metrics["recall"],
                metrics["f1_score"],
                metrics["false_positive_rate"],
            ),
        )
        connection.commit()
    except mysql.connector.Error:
        connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def create_user_and_session(
    name: str,
    email_normalized: str,
    password_hash: str,
    session_hash: str,
    expires_at,
) -> dict:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (name, email_normalized, password_hash)
            VALUES (%s, %s, %s)
            """,
            (name, email_normalized, password_hash),
        )
        user_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO auth_sessions (session_hash, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (session_hash, user_id, expires_at),
        )
        connection.commit()
        return {"id": user_id, "name": name, "email": email_normalized}
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def get_user_by_email(email_normalized: str) -> dict | None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, name, email_normalized, password_hash
            FROM users
            WHERE email_normalized = %s
            """,
            (email_normalized,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": int(row[0]),
            "name": str(row[1]),
            "email": str(row[2]),
            "password_hash": str(row[3]),
        }
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def create_user_session(user_id: int, session_hash: str, expires_at) -> None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO auth_sessions (session_hash, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (session_hash, user_id, expires_at),
        )
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def get_session_user(session_hash: str) -> dict | None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT users.id, users.name, users.email_normalized
            FROM auth_sessions
            INNER JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.session_hash = %s
              AND auth_sessions.expires_at > UTC_TIMESTAMP(6)
            """,
            (session_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {"id": int(row[0]), "name": str(row[1]), "email": str(row[2])}
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def delete_user_session(session_hash: str) -> None:
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM auth_sessions WHERE session_hash = %s",
            (session_hash,),
        )
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def _schema_statements() -> dict[str, str]:
    statements = {}
    for raw_statement in SCHEMA_FILE.read_text(encoding="utf-8").split(";"):
        statement = raw_statement.strip()
        if not statement:
            continue
        match = re.match(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`([a-z_]+)`",
            statement,
            flags=re.IGNORECASE,
        )
        if match is None:
            raise ValueError("Schema file contains a statement other than a table creation.")
        table_name = match.group(1)
        if table_name not in EXPECTED_TABLES:
            raise ValueError(f"Unexpected table in schema file: {table_name}")
        statements[table_name] = statement

    if statements.keys() != EXPECTED_TABLES:
        raise ValueError("Schema file must define each expected table exactly once.")
    return statements


def initialize_missing_tables() -> list[str]:
    statements = _schema_statements()
    connection = open_database_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE()")
        selected_database = cursor.fetchone()
        if selected_database is None or selected_database[0] != EXPECTED_DATABASE:
            raise DatabaseConfigurationError(
                f"Connected database must be {EXPECTED_DATABASE!r}; no schema changes made."
            )

        cursor.execute("SHOW TABLES")
        existing_tables = {row[0] for row in cursor.fetchall()}
        missing_tables = sorted(EXPECTED_TABLES - existing_tables)
        for table_name in missing_tables:
            cursor.execute(statements[table_name])
        connection.commit()
        return missing_tables
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()
