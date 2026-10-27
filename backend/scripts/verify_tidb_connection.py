import getpass
import hashlib
import os
import re
import ssl
import sys
from pathlib import Path

from app.database import (
    EXPECTED_DATABASE,
    DatabaseConfigurationError,
    get_database_settings,
    open_database_connection,
)


EXPECTED_TABLES = {
    "scan_results",
    "model_evaluations",
    "model_versions",
}
ISRG_ROOT_X1_SHA256 = (
    "96BCEC06264976F37460779ACF28C5A7"
    "CFE8A3C0AAE11A8FFCEE05C0BDDF08C6"
)
ENVIRONMENT_KEYS = (
    "APP_ENV",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_SSL_CA",
    "DB_ALLOW_EMPTY_PASSWORD",
)
DEFAULT_CA_PATH = Path.home() / "Downloads" / "isrgrootx1.pem"


def prompt_required(prompt: str) -> str:
    value = input(prompt).strip()
    if not value:
        raise ValueError("A required value was not provided.")
    return value


def prompt_cloud_endpoint() -> str:
    host = prompt_required(
        "Enter the hostname shown in TiDB Cloud > Connect (hostname only): "
    ).rstrip(".")
    confirmation = prompt_required(
        "Enter the hostname again to confirm it matches the TiDB Cloud console: "
    ).rstrip(".")
    if host.casefold() != confirmation.casefold():
        raise ValueError("The hostname entries differ; verify the TiDB Cloud Connect dialog.")
    if not host.casefold().endswith(".tidbcloud.com"):
        raise ValueError("The endpoint must be a TiDB Cloud *.tidbcloud.com hostname.")
    return host


def prompt_port() -> str:
    port = prompt_required("Enter the port shown in the TiDB Cloud Connect dialog: ")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("The port must be an integer from 1 to 65535.")
    return port


def prompt_ca_path() -> Path:
    default = str(DEFAULT_CA_PATH)
    entered = input(
        f"Enter the ISRG Root X1 PEM path, or press Enter for {default}: "
    ).strip()
    if len(entered) >= 2 and entered[0] == entered[-1] and entered[0] in {"'", '"'}:
        entered = entered[1:-1]
    path = Path(entered or default).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            "The CA certificate file was not found. Use the official TiDB Cloud "
            "TLS instructions to obtain ISRG Root X1."
        )

    try:
        certificate_der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("The selected CA file is not a valid PEM certificate.") from exc

    fingerprint = hashlib.sha256(certificate_der).hexdigest().upper()
    if fingerprint != ISRG_ROOT_X1_SHA256:
        raise ValueError(
            "The selected certificate is not the expected ISRG Root X1 certificate."
        )
    return path.resolve()


def safe_error_message(error: Exception, private_values: list[str]) -> str:
    message = str(error)
    for value in sorted((item for item in private_values if item), key=len, reverse=True):
        message = re.sub(re.escape(value), "<redacted>", message, flags=re.IGNORECASE)
    return message or "No additional diagnostic message was provided."


def verify_negotiated_tls(connection) -> None:
    cipher = None
    native_connection = getattr(connection, "_cmysql", None)
    native_cipher = getattr(native_connection, "get_ssl_cipher", None)
    if callable(native_cipher):
        cipher = native_cipher()
    else:
        socket_wrapper = getattr(connection, "_socket", None)
        raw_socket = getattr(socket_wrapper, "sock", None)
        socket_cipher = getattr(raw_socket, "cipher", None)
        if callable(socket_cipher):
            cipher_details = socket_cipher()
            if cipher_details:
                cipher = cipher_details[0]

    if not cipher:
        raise RuntimeError("A negotiated TLS cipher could not be confirmed.")


def main() -> int:
    connection = None
    cursor = None
    private_values: list[str] = []
    password = ""

    try:
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Run this verifier in an interactive terminal so credentials stay masked."
            )
        host = prompt_cloud_endpoint()
        port = prompt_port()
        username = getpass.getpass(
            "Enter the database username shown in the TiDB Cloud Connect dialog: "
        )
        if not username:
            raise ValueError("The database username must not be empty.")
        ca_path = prompt_ca_path()
        password = getpass.getpass("Enter the TiDB Cloud database password: ")
        if not password:
            raise ValueError("The database password must not be empty.")

        private_values = [host, username, password, str(ca_path)]
        os.environ.update(
            {
                "APP_ENV": "production",
                "DB_HOST": host,
                "DB_PORT": port,
                "DB_NAME": EXPECTED_DATABASE,
                "DB_USER": username,
                "DB_PASSWORD": password,
                "DB_SSL_CA": str(ca_path),
                "DB_ALLOW_EMPTY_PASSWORD": "false",
            }
        )
        settings = get_database_settings()
        if settings.database != EXPECTED_DATABASE or not settings.ssl_ca:
            raise DatabaseConfigurationError(
                "Cloud database name or TLS CA configuration is invalid."
            )

        connection = open_database_connection()
        verify_negotiated_tls(connection)
        cursor = connection.cursor()

        cursor.execute("SELECT DATABASE()")
        selected_database = cursor.fetchone()[0]
        cursor.execute("SELECT VERSION()")
        server_version = str(cursor.fetchone()[0])
        cursor.execute("SHOW TABLES")
        tables = {str(row[0]) for row in cursor.fetchall()}

        if selected_database != EXPECTED_DATABASE:
            raise RuntimeError("The active database is not phishshift_db.")
        if "tidb" not in server_version.casefold():
            raise RuntimeError("The server version did not identify TiDB.")

        missing_tables = EXPECTED_TABLES - tables
        if missing_tables:
            print(
                "Connection verified, but expected core tables are missing: "
                + ", ".join(sorted(missing_tables)),
                file=sys.stderr,
            )
            return 1

        print("TLS certificate and server identity verification: passed")
        print("Negotiated TLS cipher: confirmed")
        print("Selected database: phishshift_db")
        print("TiDB version:", server_version)
        print("Tables:", ", ".join(sorted(tables)))
        return 0
    except Exception as exc:
        message = safe_error_message(exc, private_values)
        print(
            f"Read-only TiDB verification failed ({type(exc).__name__}): {message}",
            file=sys.stderr,
        )
        return 1
    finally:
        try:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception as exc:
                    print(
                        "Cursor cleanup failed "
                        f"({type(exc).__name__}); details suppressed.",
                        file=sys.stderr,
                    )
        finally:
            try:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception as exc:
                        print(
                            "Connection cleanup failed "
                            f"({type(exc).__name__}); details suppressed.",
                            file=sys.stderr,
                        )
            finally:
                for key in ENVIRONMENT_KEYS:
                    os.environ.pop(key, None)
                password = ""


if __name__ == "__main__":
    raise SystemExit(main())
