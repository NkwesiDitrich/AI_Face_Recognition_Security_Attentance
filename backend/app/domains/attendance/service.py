from typing import Dict, Any, Optional, Tuple, List
from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService
from app.domains.attendance.models import AttendanceLog
from app.domains.user.models import User
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
import numpy as np
import cv2
import tempfile
import os
import asyncio

# DeepFace match threshold
VERIFICATION_THRESHOLD = 0.6

class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    def _detect_face_with_coordinates(self, img_path: str) -> Dict[str, Any]:
        """
        Detect face and return bounding box coordinates for drawing green frame.
        """
        try:
            # Read image
            img = cv2.imread(img_path)
            if img is None:
                return {"detected": False, "coordinates": None, "error": "Failed to read image"}
            
            # Get image dimensions
            height, width = img.shape[:2]
            
            # Use DeepFace to detect faces
            try:
                detections = DeepFace.extract_faces(
                    img_path=img_path,
                    detector_backend='opencv',
                    enforce_detection=False
                )
                
                if not detections or len(detections) == 0:
                    return {
                        "detected": False,
                        "coordinates": None,
                        "message": "No face detected in frame"
                    }
                
                # Get the largest face (most likely the main subject)
                largest_face = max(detections, key=lambda x: x['facial_area']['w'] * x['facial_area']['h'])
                facial_area = largest_face['facial_area']
                
                # Extract coordinates
                x = facial_area['x']
                y = facial_area['y']
                w = facial_area['w']
                h = facial_area['h']
                
                # Ensure coordinates are within image bounds
                x = max(0, x)
                y = max(0, y)
                w = min(w, width - x)
                h = min(h, height - y)
                
                return {
                    "detected": True,
                    "coordinates": {
                        "x": int(x),
                        "y": int(y),
                        "width": int(w),
                        "height": int(h),
                        "x2": int(x + w),
                        "y2": int(y + h)
                    },
                    "message": "Face detected successfully"
                }
            except Exception as e:
                return {
                    "detected": False,
                    "coordinates": None,
                    "error": str(e)
                }
        except Exception as e:
            return {
                "detected": False,
                "coordinates": None,
                "error": str(e)
            }

    async def _extract_encoding_and_liveness(self, image_data: bytes) -> Dict[str, Any]:
        """
        Extracts face encoding and performs Liveness checks (Emotion).
        FIXED: Proper validation before accessing array indices.
        """
        temp_path = None
        try:
            # 1. Convert bytes to NumPy array and decode image using OpenCV
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                return {
                    "status": "error",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "Failed to decode image.",
                    "face_detected": False,
                    "coordinates": None
                }

            # 2. Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            success = cv2.imwrite(temp_path, img)
            if not success:
                return {
                    "status": "error",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "Failed to write image.",
                    "face_detected": False,
                    "coordinates": None
                }

            # 2.5. Detect face and get coordinates for green frame
            face_detection = await run_in_threadpool(
                self._detect_face_with_coordinates,
                temp_path
            )

            # 3. DeepFace Analysis (Emotion and Encoding)
            
            # 3a. Analyze for Emotion (Liveness Check)
            analysis_results = await run_in_threadpool(
                DeepFace.analyze,
                img_path=temp_path,
                actions=['emotion'],
                enforce_detection=False,
                detector_backend='opencv'
            )
            
            # ✅ FIX: Proper validation before accessing results
            if not analysis_results:
                return {
                    "status": "no_face",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "❌ No face detected. Please ensure your face is clearly visible in the camera.",
                    "face_detected": False,
                    "coordinates": None
                }
            
            # Handle both list and dict returns from DeepFace
            if isinstance(analysis_results, list):
                if len(analysis_results) == 0:
                    return {
                        "status": "no_face",
                        "encoding": None,
                        "liveness": "fail",
                        "message": "❌ No face detected. Please ensure your face is clearly visible in the camera.",
                        "face_detected": False,
                        "coordinates": None
                    }
                face_result = analysis_results[0]
            elif isinstance(analysis_results, dict):
                face_result = analysis_results
            else:
                return {
                    "status": "error",
                    "encoding": None,
                    "liveness": "fail",
                    "message": f"Unexpected response type from face analysis: {type(analysis_results)}",
                    "face_detected": False,
                    "coordinates": None
                }

            dominant_emotion = face_result.get('dominant_emotion', 'neutral')
            
            # RELAXED LIVENESS LOGIC: Only fail on clearly negative emotions
            negative_emotions = ['sad', 'angry', 'fear', 'disgust']
            liveness_emotion_status = "fail" if dominant_emotion in negative_emotions else "pass"
            
            # 3b. Extract Encoding for Recognition
            embedding_objs = await run_in_threadpool(
                DeepFace.represent,
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=False
            )
            
            # ✅ FIX: Proper validation for embedding results
            if not embedding_objs or len(embedding_objs) == 0:
                return {
                    "status": "error",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "Failed to extract face encoding. Face may not be clear enough.",
                    "face_detected": face_detection.get("detected", False),
                    "coordinates": face_detection.get("coordinates")
                }
            
            encoding = embedding_objs[0].get('embedding') if isinstance(embedding_objs[0], dict) else None
            
            if encoding is None:
                return {
                    "status": "error",
                    "encoding": None,
                    "liveness": "fail",
                    "message": "Failed to extract face encoding.",
                    "face_detected": face_detection.get("detected", False),
                    "coordinates": face_detection.get("coordinates")
                }

            liveness_status = liveness_emotion_status

            return {
                "status": "face_detected",
                "encoding": encoding,
                "liveness": liveness_status,
                "emotion": dominant_emotion,
                "message": f"✅ Face detected! Emotion: {dominant_emotion}",
                "face_detected": True,
                "coordinates": face_detection.get("coordinates")
            }
            
        except Exception as e:
            print(f"❌ Error in _extract_encoding_and_liveness: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "encoding": None,
                "liveness": "fail",
                "message": f"Server Error: {str(e)}",
                "face_detected": False,
                "coordinates": None
            }
        
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    print(f"⚠️ Could not delete temp file: {e}")

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        Core logic for attendance: Liveness -> Recognition -> Logging.
        Uses a lock to ensure only one frame is processed at a time.
        """
        # Check if a frame is already being processed
        if self._processing_lock.locked():
            return {
                "message": "Processing previous frame...",
                "user": None,
                "status": "processing",
                "face_detected": False,
                "coordinates": None
            }

        async with self._processing_lock:
            print("[DEBUG] Processing attendance frame...")
            
            analysis = await self._extract_encoding_and_liveness(image_data)
            
            # 1. Check for Face Detection / Decoding Errors
            if analysis['status'] != 'face_detected':
                return {
                    "message": analysis['message'],
                    "user": None,
                    "status": "fail",
                    "face_detected": analysis.get("face_detected", False),
                    "coordinates": analysis.get("coordinates")
                }

            # 2. Check Liveness
            if analysis['liveness'] == 'fail':
                return {
                    "message": f"⚠️ Liveness Check Failed. Detected Emotion: {analysis['emotion']}. Please maintain a neutral expression.",
                    "user": None,
                    "status": "fail",
                    "face_detected": True,
                    "coordinates": analysis.get("coordinates")
                }

            # 3. Recognition
            target_encoding_np = np.array(analysis['encoding'])
            known_users = await self.user_service.user_repo.get_all_encodings()
            
            best_match: Optional[Tuple[User, float]] = None
            
            for user in known_users:
                if not user.face_encodings:
                    continue
                
                known_encoding_np = np.array(user.face_encodings)
                # Calculate Euclidean distance
                distance = np.linalg.norm(target_encoding_np - known_encoding_np)
                
                if distance < VERIFICATION_THRESHOLD:
                    if best_match is None or distance < best_match[1]:
                        best_match = (user, distance)

            if best_match:
                matched_user = best_match[0]
                
                # 4. Logging
                log_data = AttendanceLog(
                    user_id=str(matched_user.id),
                    event_type="check_in",
                    liveness_status="pass",
                )
                await self.attendance_repo.add_log(log_data)
                
                return {
                    "message": f"✅ Welcome, {matched_user.name}! Check-in Successful.",
                    "user": matched_user.name,
                    "status": "success",
                    "face_detected": True,
                    "coordinates": analysis.get("coordinates"),
                    "distance": float(best_match[1])
                }

            return {
                "message": f"❌ Recognition Failed. User not found in database. Please register first.",
                "user": None,
                "status": "fail",
                "face_detected": True,
                "coordinates": analysis.get("coordinates")
            }