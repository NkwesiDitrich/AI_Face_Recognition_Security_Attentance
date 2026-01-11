# Troubleshooting Guide

## Server Startup Issues

### "MongoDB connection closed" Error

**This is NORMAL!** This message appears when you stop the server (Ctrl+C). It's just the shutdown handler cleaning up.

### Server Not Starting

If the server crashes during startup, check:

1. **Is MongoDB Running?**
   ```bash
   # On Windows, check if MongoDB service is running:
   # Open Services (services.msc) and look for "MongoDB"
   
   # Or start MongoDB manually:
   mongod
   ```

2. **Check Startup Messages**
   Look for these messages when starting:
   ```
   Connecting to MongoDB...
   Successfully connected to MongoDB!
   Loading AI Models...
   All DeepFace models configured successfully.
   Application startup complete.
   Uvicorn running on http://0.0.0.0:8000
   ```

3. **Common Issues**

   **MongoDB Not Running:**
   - Error: "Could not connect to MongoDB"
   - Solution: Start MongoDB service or run `mongod`

   **Port Already in Use:**
   - Error: "Address already in use"
   - Solution: Stop other processes on port 8000, or use a different port

   **AI Model Loading Takes Time:**
   - First startup can take 1-2 minutes to download models
   - This is normal - wait for "All DeepFace models configured successfully."

### Long Startup Time

**Normal:** First startup can take 1-2 minutes because:
- DeepFace downloads AI models (Emotion, ArcFace) on first use
- These models are several hundred MB

**Subsequent startups:** Should be much faster (10-20 seconds)

## Testing Server Status

1. **Check if server is running:**
   ```bash
   curl http://localhost:8000
   # Should return: {"message": "AI Face Attendance API is running"}
   ```

2. **Check MongoDB connection:**
   ```bash
   # The server will print connection status on startup
   # Look for: "Successfully connected to MongoDB!"
   ```

3. **Check API docs:**
   Open in browser: `http://localhost:8000/docs`
   - Should show Swagger UI with all endpoints

## Admin Login Issues

### "Connection timeout" or "Network Error"

1. **Backend not running:**
   - Start backend: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
   - Wait for "Application startup complete"

2. **CORS issues:**
   - CORS is configured in `backend/app/main.py`
   - Make sure your frontend URL is in `allow_origins` list

3. **Wrong API URL:**
   - Check `admin-web/src/lib/api.ts`
   - Should be: `http://localhost:8000`

### "Invalid email or password"

1. **Admin user exists?**
   - Run: `python scripts/create_admin.py`
   - Create admin with correct credentials

2. **Backend logs:**
   - Check backend terminal for error messages
   - Look for authentication errors

## Quick Health Check

Run these commands to verify everything is working:

```bash
# 1. Start MongoDB (if not running)
# Windows: Start MongoDB service
# Or: mongod

# 2. Start backend
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. In another terminal, test the API
curl http://localhost:8000

# 4. Check API docs
# Open: http://localhost:8000/docs

# 5. Start admin web
cd admin-web
npm run dev

# 6. Test admin login
# Open: http://localhost:3000 (or port shown)
```

If all steps work, your system is configured correctly! ✅
