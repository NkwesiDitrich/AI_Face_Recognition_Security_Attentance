# Face Attendance Admin Dashboard

Professional admin dashboard for monitoring and managing the AI Face Attendance System.

## 🚀 Features

### Level 1 - Foundation (Current Implementation)

- ✅ **Admin Authentication & Authorization**
  - Secure JWT-based login
  - Role-based access control (Super Admin, Admin, Viewer)
  - Session management
  - Logout functionality

- ✅ **Users Management**
  - List all registered users
  - Search by name or employee ID
  - Filter by status (active/inactive) and role
  - View user profiles and details
  - View enrollment status and metadata
  - Activate/deactivate users
  - Delete users (with confirmation)

- ✅ **Attendance Records (Read-Only)**
  - View all attendance records
  - Filter by date range, user, and status
  - Search attendance records
  - View detailed event information
  - Export to CSV (UI ready)

## 🛠️ Technology Stack

- **React 18** with TypeScript
- **Vite** for fast development and building
- **React Router** for navigation
- **Zustand** for state management
- **TanStack Query** (React Query) for data fetching
- **Tailwind CSS** for styling
- **Lucide React** for icons
- **Axios** for API communication

## 📦 Installation

1. Navigate to the admin-web directory:
```bash
cd admin-web
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env` file from the example:
```bash
cp .env.example .env
```

4. Update the `.env` file with your backend API URL:
```
VITE_API_URL=http://localhost:8000
```

## 🏃 Development

Start the development server:
```bash
npm run dev
```

The app will be available at `http://localhost:3000`

## 🏗️ Build

Build for production:
```bash
npm run build
```

The production build will be in the `dist` directory.

## 📁 Project Structure

```
admin-web/
├── src/
│   ├── components/        # Reusable components
│   │   ├── Layout.tsx
│   │   └── ProtectedRoute.tsx
│   ├── lib/              # Utility libraries
│   │   └── api.ts        # API client
│   ├── pages/            # Page components
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Users.tsx
│   │   ├── UserDetail.tsx
│   │   └── Attendance.tsx
│   ├── store/            # State management
│   │   └── authStore.ts
│   ├── types/            # TypeScript types
│   │   └── index.ts
│   ├── App.tsx           # Main app component
│   ├── main.tsx          # Entry point
│   └── index.css         # Global styles
├── public/               # Static assets
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## 🔐 Authentication

The app uses JWT tokens stored in localStorage. Tokens are automatically included in API requests via axios interceptors.

### Role Hierarchy

- **Super Admin** (level 3): Full system access
- **Admin** (level 2): Operational access
- **Viewer** (level 1): Read-only access

## 🌐 API Integration

All API calls go through the centralized API client (`src/lib/api.ts`). The base URL is configured via the `VITE_API_URL` environment variable.

### Required Backend Endpoints

The admin dashboard expects these backend endpoints:

#### Authentication
- `POST /api/v1/admin/auth/login`
- `POST /api/v1/admin/auth/logout`
- `GET /api/v1/admin/auth/me`

#### Users
- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/:id`
- `POST /api/v1/admin/users`
- `PUT /api/v1/admin/users/:id`
- `DELETE /api/v1/admin/users/:id`
- `GET /api/v1/admin/users/:id/enrollment`
- `POST /api/v1/admin/users/:id/re-enroll`
- `POST /api/v1/admin/users/bulk-import`

#### Attendance
- `GET /api/v1/admin/attendance`
- `GET /api/v1/admin/attendance/:id`

#### Logs
- `GET /api/v1/admin/logs/enrollment`
- `GET /api/v1/admin/logs/recognition`
- `GET /api/v1/admin/logs/liveness`
- `GET /api/v1/admin/logs/admin-actions`

**Note**: These backend endpoints need to be implemented in your Python FastAPI backend.

## 🎨 UI Components

The app uses Tailwind CSS for styling with custom component classes:

- `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`
- `.input`
- `.card`
- `.table`, `.table-container`
- `.badge`, `.badge-success`, `.badge-warning`, `.badge-danger`, `.badge-info`

## 🚧 Future Enhancements (Levels 2-4)

- Real-time attendance feed (WebSocket)
- Notifications & alerts
- Devices & active sessions monitoring
- Manual attendance override
- Reports & exports
- System settings
- Admin messaging & broadcasts

## 📝 Notes

- The dashboard currently requires backend endpoints to be implemented
- All admin actions are logged (when backend supports it)
- The UI is responsive and mobile-friendly
- All routes are protected by authentication
- Role-based permissions are enforced

## 🤝 Contributing

This is part of the AI Face Attendance System project. Follow the main project guidelines for contributions.

## 📄 License

Same as the main project license.