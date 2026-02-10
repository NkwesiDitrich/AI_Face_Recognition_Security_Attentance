# AI Face Attendance Security System

A multi-client attendance system with a FastAPI backend, admin dashboard, user portal, and Flutter mobile app.

## Quick setup (local)

1) Backend
   - `cd backend`
   - `pip install -r requirements.txt`
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

2) Admin web dashboard
   - `cd admin-web`
   - `npm install`
   - Set `VITE_API_URL` in `admin-web/.env` to `http://localhost:8000`
   - `npm run dev`

3) User web
   - `cd user-web`
   - `npm install`
   - Set `VITE_API_URL` in `user-web/.env` to `http://localhost:8000`
   - `npm run dev`

4) Mobile app (optional)
   - `cd frontend`
   - `flutter run --dart-define=API_BASE_URL=http://localhost:8000`

## Default demo credentials

- Admin dashboard
  - Email: `hackergeek55@gmail.com`
  - Password: `12345678`
- User web
  - Access code: `1507`

## Notes

- One backend serves both web clients.
- For deployment steps, see `DEPLOYMENT.md`.
