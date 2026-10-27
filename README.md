# PhishShift — Message Risk Scanner

PhishShift is a local phishing-message risk scanner built with FastAPI,
scikit-learn, React, Vite, TypeScript, and MariaDB. It provides account-based
message scanning, private scan history, model explanations, and held-out model
evaluation results.

The classifier is a TF-IDF + Logistic Regression baseline. Its outputs are
advisory probabilities, not guarantees. Do not submit passwords, confidential
communications, or sensitive personal information. Submitted scan text is
stored in the configured database.

## Local setup

1. Start MariaDB in XAMPP and create/select the existing `phishshift_db`
   database. Do not expose the database port publicly.
2. Copy `backend/.env.example` to `backend/.env` and privately configure the
   local database credentials and a random `SESSION_SECRET`. Never commit
   `backend/.env`.
3. Install backend requirements into a Python virtual environment:

   ```powershell
   Set-Location E:\PhishShift\backend
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Apply the safe, additive database migrations and initialize missing tables:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.init_db
   .\.venv\Scripts\python.exe -m scripts.migrate_auth
   .\.venv\Scripts\python.exe -m scripts.migrate_project_metadata
   ```

5. From `E:\PhishShift`, train the model. The script downloads the documented
   dataset, verifies its checksum, trains reproducibly, saves the local model
   artifact, and writes the evaluation report:

   ```powershell
   .\backend\.venv\Scripts\python.exe .\backend\scripts\train_model.py
   ```

6. Start the API and frontend in separate PowerShell windows:

   ```powershell
   Set-Location E:\PhishShift\backend
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
   ```

   ```powershell
   Set-Location E:\PhishShift\frontend
   npm ci
   npm run dev
   ```

7. Open `http://127.0.0.1:5173`. Create an account and use the authenticated
   dashboard to scan messages and view history.

See [backend/DATABASE.md](backend/DATABASE.md) for database configuration and
migrations, [backend/ML_BACKEND.md](backend/ML_BACKEND.md) for model and API
details, and [data/README.md](data/README.md) for dataset provenance and
training notes.

## Validation

```powershell
Set-Location E:\PhishShift
.\backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
Set-Location E:\PhishShift\frontend
npm ci
npm run build
npm audit
```

The local dataset CSV, trained model artifact, environment files, virtual
environments, frontend dependencies, and build output are intentionally
excluded from Git. Generate the dataset/model locally by following the
documented training steps.
