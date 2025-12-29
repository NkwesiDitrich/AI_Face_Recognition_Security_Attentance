# backend/app/domains/attendance/service.py

from typing import Dict, Any, Optional, List
import numpy as np
import cv2
import tempfile
import os
import asyncio
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace

from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService
from app.domains.attendance.models import AttendanceLog

class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        Phase 1: Real-time Face Recognition.
        Uses the same ArcFace logic as enrollment with relaxed fallback for video.
        """
        if self._processing_lock.locked():
            return {"status": "processing", "message": "Processing..."}

        async with self._processing_lock:
            try:
                # Use the search method that returns face detection status
                matched_user, face_detected = await self.user_service.search_user_with_info(image_data)
                
                if matched_user:
                    return {
                        "status": "success",
                        "message": "✔ Face recognized",
                        "user": matched_user.name,
                        "user_id": str(matched_user.id),
                        "face_detected": True
                    }

                if face_detected:
                    return {
                        "status": "fail",
                        "message": "Face not registered",
                        "face_detected": True
                    }

                return {
                    "status": "no_face",
                    "message": "Place your face inside the frame",
                    "face_detected": False
                }

            except Exception as e:
                print(f"DEBUG: Error in process_attendance_frame: {e}")
                return {"status": "error", "message": f"Server Error: {str(e)}"}

    async def record_attendance(self, user_id: str, liveness_status: str = "pass") -> Dict[str, Any]:
        """Phase 5: Final Recording."""
        log_data = AttendanceLog(user_id=user_id, event_type="check_in", liveness_status=liveness_status)
        await self.attendance_repo.add_log(log_data)
        return {"status": "recorded", "message": "Attendance recorded successfully"}