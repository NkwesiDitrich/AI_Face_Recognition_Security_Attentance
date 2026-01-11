# Admin Dashboard Setup Guide

## Level 1 Implementation - Complete ✅

All Level 1 features have been fully implemented:

### ✅ 1. Admin Authentication & Authorization
- Admin login (email + password)
- JWT-based secure sessions
- Role-based access control (super_admin, admin, viewer)
- Get current admin info
- Logout functionality

### ✅ 2. Users Management
- List all users with search and filtering
- View user details
- Create new users
- Update user information
- Delete users (with confirmation)
- View enrollment status
- Force re-enrollment
- Bulk import (placeholder for future)

### ✅ 3. Attendance Records (Read-Only)
- View all attendance records
- Filter by date range, user, status
- View detailed attendance record
- Pagination support

### ✅ 4. Logs & Security Audit
- Enrollment logs
- Recognition logs
- Liveness logs
- Admin action logs
- Filtering by user/session/admin

## Backend Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Create First Admin User

```bash
python scripts/create_admin.py
```

Follow the prompts to create your first admin account.

### 3. Start Backend Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup

### 1. Install Dependencies

```bash
cd admin-web
npm install
```

### 2. Configure API URL

Create a `.env` file in `admin-web/`:

```env
VITE_API_URL=http://localhost:8000
```

Or update `admin-web/src/lib/api.ts` if needed.

### 3. Start Development Server

```bash
npm run dev
```

The admin dashboard will be available at `http://localhost:5173`

## API Endpoints

All endpoints are prefixed with `/api/v1/admin`

### Authentication
- `POST /auth/login` - Admin login
- `POST /auth/logout` - Admin logout
- `GET /auth/me` - Get current admin

### Users
- `GET /users` - List users (with search/filter)
- `GET /users/{id}` - Get user details
- `POST /users` - Create user
- `PUT /users/{id}` - Update user
- `DELETE /users/{id}` - Delete user
- `GET /users/{id}/enrollment` - Get enrollment status
- `POST /users/{id}/re-enroll` - Force re-enrollment

### Attendance
- `GET /attendance` - List attendance records
- `GET /attendance/{id}` - Get attendance record

### Logs
- `GET /logs/enrollment` - Enrollment logs
- `GET /logs/recognition` - Recognition logs
- `GET /logs/liveness` - Liveness logs
- `GET /logs/admin-actions` - Admin action logs

## Security Notes

- JWT tokens expire after 30 days
- All admin actions are logged
- Password hashing uses bcrypt
- Role-based access control enforced
- Change `SECRET_KEY` in production (backend/app/domains/admin/service.py)

## Next Steps (Level 2+)

- Dashboard overview with statistics
- Real-time attendance feed
- Notifications & alerts
- Devices & active sessions
- Manual attendance override
- Reports & exports
- System settings
- Admin messaging
