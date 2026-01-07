# backend/app/domains/attendance/service.py
# ✅ COMPLETE - Face Recognition + Attendance Recording

from typing import Dict, Any
import numpy as np
import cv2
import asyncio
import os
import tempfile
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService

# ============================================================================
# FACE RECOGNITION SETTINGS (Same as enrollment)
# ============================================================================
DETECTOR_BACKENDS = ["retinaface", "mtcnn", "opencv", "mediapipe"]
MODEL_NAME = "ArcFace"

# NOTE:
# - Lower cosine distance = more similar.
# - We intentionally use a *slightly* more permissive threshold than the
#   recommended 0.40 for ArcFace so that legitimately enrolled faces are
#   very unlikely to be rejected during attendance (step 1),
#   while still being reasonably strict against impostors.
#   You can tune this between 0.45–0.65 depending on your environment.
RECOGNITION_THRESHOLD = 0.60

print("="*60)
print("✅ Attendance Service Initialized")
print("="*60)
print(f"   Model: {MODEL_NAME}")
print(f"   Detectors: {DETECTOR_BACKENDS}")
print(f"   Threshold: {RECOGNITION_THRESHOLD}")
print("="*60)


class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1: Face Recognition
        """
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing another request..."
            }
        
        async with self._processing_lock:
            temp_path = None
            try:
                print("\n" + "="*50)
                print("📥 PHASE 1: FACE RECOGNITION")
                print("="*50)
                
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is None:
                    print("❌ Invalid image format")
                    return {"status": "error", "message": "Invalid image format"}

                h, w = img.shape[:2]
                print(f"✅ Image: {w}x{h} ({len(image_data)} bytes)")

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    temp_path = tmp.name
                cv2.imwrite(temp_path, img)
                print(f"✅ Saved temp: {temp_path}")

                print("🔍 Extracting embedding (ArcFace)...")
                
                embedding = None
                backend_used = None
                
                for backend in DETECTOR_BACKENDS:
                    try:
                        print(f"   Trying {backend}...")
                        
                        represent_output = await run_in_threadpool(
                            DeepFace.represent,
                            img_path=temp_path,
                            model_name=MODEL_NAME,
                            detector_backend=backend,
                            enforce_detection=True,
                            align=True,
                        )
                        
                        embedding = self.user_service._parse_deepface_embedding(represent_output)
                        
                        if embedding:
                            backend_used = backend
                            print(f"   ✅ Success with {backend}")
                            break
                            
                    except Exception as e:
                        error_str = str(e).lower()
                        if "face could not be detected" in error_str:
                            print(f"   ⚠️ {backend}: No face detected")
                        else:
                            print(f"   ⚠️ {backend}: {str(e)[:50]}")
                        continue

                if embedding is None:
                    print("🔄 Trying relaxed detection...")
                    try:
                        represent_output = await run_in_threadpool(
                            DeepFace.represent,
                            img_path=temp_path,
                            model_name=MODEL_NAME,
                            detector_backend="opencv",
                            enforce_detection=False,
                            align=True,
                        )
                        embedding = self.user_service._parse_deepface_embedding(represent_output)
                        if embedding:
                            backend_used = "opencv (relaxed)"
                            print(f"   ✅ Success with relaxed detection")
                    except Exception as e:
                        print(f"   ❌ Relaxed also failed: {e}")

                if not embedding or len(embedding) < 512:
                    print("❌ No valid face embedding")
                    return {"status": "no_face", "message": "No face detected"}

                print(f"✅ Embedding: {len(embedding)} dimensions")
                print(f"   Backend: {backend_used}")

                print("\n👥 Comparing with enrolled users...")
                
                known_users = await self.user_service.user_repo.get_all_encodings()
                
                if not known_users:
                    print("⚠️ No users enrolled")
                    return {"status": "not_recognized", "message": "No users registered"}

                print(f"✅ Found {len(known_users)} enrolled users")

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

                if best_match and best_distance < RECOGNITION_THRESHOLD:
                    confidence = float(1.0 - best_distance)
                    print(f"\n✅ RECOGNIZED: {best_name} (confidence: {confidence:.2%})")
                    
                    return {
                        "status": "recognized",
                        "user": {"id": best_id, "name": best_name},
                        "confidence": round(confidence, 4),
                        "distance": round(best_distance, 4),
                        "message": f"Face recognized: {best_name}"
                    }
                else:
                    print(f"\n❌ NOT RECOGNIZED: {best_name}")
                    
                    return {
                        "status": "not_recognized",
                        "message": "Face not recognized",
                        "distance": round(best_distance, 4)
                    }

            except Exception as e:
                print(f"\n❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
                return {"status": "error", "message": str(e)}

            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                        print("\n🗑️ Temp file cleaned up")
                    except:
                        pass

    async def record_attendance(self, user_id: str, liveness_status: str = "passed", event_type: str = "check_in") -> Dict[str, Any]:
        """
        PHASE 4: Record attendance after successful recognition + liveness.
        
        Args:
            user_id: The ID of the recognized user
            liveness_status: "passed" or "failed" (from frontend liveness check)
            event_type: Type of event (default: "check_in")
        """
        try:
            from app.domains.attendance.models import AttendanceLog
            
            log = AttendanceLog(
                user_id=user_id, 
                status="present",
                liveness=liveness_status,
                event_type=event_type
            )
            result = await self.attendance_repo.add_log(log)
            
            print("\n" + "="*50)
            print("✅ PHASE 4: ATTENDANCE RECORDED")
            print("="*50)
            print(f"   User ID: {user_id}")
            print(f"   Liveness: {liveness_status}")
            print(f"   Event: {event_type}")
            print(f"   Log ID: {result.id}")
            print("="*50)
            
            return {
                "status": "success",
                "message": "Attendance recorded successfully",
                "user_id": user_id,
                "liveness": liveness_status,
                "event_type": event_type
            }
        except Exception as e:
            print(f"❌ Recording error: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
