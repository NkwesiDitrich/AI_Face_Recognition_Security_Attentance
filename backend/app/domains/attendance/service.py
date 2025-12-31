# backend/app/domains/attendance/service.py
# ✅ COMPLETE PHASE 1 - SIMPLIFIED BACKEND (Recognition Only)
# Frontend handles face detection + quality check, backend only recognizes

"""
PHASE 1 - Face Recognition (Backend)

This backend ONLY does recognition. Frontend (ML Kit) handles:
- Face detection
- Face quality validation (size, position, angle)
- Only sends HIGH-QUALITY frames to backend

Backend receives validated frames and:
1. Extract embedding (ArcFace)
2. Compare with enrolled users
3. Return recognition result
"""

from typing import Dict, Any, Optional, List
import numpy as np
import cv2
import tempfile
import os
import asyncio
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace

from app.domains.attendance.repository import AttendanceRepository
from app.domains.attendance.models import AttendanceLog

# Recognition threshold (more lenient since frontend sends only valid faces)
RECOGNITION_THRESHOLD = 0.50


class AttendanceService:
    def __init__(self, attendance_repo, user_service):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1 - Face Recognition Endpoint
        
        Frontend (ML Kit) already validated:
        ✅ Face is present
        ✅ Face size >= 120x120 pixels
        ✅ Face is centered
        ✅ Face is not tilted
        
        Backend only needs to:
        1. Extract embedding
        2. Compare with enrolled users
        3. Return recognition result
        """
        # Rate limiting
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing...",
                "face_detected": True
            }

        async with self._processing_lock:
            try:
                print("\n" + "="*60)
                print("🎯 PHASE 1 - Face Recognition (Backend)")
                print("="*60)

                # Decode image
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is None:
                    print("❌ Failed to decode image")
                    return {
                        "status": "error",
                        "message": "Invalid image",
                        "face_detected": False
                    }

                height, width = img.shape[:2]
                print(f"✅ Image decoded: {height}x{width}")

                # Save to temp file
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                        temp_path = tmp_file.name
                    cv2.imwrite(temp_path, img)

                    # Extract embedding (ArcFace is most accurate)
                    print("🔍 Extracting face embedding...")
                    
                    results = await run_in_threadpool(
                        DeepFace.represent,
                        img_path=temp_path,
                        model_name="ArcFace",
                        detector_backend="skip",  # Skip detection, use entire image
                        enforce_detection=False,
                        align=True
                    )

                    print(f"📊 DeepFace returned {len(results)} results")

                    if not results or len(results) == 0:
                        print("❌ No embedding extracted")
                        return {
                            "status": "no_embedding",
                            "message": "Could not extract face encoding",
                            "face_detected": False
                        }

                    # Handle DeepFace output format
                    result = results[0]
                    
                    # DeepFace can return either:
                    # 1. Dict with "embedding" key: {"embedding": [...], ...}
                    # 2. Direct list of floats: [0.123, 0.456, ...]
                    
                    if isinstance(result, dict) and "embedding" in result:
                        embedding = result["embedding"]
                    elif isinstance(result, list):
                        embedding = result
                    else:
                        print(f"❌ Unexpected format: {type(result)}")
                        return {
                            "status": "error",
                            "message": "Unexpected embedding format",
                            "face_detected": False
                        }

                    if not embedding or len(embedding) < 512:
                        print("❌ Invalid embedding")
                        return {
                            "status": "error",
                            "message": "Invalid face encoding",
                            "face_detected": False
                        }

                    print(f"✅ Embedding extracted: {len(embedding)} dimensions")

                    # Get enrolled users from MongoDB
                    print("🔍 Fetching enrolled users...")
                    known_users = await self.user_service.user_repo.get_all_encodings()
                    
                    if not known_users:
                        print("⚠️ No users enrolled")
                        return {
                            "status": "not_recognized",
                            "message": "No users registered in system",
                            "face_detected": True
                        }

                    print(f"✅ Found {len(known_users)} enrolled users")

                    # Compare embeddings using cosine distance
                    target_vec = self.user_service._l2_normalize(embedding)
                    
                    best_match = None
                    best_distance = float('inf')
                    best_user_name = "Unknown"

                    for user in known_users:
                        if not user.face_encodings:
                            continue
                        
                        if len(user.face_encodings) != len(embedding):
                            continue
                        
                        known_vec = self.user_service._l2_normalize(user.face_encodings)
                        distance = self.user_service._cosine_distance(target_vec, known_vec)
                        
                        print(f"   Distance to {user.name}: {distance:.4f} (threshold: {RECOGNITION_THRESHOLD})")
                        
                        if distance < best_distance:
                            best_distance = distance
                            best_match = user
                            best_user_name = user.name

                    print(f"\n🏆 Best match: {best_user_name}")
                    print(f"   Best distance: {best_distance:.4f}")
                    print(f"   Threshold: {RECOGNITION_THRESHOLD}")

                    # Return result
                    if best_match and best_distance < RECOGNITION_THRESHOLD:
                        confidence = float(1.0 - best_distance)
                        print(f"✅ SUCCESS: {best_user_name} recognized!")
                        
                        return {
                            "status": "recognized",
                            "message": "✔ Face recognized",
                            "user": {
                                "id": str(best_match.id),
                                "name": best_user_name
                            },
                            "face_detected": True,
                            "distance": best_distance,
                            "confidence": confidence
                        }
                    else:
                        print(f"❌ FAIL: Distance {best_distance:.4f} >= threshold {RECOGNITION_THRESHOLD}")
                        
                        return {
                            "status": "not_recognized",
                            "message": "Face not registered",
                            "face_detected": True,
                            "distance": best_distance
                        }

                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                            print("🧹 Cleaned up temp file")
                        except:
                            pass

            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error",
                    "message": str(e),
                    "face_detected": True
                }

    async def record_attendance(self, user_id: str) -> Dict[str, Any]:
        """Record attendance after successful recognition."""
        try:
            log = AttendanceLog(user_id=user_id, status="present")
            result = await self.attendance_repo.add_log(log)
            return {
                "status": "success",
                "message": "Attendance recorded",
                "log_id": str(result.id)
            }
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return {"status": "error", "message": str(e)}
