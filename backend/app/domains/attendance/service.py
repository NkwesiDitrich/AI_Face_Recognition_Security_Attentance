# backend/app/domains/attendance/service.py
# ✅ SIMPLE, STABLE REAL-TIME FACE RECOGNITION

"""
Real-time Face Recognition - Simple and Stable

This implementation:
1. Detects face with lenient detection (for video)
2. Extracts encoding
3. Compares with ALL enrolled users
4. Returns proper success/fail response
5. NO complex rotation logic (causes issues)
6. NO WebSocket disconnections
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

# Threshold for recognition (lenient for video)
RECOGNITION_THRESHOLD = 0.55


class AttendanceService:
    def __init__(self, attendance_repo, user_service):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        SIMPLE REAL-TIME FACE RECOGNITION FLOW:
        
        1. Rate limit (prevent overlapping)
        2. Decode image
        3. Detect face + Extract encoding (with lenient detection)
        4. Compare with ALL enrolled users in MongoDB
        5. Return success/fail
        """
        # Rate limiting
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing previous frame...",
                "face_detected": False
            }

        async with self._processing_lock:
            try:
                print("\n" + "="*60)
                print("🎯 Processing attendance frame")
                print("="*60)

                # Step 1: Decode image
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is None:
                    return {
                        "status": "error",
                        "message": "Invalid image",
                        "face_detected": False
                    }

                print(f"✅ Image decoded: {img.shape}")

                # Step 2: Save to temp file
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                        temp_path = tmp_file.name
                    cv2.imwrite(temp_path, img)
                    print(f"✅ Saved: {temp_path}")

                    # Step 3: Detect face + Extract encoding (LENIENT for video!)
                    print("🔍 Detecting face...")
                    
                    # Use LENIENT detection for real-time video
                    # This is the KEY difference from enrollment!
                    results = await run_in_threadpool(
                        DeepFace.represent,
                        img_path=temp_path,
                        model_name="ArcFace",
                        detector_backend="opencv",
                        enforce_detection=False,  # ✅ LENIENT for video!
                        align=True
                    )

                    print(f"📊 DeepFace returned {len(results)} results")

                    if not results or len(results) == 0:
                        print("❌ No face detected")
                        return {
                            "status": "no_face",
                            "message": "Place your face inside the frame",
                            "face_detected": False
                        }

                    # Get the first result
                    result = results[0]
                    embedding = result.get("embedding")
                    facial_area = result.get("facial_area", {})

                    if not embedding or not isinstance(embedding, list) or len(embedding) < 512:
                        print("❌ Invalid embedding")
                        return {
                            "status": "no_face",
                            "message": "Place your face inside the frame",
                            "face_detected": False
                        }

                    print(f"✅ Face detected! Embedding length: {len(embedding)}")

                    # Calculate normalized coordinates
                    height, width = img.shape[:2]
                    coords = {
                        "x": float(facial_area.get("x", 0) / width),
                        "y": float(facial_area.get("y", 0) / height),
                        "w": float(facial_area.get("w", 0) / width),
                        "h": float(facial_area.get("h", 0) / height)
                    }

                    # Step 4: Get ALL enrolled users from MongoDB
                    print("🔍 Fetching enrolled users...")
                    known_users = await self.user_service.user_repo.get_all_encodings()
                    
                    if not known_users:
                        print("⚠️ No users enrolled")
                        return {
                            "status": "fail",
                            "message": "No users registered in system",
                            "face_detected": True,
                            "coords": coords
                        }

                    print(f"✅ Found {len(known_users)} enrolled users")

                    # Step 5: Compare with ALL enrolled users
                    print("🔄 Comparing with enrolled users...")
                    
                    target_vec = self.user_service._l2_normalize(embedding)
                    best_match = None
                    best_distance = float('inf')
                    best_user_name = "Unknown"

                    for user in known_users:
                        if not user.face_encodings:
                            continue
                        
                        # Skip if encoding size mismatch
                        if len(user.face_encodings) != len(embedding):
                            print(f"⚠️ Skipping {user.name}: size mismatch ({len(user.face_encodings)} vs {len(embedding)})")
                            continue
                        
                        # Compare encodings
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

                    # Step 6: Return result based on threshold
                    if best_match and best_distance < RECOGNITION_THRESHOLD:
                        # ✅ RECOGNIZED!
                        print(f"✅ SUCCESS: {best_user_name} is recognized!")
                        
                        return {
                            "status": "success",
                            "message": "✔ Face recognized",
                            "user": best_user_name,
                            "user_id": str(best_match.id),
                            "face_detected": True,
                            "coords": coords,
                            "distance": best_distance,
                            "confidence": float(1.0 - best_distance)
                        }
                    else:
                        # Face detected but NOT in database
                        if best_match:
                            print(f"❌ FAIL: Distance {best_distance:.4f} >= threshold {RECOGNITION_THRESHOLD}")
                        else:
                            print("❌ FAIL: No match found")
                        
                        return {
                            "status": "fail",
                            "message": "Face not registered",
                            "face_detected": True,
                            "coords": coords,
                            "distance": best_distance
                        }

                finally:
                    # Clean up temp file
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
                    "face_detected": False
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
