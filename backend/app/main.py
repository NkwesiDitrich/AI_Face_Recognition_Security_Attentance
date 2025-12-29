# backend/app/main.py

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
import asyncio # <-- NEW IMPORT for the fix
from app.core.database import connect_to_mongo, close_mongo_connection
from app.core.ai_model import load_ai_models

# Routers (uncommented)
from app.api.v1.user import router as user_router
from app.api.v1.attendance import router as attendance_router



app = FastAPI(
    title="AI Face Attendance System (DDD)",
    version="1.0.0",
)

# ----------------------------
# Application Start & Shutdown
# ----------------------------

@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    # FINAL FIX: Use asyncio.to_thread to reliably run the synchronous DeepFace loading
    # This prevents the Uvicorn event loop from being blocked and prematurely cancelled.
    await asyncio.to_thread(load_ai_models)

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

# ----------------------------
# Include Router Endpoints
# ----------------------------
app.include_router(user_router, tags=["User"], prefix="/api/v1")
app.include_router(attendance_router, tags=["Attendance"], prefix="/api/v1")

# ----------------------------
# Root Check
# ----------------------------
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "AI Face Attendance API is running"}
