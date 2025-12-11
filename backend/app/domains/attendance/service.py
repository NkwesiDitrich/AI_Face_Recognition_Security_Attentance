from typing import Dict, Any, List, Optional, Tuple
from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService
from app.domains.attendance.models import AttendanceLog
from app.domains.user.models import User
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
import numpy as np
from PIL import Image
import io
import cv2
import tempfile
import os

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
        """
        temp_path = None
        try:
            # ✅ FIXED: Proper image handling with error checking
            print(f"[DEBUG] Received image data of size: {len(image_data)} bytes")
            
            # 1. Validate image data
            if not image_data or len(image_data) == 0:
                print("[ERROR] Empty image data received")
                return {
                    "status": "error",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "Empty image data"
                }

            # 2. Create BytesIO object and reset pointer
            image_bytes = io.BytesIO(image_data)
            image_bytes.seek(0)  # ✅ CRITICAL: Reset pointer to start

            # 3. Try to open image with PIL
            try:
                image = Image.open(image_bytes)
                print(f"[DEBUG] Image opened successfully: {image.format}, {image.size}, {image.mode}")
            except Exception as e:
                print(f"[ERROR] Cannot open image with PIL: {e}")
                # Try to load as numpy array directly
                try:
                    nparr = np.frombuffer(image_data, np.uint8)
                    image_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if image_np is None:
                        raise ValueError("Failed to decode image with OpenCV")
                    image = Image.fromarray(cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB))
                    print(f"[DEBUG] Image decoded with OpenCV successfully")
                except Exception as e2:
                    print(f"[ERROR] Cannot decode image with OpenCV either: {e2}")
                    return {
                        "status": "error",
                        "encoding": None,
                        "liveness": "fail",
                        "message": f"Cannot decode image: {str(e)}"
                    }

            # 4. Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
                print(f"[DEBUG] Converted image to RGB")

            # 5. Save to temporary file
            # Use tempfile for cross-platform compatibility
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                temp_path = tmp_file.name
                image.save(temp_path, format='JPEG')
                print(f"[DEBUG] Image saved to: {temp_path}")

            # 6. DeepFace Analysis (Recognition + Emotion) ASYNCHRONOUSLY
            print("[DEBUG] Starting DeepFace analysis...")
            analysis_results = await run_in_threadpool(
                DeepFace.analyze,
                img_path=temp_path,
                actions=['emotion'],  # Start with just emotion for faster processing
                enforce_detection=False,
                detector_backend='opencv'
            )
            print(f"[DEBUG] DeepFace analysis complete: {analysis_results}")

            # 7. Check for Face Detection
            if not analysis_results or not isinstance(analysis_results, list) or len(analysis_results) == 0:
                print("[ERROR] No face detected in analysis")
                return {
                    "status": "no_face",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "No face detected."
                }

            # Assuming one face is detected
            face_result = analysis_results[0]

            # 8. Liveness Check 1: Emotion
            dominant_emotion = face_result.get('dominant_emotion', 'neutral')
            print(f"[DEBUG] Dominant emotion: {dominant_emotion}")
            
            # Accept neutral, happy, and surprise as valid for liveness
            liveness_emotion_status = "pass" if dominant_emotion in ['happy', 'surprise', 'neutral'] else "fail"

            # 9. Liveness Check 2: Blinking (Placeholder for now)
            liveness_blinking_status = "pass"  # Assume pass for now

            # 10. Extract Encoding (Separate call for encoding)
            print("[DEBUG] Extracting face encoding...")
            embedding_objs = await run_in_threadpool(
                DeepFace.represent,
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=False
            )
            
            encoding = None
            if embedding_objs and len(embedding_objs) > 0:
                encoding = embedding_objs[0]['embedding']
                print(f"[DEBUG] Encoding extracted successfully: length={len(encoding)}")
            else:
                print("[ERROR] No encoding extracted")
                return {
                    "status": "error",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "Failed to extract face encoding"
                }

            liveness_status = "pass" if liveness_emotion_status == "pass" and liveness_blinking_status == "pass" else "fail"

            return {
                "status": "face_detected",
                "encoding": encoding,
                "liveness": liveness_status,
                "emotion": dominant_emotion,
                "message": f"Emotion: {dominant_emotion}. Liveness: {liveness_status.upper()}"
            }

        except Exception as e:
            print(f"[ERROR] _extract_encoding_and_liveness(): {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "encoding": None,
                "liveness": "fail",
                "message": f"Server Error: {str(e)}"
            }
        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"[DEBUG] Cleaned up temp file: {temp_path}")
                except Exception as e:
                    print(f"[ERROR] Failed to clean up temp file: {e}")

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