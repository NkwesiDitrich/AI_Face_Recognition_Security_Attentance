# Quick Start Guide

## 🚀 Running Your Application

### You Only Need ONE Backend Server!

The backend serves **both** the mobile app and admin web dashboard.

### Step 1: Start the Backend (Required)

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**This single backend server provides:**
- ✅ Mobile app API endpoints (`/api/v1/user/*`, `/api/v1/attendance/*`)
- ✅ Admin web dashboard API endpoints (`/api/v1/admin/*`)
- ✅ WebSocket endpoints for real-time attendance

### Step 2: Start Admin Web Dashboard (Optional)

Open a **new terminal** window:

```bash
cd admin-web
npm run dev
```

The admin dashboard will be available at `http://localhost:3000` (or the port shown in the terminal)

### Step 3: Use Mobile App

Point your mobile app to: `http://localhost:8000` (or your server IP if running on a device)

## 🔧 Troubleshooting

### "Request timeout" or "Connection refused" errors

**Problem**: Backend is not running or CORS is blocking requests

**Solution**: 
1. Make sure the backend is running (Step 1)
2. Check the terminal - you should see "Application startup complete"
3. Test by visiting `http://localhost:8000` in your browser - you should see: `{"message": "AI Face Attendance API is running"}`

### Admin login not working

1. Make sure backend is running
2. Check browser console (F12) for errors
3. Verify the backend URL in `admin-web/src/lib/api.ts` is `http://localhost:8000`
4. Check backend terminal for error messages

### CORS errors

The CORS middleware is now configured in `backend/app/main.py`. If you're still getting CORS errors:

1. Restart the backend server
2. Check that your frontend URL is in the `allow_origins` list
3. Clear browser cache and try again

## 📝 Summary

- **One backend** = Serves mobile app + admin web dashboard
- **Run backend first** = Always start the backend before using the admin web
- **Port 8000** = Backend API server
- **Port 3000/5173** = Admin web dashboard (development)

This is the **professional standard** - one API backend, multiple frontend clients! ✅
