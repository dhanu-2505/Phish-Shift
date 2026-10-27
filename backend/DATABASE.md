# Local database setup

PhishShift connects to the existing `phishshift_db` database on
`127.0.0.1:3306`. It does not create the database, drop tables, or alter tables
that already exist. The initializer checks the selected database and creates
only missing tables.

## Configure credentials privately

Edit `backend/.env` on this computer and set `DB_USER` and `DB_PASSWORD` to the
credentials you use for your local MariaDB account. Do not paste the password
into source files, terminal commands, screenshots, or chat. If the account
intentionally has no password, leave `DB_PASSWORD` empty and explicitly set
`DB_ALLOW_EMPTY_PASSWORD=true`.

The `.env` file is excluded by `backend/.gitignore`. Keep the local database
private and do not expose its port publicly.

## Initialize the missing tables

Start MySQL in the XAMPP Control Panel, then open PowerShell and run:

```powershell
Set-Location E:\PhishShift\backend
.\.venv\Scripts\python.exe .\scripts\init_db.py
```

The script connects to the configured database, confirms that
`phishshift_db` is selected, inspects its tables, and creates only missing
`scan_results`, `model_evaluations`, and `model_versions` tables.

## Scan message privacy

`scan_results.message_text` stores the submitted message so local scan history
can display what was analyzed. Messages may contain sensitive information.
Use only a private local demo database, restrict access to the database, and
avoid scanning real personal or confidential messages. No message contents are
written to application logs by this database layer.

## Database health endpoint

From `backend`, run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The local API uses port `8765`, because port `8000` is occupied on this
computer:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/health/db`. The endpoint returns only whether the
connection succeeded; it does not return database credentials.

## Authentication migration

After configuring the new authentication settings in `backend/.env`, run:

```powershell
Set-Location E:\PhishShift\backend
.\.venv\Scripts\python.exe -m scripts.migrate_auth
```

This idempotent migration creates the `users` and `auth_sessions` tables and
adds a nullable `scan_results.user_id` column, index, and foreign key if
missing. Existing scans remain unowned (`user_id IS NULL`); they are not
assigned to newly registered users. The migration does not drop or reset
tables or rows.
