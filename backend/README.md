# Backend (FastAPI sample)

This folder contains a minimal FastAPI app.

Quick start (PowerShell):

1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Run (from `backend/` directory)

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ and http://127.0.0.1:8000/docs
