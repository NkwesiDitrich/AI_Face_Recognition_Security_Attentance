# AI Face Attendance System — Deployment Guide

This guide covers **free-tier** deployment for development and demo purposes. No paid cloud or GPU resources required.

---

## Recommended Free Stack

| Component    | Service              | Notes                                          |
|-------------|----------------------|------------------------------------------------|
| Backend     | Render Free Tier     | FastAPI + AI model. Free tier sleeps after inactivity. |
| Database    | MongoDB Atlas Free   | 512 MB storage, cloud-hosted, works from anywhere.    |
| Admin Web   | Vercel Free          | React admin dashboard. SSL included.           |
| User Web    | Vercel Free          | React user portal. SSL included.               |
| Mobile App  | Flutter debug/APK    | Connect to deployed backend. No store publish needed. |

---

## 1. MongoDB Atlas (Production Database)

### 1.1 Create cluster

1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
2. Sign up or log in.
3. Create a **free M0** cluster (e.g. AWS, region nearest to you).
4. Create a database user (save username and password).
5. Add IP access: **0.0.0.0/0** (for cloud backends) or restrict to your Render IP later.
6. Click **Connect** → **Connect your application**.
7. Copy the connection string, e.g.:
   ```
   mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
8. Add your database name:
   ```
   mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/face_attendance_db?retryWrites=true&w=majority
   ```

### 1.2 Env variable for backend

Use this as `MONGO_URI` in the backend:

```
MONGO_URI=mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/face_attendance_db?retryWrites=true&w=majority
DATABASE_NAME=face_attendance_db
```

---

## 2. Backend (Render)

### 2.1 Prepare backend

1. Push backend code to GitHub (or use the repo root if it’s a monorepo).
2. Ensure `backend/` contains:
   - `requirements.txt`
   - `app/main.py` (or correct entry point)
   - `.python-version` (optional; use `3.11` for TensorFlow/DeepFace compatibility)

### 2.2 Deploy on Render

1. Go to [Render](https://render.com) and sign up (GitHub login).
2. **New** → **Web Service**.
3. Connect your GitHub repo.
4. Set:
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables:
   - `MONGO_URI` — Atlas connection string
   - `DATABASE_NAME` — `face_attendance_db`
   - `CORS_ORIGINS` — comma-separated frontend URLs, e.g.:
     ```
     https://admin-your-app.vercel.app,https://user-your-app.vercel.app
     ```
6. Deploy and wait. Your backend URL will look like: `https://your-app.onrender.com`.

**Note:** Free tier services sleep after ~15 minutes of inactivity. First request can take ~30 seconds.

**Important:** Use `backend/requirements.txt` (not venv-generated). The project `requirements.txt` includes `tf-keras` and `opencv-python-headless` for Render compatibility. If you see `ModuleNotFoundError: No module named 'tf_keras'`, ensure `tf-keras` is in requirements and redeploy.

---

## 3. Admin Web (Vercel)

### 3.1 Deploy

1. Go to [Vercel](https://vercel.com) and sign up (GitHub).
2. **Add New** → **Project** → import your repo.
3. Set:
   - **Root Directory**: `admin-web`
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Add environment variable:
   - `VITE_API_URL` — e.g. `https://your-backend.onrender.com`
5. Deploy. Admin web will be at `https://your-admin.vercel.app`.

---

## 4. User Web (Vercel)

### 4.1 Deploy

1. In Vercel, create another project for `user-web`.
2. Set:
   - **Root Directory**: `user-web`
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Add environment variable:
   - `VITE_API_URL` — e.g. `https://your-backend.onrender.com`
4. Deploy.

---

## 5. Flutter Mobile App

### 5.1 Point app to backend

Use `--dart-define` so the app uses the deployed backend:

**Run (debug):**

```bash
cd frontend
flutter run --dart-define=API_BASE_URL=https://your-backend.onrender.com
```

**Build APK (testing/demo):**

```bash
flutter build apk --dart-define=API_BASE_URL=https://your-backend.onrender.com
```

APK output: `build/app/outputs/flutter-apk/app-release.apk`.

**iOS (simulator):**

```bash
flutter run -d "iPhone" --dart-define=API_BASE_URL=https://your-backend.onrender.com
```

### 5.2 Local / Ngrok (for local backend)

```bash
# Backend uses HTTPS via Ngrok
flutter run --dart-define=API_BASE_URL=https://xxxx.ngrok.io
```

---

## 6. Environment Variables Summary

### Backend (Render)

| Variable       | Required | Example |
|----------------|----------|---------|
| `MONGO_URI`    | Yes      | `mongodb+srv://user:pass@cluster.mongodb.net/face_attendance_db?...` |
| `DATABASE_NAME`| No       | `face_attendance_db` (default) |
| `CORS_ORIGINS` | Yes (prod) | `https://admin.vercel.app,https://user.vercel.app` |

### Admin Web (Vercel)

| Variable       | Required | Example |
|----------------|----------|---------|
| `VITE_API_URL` | Yes      | `https://your-backend.onrender.com` |

### User Web (Vercel)

| Variable       | Required | Example |
|----------------|----------|---------|
| `VITE_API_URL` | Yes      | `https://your-backend.onrender.com` |

### Flutter

| Build arg       | Example |
|-----------------|---------|
| `API_BASE_URL`  | `https://your-backend.onrender.com` |

---

## 7. Local Demo with Ngrok

To demo without deploying the backend:

1. Start backend locally:

   ```bash
   cd backend
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. Expose it with Ngrok:

   ```bash
   ngrok http 8000
   ```

3. Use the Ngrok URL (e.g. `https://abc123.ngrok.io`) as:
   - `VITE_API_URL` for admin/user web
   - `API_BASE_URL` for Flutter

**Note:** Free Ngrok URLs change on restart. Use the current URL each time.

---

## 8. First-Time Setup After Deploy

1. Create an admin user:

   ```bash
   cd backend
   python scripts/create_admin.py
   ```

   For production, run this locally with `MONGO_URI` set to your Atlas URI, or run it in a Render shell if available.

2. Enroll users from the admin web or Flutter enrollment screen.
3. Test attendance flow (face recognition + liveness).

---

## 9. AI Model on Free Tier

The app uses **DeepFace** with **ArcFace**. Free-tier servers have limited RAM/CPU:

- Render free: ~512 MB RAM — ArcFace may be slow or fail.
- For a lighter setup, you can switch to a smaller model (e.g. Facenet) in `backend/app/domains/attendance/service.py` by changing `MODEL_NAME` and testing.

---

## 10. Troubleshooting

| Issue | Check |
|-------|--------|
| CORS errors | `CORS_ORIGINS` includes your Vercel frontend URLs (with `https://`, no trailing slash). |
| MongoDB connection fails | Atlas IP allowlist includes `0.0.0.0/0` or Render IPs; credentials in `MONGO_URI` are correct. |
| Slow first request | Render free tier cold start (15–30 s) is normal. |
| WebSocket fails | Backend and frontend both use `wss://` when deployed (HTTPS). |
