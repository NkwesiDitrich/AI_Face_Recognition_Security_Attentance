# backend/app/domains/attendance/service.py
# 🔴 FIXED: Handle DeepFace returning embedding directly as a list

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
        FIXED REAL-TIME FACE RECOGNITION FLOW:

        1. Rate limit (prevent overlapping)
        2. Decode image
        3. Detect face + Extract encoding (with lenient detection)
        4. Compare with ALL enrolled users in MongoDB
        5. Return proper success/fail response
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

                    # Run in thread pool to not block
                    results = await run_in_threadpool(
                        DeepFace.represent,
                        img_path=temp_path,
                        model_name="ArcFace",
                        detector_backend="opencv",
                        enforce_detection=False,  # ✅ LENIENT for video!
                        align=True
                    )

                    print(f"📊 DeepFace returned type: {type(results)}")
                    
                    # 🔴 FIX: Handle ALL possible return types from DeepFace
                    # Case 1: results is a list of 512 floats (embedding vector directly)
                    # Case 2: results is a list of dicts [{"embedding": [...], "facial_area": {...}}, ...]
                    # Case 3: results is empty list (no face detected)
                    # Case 4: results is None or other unexpected type
                    
                    embedding = None
                    facial_area = {}
                    
                    if results is None:
                        print("❌ DeepFace returned None")
                        return {
                            "status": "no_face",
                            "message": "Place your face inside the frame",
                            "face_detected": False
                        }
                    
                    # Case 1: results is a list of floats (embedding vector)
                    if isinstance(results, list) and len(results) > 0:
                        first_item = results[0]
                        
                        # Check if first item is a float (embedding vector directly)
                        if isinstance(first_item, (int, float)):
                            print(f"✅ DeepFace returned embedding vector with {len(results)} dimensions")
                            embedding = results if isinstance(results, list) else list(results)
                            
                            # Convert to list if numpy array
                            if hasattr(embedding, 'tolist'):
                                embedding = embedding.tolist()
                                
                            # Estimate facial area (center of image)
                            height, width = img.shape[:2]
                            face_size = min(width, height) // 3
                            center_x = width // 2
                            center_y = height // 2
                            facial_area = {
                                "x": center_x - face_size // 2,
                                "y": center_y - face_size // 2,
                                "w": face_size,
                                "h": face_size
                            }
                        
                        # Case 2: results is a list of dicts
                        elif isinstance(first_item, dict):
                            print(f"✅ DeepFace returned list of {len(results)} dict(s)")
                            result_dict = first_item
                            raw_embedding = result_dict.get("embedding")
                            
                            if raw_embedding is not None:
                                # Convert numpy array to list if needed
                                if hasattr(raw_embedding, 'tolist'):
                                    embedding = raw_embedding.tolist()
                                elif isinstance(raw_embedding, list):
                                    embedding = raw_embedding
                                
                                facial_area = result_dict.get("facial_area", {})
                            else:
                                print("❌ Dict has no 'embedding' key")
                                return {
                                    "status": "no_face",
                                    "message": "Place your face inside the frame",
                                    "face_detected": False
                                }
                        
                        # Case 3: First item is something else
                        else:
                            print(f"❌ Unexpected list item type: {type(first_item)}")
                            return {
                                "status": "no_face",
                                "message": "Place your face inside the frame",
                                "face_detected": False
                            }
                    
                    # Case 4: results is not a list
                    else:
                        print(f"❌ DeepFace returned unexpected type: {type(results)}")
                        return {
                            "status": "no_face",
                            "message": "Place your face inside the frame",
                            "face_detected": False
                        }

                    # Validate embedding
                    if embedding is None:
                        print("❌ No embedding extracted")
                        return {
                            "status": "no_face",
                            "message": "Place your face inside the frame",
                            "face_detected": False
                        }
                    
                    # Convert to list if numpy array
                    if hasattr(embedding, 'tolist'):
                        embedding = embedding.tolist()
                    
                    # Check embedding length (ArcFace should be 512)
                    if not isinstance(embedding, list) or len(embedding) < 512:
                        print(f"❌ Invalid embedding length: {len(embedding) if isinstance(embedding, list) else 'not a list'}")
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
