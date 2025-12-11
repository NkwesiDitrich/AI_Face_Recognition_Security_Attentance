# backend/app/domains/attendance/service.py

from typing import Dict, Any, List, Optional, Tuple
from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService
from app.domains.attendance.models import AttendanceLog
from app.domains.user.models import User
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
import numpy as np
import io
import cv2
import tempfile
import os
import time # For blinking detection

# DeepFace match threshold (same as user service)
VERIFICATION_THRESHOLD = 0.6

# --- Liveness Detection Constants ---
# Eye Aspect Ratio (EAR) thresholds for blinking
EYE_AR_THRESH = 0.3
EYE_AR_CONSEC_FRAMES = 3


class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service

    async def _extract_encoding_and_liveness(self, image_data: bytes) -> Dict[str, Any]:
        """
        Extracts face encoding and performs Liveness checks (Emotion, Blinking).
        Uses the robust OpenCV/Numpy decoding method from the user service.
        """
        temp_path = None
        try:
            # 1. Convert bytes to NumPy array
            nparr = np.frombuffer(image_data, np.uint8)

            # 2. Decode image using OpenCV
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                print("❌ OpenCV failed to decode image.")
                return {"status": "error", "encoding": None, "liveness": "fail", "message": "Failed to decode image."}

            # 3. Save to temp file (Windows & Linux compatible)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Write the image to the temp file
            success = cv2.imwrite(temp_path, img)
            if not success:
                print(f"❌ Failed to write image to {temp_path}")
                return {"status": "error", "encoding": None, "liveness": "fail", "message": "Failed to write image."}

            print(f"✅ Image saved to: {temp_path}")

            # 4. DeepFace Analysis (Recognition + Emotion) ASYNCHRONOUSLY
            analysis_results = await run_in_threadpool(
                DeepFace.analyze,
                img_path=temp_path,
                actions=['emotion'],
                enforce_detection=False,
                detector_backend='opencv'
            )
            
            # 5. Check for Face Detection
            if not analysis_results or not isinstance(analysis_results, list) or len(analysis_results) == 0:
                return {"status": "no_face", "encoding": None, "liveness": "fail", "message": "No face detected."}

            # Assuming one face is detected
            face_result = analysis_results[0]
            
            # 6. Liveness Check 1: Emotion
            dominant_emotion = face_result.get('dominant_emotion', 'neutral')
            # We allow neutral, happy, or surprise for a basic liveness check
            liveness_emotion_status = "pass" if dominant_emotion in ['happy', 'surprise', 'neutral'] else "fail"
            
            # 7. Liveness Check 2: Blinking (Placeholder for now)
            liveness_blinking_status = "pass"
            
            # 8. Extract Encoding (Separate call for encoding)
            embedding_objs = await run_in_threadpool(
                DeepFace.represent,
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=False
            )
            
            encoding = embedding_objs[0]['embedding'] if embedding_objs and len(embedding_objs) > 0 else None
            
            if encoding is None:
                return {"status": "error", "encoding": None, "liveness": "fail", "message": "Failed to extract face encoding."}

            liveness_status = "pass" if liveness_emotion_status == "pass" and liveness_blinking_status == "pass" else "fail"

            return {
                "status": "face_detected",
                "encoding": encoding,
                "liveness": liveness_status,
                "emotion": dominant_emotion,
                "message": f"Emotion: {dominant_emotion}. Liveness: {liveness_status.upper()}"
            }
            
        except Exception as e:
            print(f"Error in _extract_encoding_and_liveness: {e}")
            return {"status": "error", "encoding": None, "liveness": "fail", "message": f"Server Error: {e}"}
        
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"✅ Cleaned up temp file: {temp_path}")
                except Exception as e:
                    print(f"⚠️ Could not delete temp file: {e}")

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        Core logic for attendance: Liveness -> Recognition -> Logging.
        """
        print("[DEBUG] Processing attendance frame...")
        
        analysis = await self._extract_encoding_and_liveness(image_data)
        
        if analysis['status'] != 'face_detected':
            return {"message": analysis['message'], "user": None, "status": "fail"}

        if analysis['liveness'] == 'fail':
            return {
                "message": f"Liveness Check Failed. Detected Emotion: {analysis['emotion']}",
                "user": None,
                "status": "fail"
            }

        # 1. Recognition
        target_encoding_np = np.array(analysis['encoding'])
        known_users = await self.user_service.user_repo.get_all_encodings()
        
        best_match: Optional[Tuple[User, float]] = None
        
        for user in known_users:
            if not user.face_encodings:
                continue
            
            known_encoding_np = np.array(user.face_encodings)
            distance = np.linalg.norm(target_encoding_np - known_encoding_np)
            
            if distance < VERIFICATION_THRESHOLD:
                if best_match is None or distance < best_match[1]:
                    best_match = (user, distance)

        if best_match:
            matched_user = best_match[0]
            
            # 2. Logging
            log_data = AttendanceLog(
                user_id=str(matched_user.id),
                event_type="check_in",
                liveness_status="pass",
            )
            await self.attendance_repo.add_log(log_data)
            
            return {
                "message": f"Welcome, {matched_user.name}! Check-in Successful.",
                "user": matched_user.name,
                "status": "success"
            }

        return {
            "message": "Recognition Failed. User not found.",
            "user": None,
            "status": "fail"
        }
