# MediKiosk

A complete full-stack healthcare intake and clinical-assistance MVP.

## Modules
1. Patient registration
2. Patient interview
3. Document/evidence upload
4. AI-assisted analysis and red-flag detection
5. Clinical summary
6. Doctor review dashboard

## Stack
- Frontend: React + Vite
- Backend: FastAPI
- Database: SQLite
- File uploads: FastAPI UploadFile
- AI: deterministic local analysis fallback; no API key required

## Run

### Backend
cd backend
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

### Frontend
cd frontend
npm install
npm run dev

Open http://localhost:5173

The frontend expects the API at http://localhost:8000. Set VITE_API_URL if needed.
