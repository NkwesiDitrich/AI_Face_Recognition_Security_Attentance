from fastapi import APIRouter

# Create the FastAPI router instance
router = APIRouter()

# Placeholder route for testing
@router.get("/attendance/test", tags=["Attendance"])
async def test_attendance_router():
    return {"message": "Attendance router is working"}
