# backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from app.core.database import connect_to_mongo, close_mongo_connection
from app.core.ai_model import load_ai_models

# Routers (uncommented)
from app.api.v1.user import router as user_router
from app.api.v1.attendance import router as attendance_router
from app.api.v1.admin import router as admin_router
from app.api.v1.user_portal import router as user_portal_router


# ----------------------------
# Application Lifespan Management
# ----------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    # Startup
    try:
        await connect_to_mongo()
        # Use asyncio.to_thread to reliably run the synchronous DeepFace loading
        # This prevents the Uvicorn event loop from being blocked
        await asyncio.to_thread(load_ai_models)
        print("✅ Application startup complete.")
    except Exception as e:
        print(f"❌ Startup error: {e}")
        raise
    
    try:
        yield  # Application runs here
    except asyncio.CancelledError:
        # Handle cancellation during reload gracefully
        print("⚠️ Application reload detected, shutting down gracefully...")
        # Don't re-raise - allow cleanup to proceed
    finally:
        # Shutdown - always runs, even if cancelled
        try:
            # Close MongoDB connection (non-blocking, quick operation)
            await close_mongo_connection()
            print("✅ Application shutdown complete.")
        except asyncio.CancelledError:
            # Ignore cancellation errors during reload/shutdown - they're expected
            # This happens when uvicorn reloads and cancels the lifespan
            pass
        except Exception as e:
            # Log other errors but don't raise - shutdown should be graceful
            print(f"⚠️ Shutdown error (non-critical): {e}")


app = FastAPI(
    title="AI Face Attendance System (DDD)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration - Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # admin-web default port
        "http://localhost:3001",  # user-web port
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
        # Add your mobile app URL if needed
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Include Router Endpoints
# ----------------------------
app.include_router(user_router, tags=["User"], prefix="/api/v1")
app.include_router(attendance_router, tags=["Attendance"], prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(user_portal_router, prefix="/api/v1")

# ----------------------------
# Root Check
# ----------------------------
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "AI Face Attendance API is running"}
