# Admin Backend Setup (Same Virtual Environment)

## Important: Use Your Existing Virtual Environment

The admin backend is **part of the same FastAPI application** as your face recognition system. 
You should use the **same virtual environment** where you already have:
- FastAPI
- Motor (MongoDB)
- DeepFace
- OpenCV
- etc.

## Setup Steps

### 1. Activate Your Existing Virtual Environment

```bash
# Navigate to your project root
cd "C:\Users\eser\Documents\Year 3\Design project\ai-face-attendance_Security-system"

# Activate your existing venv (adjust path if different)
# Example for Windows:
.\venv\Scripts\activate

# Or if your venv is named differently:
.\env\Scripts\activate
```

### 2. Install New Admin Dependencies

```bash
cd backend
pip install python-jose[cryptography] bcrypt
```

Or install all requirements (including new ones):

```bash
pip install -r requirements.txt
```

### 3. Create First Admin User

```bash
python scripts/create_admin.py
```

Follow the prompts to create your admin account.

### 4. Start the Backend Server (Same as Before)

```bash
# From the backend directory
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**That's it!** The same server now includes:
- ✅ Existing face recognition endpoints (`/api/v1/user/*`, `/api/v1/attendance/*`)
- ✅ New admin endpoints (`/api/v1/admin/*`)

## Verify It's Working

1. **Check existing endpoints still work:**
   - Face enrollment: `POST http://localhost:8000/api/v1/user/enroll`
   - Attendance WebSocket: `ws://localhost:8000/api/v1/ws/attendance`

2. **Check new admin endpoints:**
   - Admin login: `POST http://localhost:8000/api/v1/admin/auth/login`
   - API docs: `http://localhost:8000/docs` (should show all routes including admin)

## Notes

- **Same database**: Admin data goes to the same MongoDB database (`face_attendance_db`)
- **Same server**: One FastAPI app handles everything
- **Same venv**: All dependencies in one place
- **No separate server needed**: Everything runs together
