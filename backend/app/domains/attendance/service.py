# backend/app/domains/attendance/service.py
# ✅ FIXED - Consistent response format for frontend

from typing import Dict, Any
import numpy as np
import cv2
import asyncio
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService

# Threshold for recognition (adjust as needed)
RECOGNITION_THRESHOLD = 0.65


class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 3 - Face Recognition (Identity Check)
        Receives validated frame from frontend and compares with enrolled users.
        """
        # Rate limiting - one request at a time
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing another request..."
            }
        
        async with self._processing_lock:
            try:
                print("\n" + "="*50)
                print("📥 RECEIVED FRAME FOR RECOGNITION")
                print("="*50)
                
                # Decode image
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is None:
                    print("❌ Invalid image")
                    return {
                        "status": "error",
                        "message": "Invalid image format"
                    }

                h, w = img.shape[:2]
                print(f"✅ Image size: {w}x{h}")

                # PHASE 3: Extract embedding using ArcFace
                print("🔍 Extracting embedding...")
                
                # Using skip detector since frontend already validated face
                res = await run_in_threadpool(
                    DeepFace.represent,
                    img_path=img,
                    model_name="ArcFace",
                    detector_backend="skip",
                    enforce_detection=False,
                    align=True
                )
                
                embedding = self.user_service._parse_deepface_embedding(res)
                
                if not embedding or len(embedding) < 512:
                    print("❌ No valid embedding")
                    return {
                        "status": "no_face",
                        "message": "No face detected"
                    }
                
                print(f"✅ Embedding: {len(embedding)} dimensions")

                # PHASE 4: Compare with enrolled users
                print("👥 Comparing with enrolled users...")
                
                known_users = await self.user_service.user_repo.get_all_encodings()
                
                if not known_users:
                    print("⚠️ No users enrolled")
                    return {
                        "status": "not_recognized",
                        "message": "No users registered"
                    }
                
                print(f"✅ Found {len(known_users)} enrolled users")

                # Calculate similarity
                target_vec = self.user_service._l2_normalize(embedding)
                best_match = None
                best_distance = float('inf')
                best_name = "Unknown"
                best_id = None

                for user in known_users:
                    if not user.face_encodings:
                        continue
                    
                    if len(user.face_encodings) != len(embedding):
                        continue
                    
                    known_vec = self.user_service._l2_normalize(user.face_encodings)
                    distance = self.user_service._cosine_distance(target_vec, known_vec)
                    
                    print(f"   → {user.name}: distance={distance:.4f}")
                    
                    if distance < best_distance:
                        best_distance = distance
                        best_match = user
                        best_name = user.name
                        best_id = str(user.id)

                print(f"\n🏆 Best match: {best_name}")
                print(f"   Distance: {best_distance:.4f}")
                print(f"   Threshold: {RECOGNITION_THRESHOLD}")

                # PHASE 4: Return result
                if best_match and best_distance < RECOGNITION_THRESHOLD:
                    confidence = float(1.0 - best_distance)
                    print(f"✅ RECOGNIZED: {best_name} (confidence: {confidence:.2%})")
                    
                    return {
                        "status": "recognized",
                        "user": {"id": best_id, "name": best_name},
                        "confidence": confidence,
                        "message": "Face recognized successfully"
                    }
                else:
                    print(f"❌ NOT RECOGNIZED: {best_name}")
                    
                    return {
                        "status": "not_recognized",
                        "message": "Face not registered"
                    }
                    
            except Exception as e:
                print(f"❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error",
                    "message": str(e)
                }

    async def record_attendance(self, user_id: str) -> Dict[str, Any]:
        """Record attendance after successful recognition."""
        try:
            from app.domains.attendance.models import AttendanceLog
            log = AttendanceLog(user_id=user_id, status="present")
            await self.attendance_repo.add_log(log)
            return {
                "status": "success",
                "message": "Attendance recorded"
            }
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
