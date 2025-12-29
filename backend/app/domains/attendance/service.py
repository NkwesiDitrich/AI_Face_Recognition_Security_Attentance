# backend/app/domains/attendance/service.py
# COMPLETE REAL-TIME FACE RECOGNITION FIX
# Based on best practices from GitHub repositories

"""
Real-time Face Recognition for Attendance System

This implementation:
1. Uses Haar Cascades for fast face detection (green frame)
2. Uses DeepFace.represent() for face recognition
3. Has fallback for different DeepFace versions
4. Uses lenient threshold for real-time video
5. Properly handles WebSocket streaming

Based on best practices from:
- serengil/deepface (official DeepFace repo)
- ageitgey/face_recognition
- haseebsultankhan/Face-Recognition-System-using-DeepFace
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

# Lenient threshold for real-time video recognition
# Your investigation showed 0.45 is too strict for video frames
RECOGNITION_THRESHOLD = 0.55


class AttendanceService:
    def __init__(self, attendance_repo, user_service):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    def _detect_face_haar(self, img: np.ndarray) -> Optional[Dict[str, float]]:
        """
        Fast face detection using OpenCV Haar Cascades.
        Returns normalized coordinates (0-1) for the green frame.
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)

            if len(faces) == 0:
                return None

            # Get largest face
            (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])

            height, width = img.shape[:2]

            return {
                "x": float(x / width),
                "y": float(y / height),
                "w": float(w / width),
                "h": float(h / height),
                "confidence": 1.0  # Haar Cascades don't provide confidence
            }

        except Exception as e:
            print(f"[AttendanceService] Haar detection error: {e}")
            return None

    async def _extract_embedding(self, image_data: bytes) -> Optional[List[float]]:
        """
        Extract face embedding using DeepFace.
        
        This addresses the core issue:
        - Enrollment uses strict detection (high-quality photos)
        - Real-time video is lower quality
        - Need lenient detection + proper embedding extraction
        """
        temp_path = None
        try:
            # Decode image
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                print("[AttendanceService] Failed to decode image")
                return None

            # Save image for DeepFace
            temp_path = tempfile.mktemp(suffix=".jpg")
            cv2.imwrite(temp_path, img)

            print(f"[AttendanceService] Processing image: {temp_path}")

            # Try multiple strategies (from most to least preferred)
            strategies = [
                {
                    "name": "ArcFace + OpenCV (Lenient)",
                    "model": "ArcFace",
                    "detector": "opencv",
                    "enforce": False
                },
                {
                    "name": "VGG-Face + OpenCV (Lenient)",
                    "model": "VGG-Face", 
                    "detector": "opencv",
                    "enforce": False
                },
                {
                    "name": "ArcFace + No Detector",
                    "model": "ArcFace",
                    "detector": "skip",
                    "enforce": False
                }
            ]

            for strategy in strategies:
                try:
                    print(f"[AttendanceService] Trying {strategy['name']}...")

                    if strategy["detector"] == "skip":
                        # Skip detection, use entire image
                        result = await run_in_threadpool(
                            DeepFace.represent,
                            img_path=temp_path,
                            model_name=strategy["model"],
                            enforce_detection=False,
                        )
                    else:
                        # Use detection
                        result = await run_in_threadpool(
                            DeepFace.represent,
                            img_path=temp_path,
                            model_name=strategy["model"],
                            detector_backend=strategy["detector"],
                            align=True,
                            enforce_detection=False,  # Lenient for video
                        )

                    # Parse result
                    if result and len(result) > 0:
                        first = result[0]

                        # DeepFace.represent returns list of dicts with "embedding" key
                        if isinstance(first, dict) and "embedding" in first:
                            embedding = first["embedding"]
                            if isinstance(embedding, list) and len(embedding) >= 100:
                                print(f"[AttendanceService] ✅ SUCCESS: {strategy['name']}")
                                print(f"[AttendanceService] Embedding length: {len(embedding)}")
                                return embedding
                        
                        # Sometimes DeepFace returns the embedding directly as a list
                        elif isinstance(first, list) and len(first) >= 100:
                            print(f"[AttendanceService] ✅ SUCCESS: {strategy['name']} (direct list)")
                            print(f"[AttendanceService] Embedding length: {len(first)}")
                            return first

                except Exception as e:
                    print(f"[AttendanceService] ⚠️ {strategy['name']} failed: {e}")
                    continue

            print("[AttendanceService] ❌ All strategies failed")
            return None

        except Exception as e:
            print(f"[AttendanceService] Embedding extraction error: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1: Real-Time Face Recognition
        
        Flow:
        1. Prevent overlapping frame processing
        2. Fast Haar detection for green frame
        3. Extract embedding for recognition
        4. Compare with enrolled users
        5. Return result
        
        Returns:
        - success: Face recognized
        - no_face: No face detected
        - fail: Face detected but not recognized
        """
        # Rate limiting
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing...",
                "face_detected": False
            }

        async with self._processing_lock:
            try:
                print("\n" + "="*60)
                print("[AttendanceService] 🎯 Processing new frame")
                print("="*60)

                # Step 1: Fast Haar detection for green frame
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if img is None:
                    return {"status": "error", "message": "Failed to decode image"}

                print("[AttendanceService] 🔍 Running Haar detection...")
                face_coords = await run_in_threadpool(
                    self._detect_face_haar, img
                )

                if not face_coords:
                    print("[AttendanceService] ❌ No face detected by Haar")
                    return {
                        "status": "no_face",
                        "message": "Place your face inside the frame",
                        "face_detected": False
                    }

                print(f"[AttendanceService] ✅ Face detected: {face_coords}")

                # Step 2: Extract embedding for recognition
                print("[AttendanceService] 🧠 Extracting embedding...")
                target_encoding = await self._extract_embedding(image_data)

                if not target_encoding:
                    print("[AttendanceService] ❌ Could not extract embedding")
                    return {
                        "status": "fail",
                        "message": "Could not process face. Please try again.",
                        "face_detected": True,
                        "coords": face_coords
                    }

                print(f"[AttendanceService] ✅ Embedding extracted: {len(target_encoding)} dimensions")

                # Step 3: Compare with enrolled users
                if not self.user_service:
                    print("[AttendanceService] ⚠️ No user_service configured")
                    return {
                        "status": "encoding_extracted",
                        "message": "Face detected and encoded",
                        "face_detected": True,
                        "coords": face_coords,
                        "encoding_length": len(target_encoding)
                    }

                print("[AttendanceService] 🔄 Comparing with enrolled users...")
                known_users = await self.user_service.user_repo.get_all_encodings()

                if not known_users:
                    print("[AttendanceService] ⚠️ No users enrolled")
                    return {
                        "status": "fail",
                        "message": "No users registered",
                        "face_detected": True,
                        "coords": face_coords
                    }

                print(f"[AttendanceService] Comparing against {len(known_users)} enrolled users")

                # Step 4: Find best match
                target_vec = self.user_service._l2_normalize(target_encoding)
                best_match = None
                best_distance = float('inf')

                for user in known_users:
                    if not user.face_encodings:
                        continue
                    
                    if len(user.face_encodings) != len(target_encoding):
                        print(f"[AttendanceService] ⚠️ Skipping {user.name}: size mismatch")
                        continue

                    known_vec = self.user_service._l2_normalize(user.face_encodings)
                    dist = self.user_service._cosine_distance(target_vec, known_vec)

                    print(f"[AttendanceService] Distance to {user.name}: {dist:.4f}")

                    if dist < best_distance:
                        best_distance = dist
                        best_match = user

                # Step 5: Return result
                print(f"\n[AttendanceService] Best match: {best_match.name if best_match else 'None'}")
                print(f"[AttendanceService] Best distance: {best_distance:.4f}")
                print(f"[AttendanceService] Threshold: {RECOGNITION_THRESHOLD}")

                if best_match and best_distance < RECOGNITION_THRESHOLD:
                    print(f"[AttendanceService] ✅ SUCCESS! Match: {best_match.name}")
                    return {
                        "status": "success",
                        "message": "✔ Face recognized",
                        "user": best_match.name,
                        "user_id": str(best_match.id),
                        "face_detected": True,
                        "coords": face_coords,
                        "confidence": float(1.0 - best_distance),
                        "debug": {
                            "distance": best_distance,
                            "threshold": RECOGNITION_THRESHOLD
                        }
                    }
                else:
                    if best_match:
                        print(f"[AttendanceService] ❌ FAIL: Distance {best_distance:.4f} >= threshold {RECOGNITION_THRESHOLD}")
                    else:
                        print("[AttendanceService] ❌ FAIL: No match found")
                    
                    return {
                        "status": "fail",
                        "message": "Face not registered",
                        "face_detected": True,
                        "coords": face_coords,
                        "debug": {
                            "best_distance": best_distance if best_match else None,
                            "threshold": RECOGNITION_THRESHOLD
                        }
                    }

            except Exception as e:
                print(f"[AttendanceService] Error: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error",
                    "message": str(e),
                    "face_detected": False
                }

    async def record_attendance(self, user_id: str, liveness_status: str = "pass") -> Dict[str, Any]:
        """Record attendance after successful recognition and liveness check."""
        try:
            log_data = AttendanceLog(
                user_id=user_id,
                event_type="check_in",
                liveness_status=liveness_status,
            )
            await self.attendance_repo.add_log(log_data)
            return {
                "status": "recorded",
                "message": "Attendance recorded",
                "user_id": user_id
            }
        except Exception as e:
            print(f"[AttendanceService] Recording error: {e}")
            return {"status": "error", "message": str(e)}
