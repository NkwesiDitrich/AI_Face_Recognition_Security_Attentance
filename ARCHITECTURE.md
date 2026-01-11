# Architecture Overview

## Backend Architecture

### Single Backend Server ✅ (Recommended Practice)

This project uses a **single FastAPI backend server** that serves all clients:

- ✅ **Mobile App** (Android/iOS)
- ✅ **Admin Web Dashboard**
- ✅ **Any future clients** (desktop apps, IoT devices, etc.)

**Why this is a professional best practice:**

1. **Single Source of Truth**: One API, one database, consistent business logic
2. **Easier Maintenance**: Update code in one place, not multiple backends
3. **Cost Effective**: One server to deploy, monitor, and scale
4. **Better Security**: One authentication system, one set of security policies
5. **Industry Standard**: Most modern applications use this pattern (REST API + multiple clients)

### How It Works

```
┌─────────────────┐         ┌──────────────────┐
│  Mobile App     │────────▶│                  │
│  (Android/iOS)  │         │                  │
└─────────────────┘         │   FastAPI        │
                            │   Backend        │
┌─────────────────┐         │   (Port 8000)    │
│  Admin Web      │────────▶│                  │
│  Dashboard      │         │                  │
└─────────────────┘         └──────────────────┘
                                    │
                                    ▼
                            ┌───────────────┐
                            │   MongoDB     │
                            │   Database    │
                            └───────────────┘
```

### API Routes Organization

The backend organizes routes by domain:

- `/api/v1/user/*` - User management (face enrollment, etc.)
- `/api/v1/attendance/*` - Attendance tracking
- `/api/v1/admin/*` - Admin dashboard endpoints
- `/api/v1/ws/*` - WebSocket endpoints

### Running the Backend

**Only ONE backend server needs to run:**

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

This single command starts the backend that serves:
- ✅ Mobile app requests
- ✅ Admin web dashboard requests
- ✅ All API endpoints

### Frontend Clients

Each client connects to the same backend:

1. **Mobile App**: Connects to `http://your-server:8000`
2. **Admin Web**: Connects to `http://localhost:8000` (development) or `http://your-server:8000` (production)

### Development Setup

1. **Start Backend** (once):
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Start Admin Web** (in a new terminal):
   ```bash
   cd admin-web
   npm run dev
   ```

3. **Mobile App**: Point to the same backend URL

### Production Deployment

In production, you typically:

1. Deploy the backend to a server (e.g., AWS, DigitalOcean, Heroku)
2. Configure CORS to allow your frontend domains
3. Update frontend `.env` files to point to the production backend URL
4. Deploy frontends separately (web app to Netlify/Vercel, mobile app to stores)

### Benefits of This Architecture

✅ **Scalability**: Scale one backend, all clients benefit  
✅ **Consistency**: Same data, same business rules for all clients  
✅ **Development Speed**: One codebase, faster iteration  
✅ **Testing**: Test once, works everywhere  
✅ **Security**: One security model to maintain  
✅ **Cost**: One server to pay for  

This is the **industry standard** approach used by companies like:
- GitHub (one API, web + mobile apps)
- Twitter (one API, web + mobile apps)
- Slack (one API, web + mobile + desktop apps)
