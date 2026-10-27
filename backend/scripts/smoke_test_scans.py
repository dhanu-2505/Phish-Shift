import getpass
import json
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


SAMPLE_MESSAGES = (
    (
        "A team meeting is scheduled for Thursday at 10 AM. Please bring the project notes.",
        "user",
    ),
    (
        "Your mailbox will be disabled today. Sign in immediately at "
        "https://example.invalid/account to keep access.",
        "verification",
    ),
    (
        "Thanks for sending the report. I reviewed the figures and added comments to the shared document.",
        "user",
    ),
    (
        "We could not deliver your package. Confirm your details at "
        "https://example.invalid/parcel before midnight.",
        "verification",
    ),
    (
        "The library closes at 6 PM on weekdays. Your reserved book is ready for pickup.",
        "user",
    ),
    (
        "A payment was declined. Reply with your account details or visit "
        "https://example.invalid/secure to restore your access.",
        "verification",
    ),
)


class SafeApiError(RuntimeError):
    pass


def request_json(opener, url: str, method: str = "GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = {"Accept": "application/json"}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SafeApiError(f"API request failed with HTTP {exc.code}.") from None
    except urllib.error.URLError:
        raise SafeApiError("The local API could not be reached.") from None


def csrf_header(opener, base_url: str) -> dict[str, str]:
    _, payload = request_json(opener, f"{base_url}/api/auth/csrf")
    return {"X-CSRF-Token": payload["csrf_token"]}


def run(base_url: str, email: str) -> int:
    cookies = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    password = getpass.getpass("Account password (input hidden): ")
    try:
        request_json(
            opener,
            f"{base_url}/api/auth/login",
            method="POST",
            body={"email": email, "password": password},
            headers=csrf_header(opener, base_url),
        )
    except SafeApiError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1
    finally:
        password = ""

    print("Authenticated. Sending six real model predictions; message text will not be printed.")
    saved = 0
    try:
        for index, (message, record_kind) in enumerate(SAMPLE_MESSAGES, start=1):
            _, result = request_json(
                opener,
                f"{base_url}/api/predict",
                method="POST",
                body={"message": message, "record_kind": record_kind},
                headers=csrf_header(opener, base_url),
            )
            print(
                f"Scan {index}: id={result['scan_id']}, "
                f"label={result['predicted_label']}, "
                f"risk={float(result['risk_score']):.4f}, "
                f"kind={record_kind}"
            )
            saved += 1

        _, history = request_json(
            opener,
            f"{base_url}/api/scans?page=1&page_size=100&sort_by=created_at&sort_order=desc",
        )
        print(f"Authenticated history returned {history['total']} scans.")
    except SafeApiError as exc:
        print(f"Verification stopped after {saved} saved scans: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            request_json(
                opener,
                f"{base_url}/api/auth/logout",
                method="POST",
                body={},
                headers=csrf_header(opener, base_url),
            )
            print("Session logged out.")
        except SafeApiError:
            print("Warning: automatic logout failed; close the browser session or retry logout.", file=sys.stderr)
    return 0 if saved == len(SAMPLE_MESSAGES) else 1


def main() -> int:
    base_url = input("Local API base URL [http://127.0.0.1:8765]: ").strip()
    if not base_url:
        base_url = "http://127.0.0.1:8765"
    base_url = base_url.rstrip("/")
    email = input("Account email: ").strip()
    if not email:
        print("An account email is required.", file=sys.stderr)
        return 2
    confirmation = input(
        "This will save six labeled verification/user scans to that account. Continue? [y/N]: "
    ).strip().casefold()
    if confirmation != "y":
        print("No scans were submitted.")
        return 0
    try:
        return run(base_url, email)
    except SafeApiError as exc:
        print(f"Scan verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
