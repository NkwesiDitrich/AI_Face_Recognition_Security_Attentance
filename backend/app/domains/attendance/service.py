# backend/app/domains/attendance/service.py

from typing import Dict, Any, Optional, Tuple
from fastapi.concurrency import run_in_threadpool
from app.domains.attendance.repository import AttendanceRepository
from app.domains.attendance.models import AttendanceLog
from app.domains.user.service import UserService
from app.domains.user.models import User
from PIL import Image
import numpy as np
import io
import cv2
import time
from deepface import DeepFace


# -------------------------
# Configuration
# -------------------------
VERIFICATION_THRESHOLD = 0.6     # Same threshold as UserService

# Liveness placeholder thresholds
EYE_AR_THRESH = 0.3
EYE_AR_CONSEC_FRAMES = 3


class AttendanceService:

    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service

    # ----------------------------------------------------------------------
    # Helper function: Extract encoding + liveness
    # ----------------------------------------------------------------------
    async def _extract_encoding_and_liveness(self, image_data: bytes) -> Dict[str, Any]:
        """Extract face encoding + calculate liveness (emotion + blinking)."""
        try:
            # ---- 1. Load Image ----
            image = Image.open(io.BytesIO(image_data))
            if image.mode != "RGB":
                image = image.convert("RGB")

            temp_path = "/tmp/temp_attendance_frame.jpg"
            image.save(temp_path)

            # ---- 2. DeepFace Analysis ----
            analysis_results = await run_in_threadpool(
                DeepFace.analyze,
                img_path=temp_path,
                actions=["emotion"],
                enforce_detection=False,
                detector_backend="opencv"
            )

            # Check detection
            if not isinstance(analysis_results, list) or len(analysis_results) == 0:
                return {
                    "status": "no_face",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "No face detected."
                }

            face_result = analysis_results[0]

            # ---- 3. Liveness via Emotion ---
            dominant_emotion = face_result.get("dominant_emotion", "neutral")
            liveness_emotion = "pass" if dominant_emotion in ["happy", "surprise"] else "fail"

            # ---- 4. Placeholder blinking check ----
            liveness_blink = "pass"

            # ---- 5. Face Encoding ----
            encoding_objs = await run_in_threadpool(
                DeepFace.represent,
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=False
            )

            encoding = encoding_objs[0]["embedding"] if encoding_objs else None

            liveness_status = (
                "pass" if liveness_emotion == "pass" and liveness_blink == "pass" else "fail"
            )

            return {
                "status": "face_detected",
                "encoding": encoding,
                "liveness": liveness_status,
                "emotion": dominant_emotion,
                "message": f"Emotion: {dominant_emotion}. Liveness: {liveness_status.upper()}"
            }

        except Exception as e:
            print(f"[ERROR] _extract_encoding_and_liveness(): {e}")
            return {
                "status": "error",
                "encoding": None,
                "liveness": "fail",
                "message": f"Server Error: {e}"
            }

    # ----------------------------------------------------------------------
    # Main Recognition + Logging
    # ----------------------------------------------------------------------
    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """Liveness -> Recognition -> Log Attendance."""
        analysis = await self._extract_encoding_and_liveness(image_data)

        # No face detected
        if analysis["status"] != "face_detected":
            return {
                "status": "fail",
                "message": analysis["message"],
                "user": None
            }

        # Liveness failed
        if analysis["liveness"] == "fail":
            return {
                "status": "fail",
                "message": f"Liveness Failed. Emotion: {analysis['emotion']}",
                "user": None
            }

        # ---------------------------
        # Face Recognition
        # ---------------------------
        target_encoding_np = np.array(analysis["encoding"])
        known_users = await self.user_service.user_repo.get_all_encodings()

        best_match: Optional[Tuple[User, float]] = None

        for user in known_users:
            if not user.face_encodings:
                continue

            known_enc_np = np.array(user.face_encodings)
            distance = np.linalg.norm(target_encoding_np - known_enc_np)

            if distance < VERIFICATION_THRESHOLD:
                if best_match is None or distance < best_match[1]:
                    best_match = (user, distance)

        if best_match:
            matched_user = best_match[0]

            # ---------------------------
            # Store attendance log
            # ---------------------------
            log_entry = AttendanceLog(
                user_id=str(matched_user.id),
                event_type="check_in",
                liveness_status="pass"
            )
            await self.attendance_repo.add_log(log_entry)

            return {
                "status": "success",
                "user": matched_user.name,
                "message": f"Welcome, {matched_user.name}! Check-in Successful."
            }

        # No match
        return {
            "status": "fail",
            "user": None,
            "message": "Recognition Failed. User not found."
        }
