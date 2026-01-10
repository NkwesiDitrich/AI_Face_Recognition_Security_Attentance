# backend/app/domains/attendance/service.py
# ✅ COMPLETE - Face Recognition + Attendance Recording

from typing import Dict, Any
from datetime import datetime
import numpy as np
import cv2
import asyncio
import os
import tempfile
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService
from app.domains.system_log.repository import SystemLogRepository
from app.domains.system_log.models import SystemLog
import time
import uuid

# ============================================================================
# FACE RECOGNITION SETTINGS (Same as enrollment)
# ============================================================================
DETECTOR_BACKENDS = ["retinaface", "mtcnn", "opencv", "mediapipe"]
MODEL_NAME = "ArcFace"
RECOGNITION_THRESHOLD = 0.50

print("="*60)
print("✅ Attendance Service Initialized")
print("="*60)
print(f"   Model: {MODEL_NAME}")
print(f"   Detectors: {DETECTOR_BACKENDS}")
print(f"   Threshold: {RECOGNITION_THRESHOLD}")
print("="*60)


class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService, system_log_repo: SystemLogRepository = None):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self.system_log_repo = system_log_repo  # Optional - will be None if not injected
        self._processing_lock = asyncio.Lock()
        # Track active sessions: {session_id: {"start_time": float, "device_id": str, "recognition_duration": int}}
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    async def process_attendance_frame(self, image_data: bytes, session_id: str = None, device_id: str = "mobile_app") -> Dict[str, Any]:
        """
        PHASE 1: Face Recognition
        
        Args:
            image_data: Image bytes for face recognition
            session_id: Optional session ID. If None, generates new one
            device_id: Device identifier (default: "mobile_app")
        """
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing another request..."
            }
        
        # Generate session_id if not provided
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
        
        recognition_start_time = time.time()
        
        # ✅ LOG 1: Recognition attempt started
        if self.system_log_repo:
            try:
                await self.system_log_repo.add_log(SystemLog(
                    type="attendance_recognition",
                    stage="started",
                    session_id=session_id,
                    device_id=device_id
                ))
            except Exception as e:
                print(f"⚠️ Failed to log recognition started: {e}")
        
        self._active_sessions[session_id] = {
            "start_time": recognition_start_time,
            "device_id": device_id
        }
        
        async with self._processing_lock:
            temp_path = None
            try:
                print("\n" + "="*50)
                print("📥 PHASE 1: FACE RECOGNITION")
                print(f"   Session ID: {session_id}")
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

                recognition_duration_ms = int((time.time() - recognition_start_time) * 1000)
                
                if best_match and best_distance < RECOGNITION_THRESHOLD:
                    confidence = float(1.0 - best_distance)
                    print(f"\n✅ RECOGNIZED: {best_name} (confidence: {confidence:.2%})")
                    
                    # ✅ LOG 2: Recognition success
                    if self.system_log_repo:
                        try:
                            await self.system_log_repo.add_log(SystemLog(
                                type="attendance_recognition",
                                stage="success",
                                session_id=session_id,
                                user_id=best_id,
                                confidence=round(confidence, 4),
                                distance=round(best_distance, 4),
                                duration_ms=recognition_duration_ms,
                                device_id=device_id
                            ))
                        except Exception as e:
                            print(f"⚠️ Failed to log recognition success: {e}")
                    
                    # Update session tracking
                    if session_id in self._active_sessions:
                        self._active_sessions[session_id]["recognition_duration"] = recognition_duration_ms
                        self._active_sessions[session_id]["user_id"] = best_id
                    
                    return {
                        "status": "recognized",
                        "user": {"id": best_id, "name": best_name},
                        "confidence": round(confidence, 4),
                        "distance": round(best_distance, 4),
                        "message": f"Face recognized: {best_name}",
                        "session_id": session_id  # Return session_id to frontend
                    }
                else:
                    print(f"\n❌ NOT RECOGNIZED: {best_name}")
                    
                    # ✅ LOG 2: Recognition failed
                    if self.system_log_repo:
                        try:
                            await self.system_log_repo.add_log(SystemLog(
                                type="attendance_recognition",
                                stage="failed",
                                session_id=session_id,
                                reason="no_match",
                                distance=round(best_distance, 4) if best_distance != float('inf') else None,
                                duration_ms=recognition_duration_ms,
                                device_id=device_id
                            ))
                        except Exception as e:
                            print(f"⚠️ Failed to log recognition failed: {e}")
                    
                    return {
                        "status": "not_recognized",
                        "message": "Face not recognized",
                        "distance": round(best_distance, 4) if best_distance != float('inf') else None,
                        "session_id": session_id  # Return session_id even on failure
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

    async def record_attendance(
        self, 
        user_id: str, 
        liveness_status: str = "passed", 
        event_type: str = "check_in",
        session_id: str = None,
        device_id: str = "mobile_app",
        attempts_used: int = 1,
        final_failed_action: str = None,
        actions_requested: list = None,
        liveness_start_time: float = None,
        liveness_duration_ms: int = None
    ) -> Dict[str, Any]:
        """
        PHASE 4: Record attendance after successful recognition + liveness.
        
        Args:
            user_id: The ID of the recognized user
            liveness_status: "passed" or "failed" (from frontend liveness check)
            event_type: Type of event (default: "check_in")
            session_id: Session ID from recognition phase
            device_id: Device identifier
            attempts_used: Number of liveness attempts used
            final_failed_action: Action that failed (if liveness failed)
            actions_requested: List of actions requested during liveness
            liveness_start_time: Timestamp when liveness started (for duration calculation)
            liveness_duration_ms: Pre-calculated liveness duration in ms (preferred over calculating from start_time)
        """
        try:
            from app.domains.attendance.models import AttendanceLog
            
            # Calculate total duration: recognition + liveness
            total_duration_ms = None
            if session_id and session_id in self._active_sessions:
                session = self._active_sessions[session_id]
                recognition_duration = session.get("recognition_duration")
                
                # Use provided liveness_duration_ms or calculate from start_time if needed
                liveness_duration = liveness_duration_ms
                if liveness_duration is None and liveness_start_time:
                    liveness_duration = int((time.time() - liveness_start_time) * 1000)
                
                if recognition_duration is not None and liveness_duration is not None:
                    total_duration_ms = recognition_duration + liveness_duration
            
            # ✅ LOG 5: Final attendance record (only if liveness passed)
            if liveness_status == "passed" and self.system_log_repo:
                try:
                    await self.system_log_repo.add_log(SystemLog(
                        type="attendance_record",
                        user_id=user_id,
                        session_id=session_id,
                        event_type=event_type,
                        liveness_status=liveness_status,
                        total_duration_ms=total_duration_ms,
                        device_id=device_id,
                        metadata={
                            "attempts_used": attempts_used,
                            "actions_requested": actions_requested or []
                        }
                    ))
                except Exception as e:
                    print(f"⚠️ Failed to log attendance record: {e}")
            
            # Save to attendance logs collection
            log = AttendanceLog(
                user_id=user_id, 
                status="present",
                liveness=liveness_status,
                event_type=event_type
            )
            result = await self.attendance_repo.add_log(log)
            
            # Clean up session tracking
            if session_id and session_id in self._active_sessions:
                del self._active_sessions[session_id]
            
            print("\n" + "="*50)
            print("✅ PHASE 4: ATTENDANCE RECORDED")
            print("="*50)
            print(f"   User ID: {user_id}")
            print(f"   Liveness: {liveness_status}")
            print(f"   Event: {event_type}")
            print(f"   Session ID: {session_id}")
            print(f"   Log ID: {result.id}")
            if total_duration_ms:
                print(f"   Total Duration: {total_duration_ms}ms")
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
    
    async def log_liveness_started(
        self,
        session_id: str,
        user_id: str,
        device_id: str = "mobile_app",
        actions_requested: list = None
    ):
        """✅ LOG 1: Liveness session started"""
        if self.system_log_repo:
            try:
                await self.system_log_repo.add_log(SystemLog(
                    type="liveness",
                    stage="started",
                    session_id=session_id,
                    user_id=user_id,
                    device_id=device_id,
                    actions_requested=actions_requested or []
                ))
            except Exception as e:
                print(f"⚠️ Failed to log liveness started: {e}")
    
    async def log_liveness_attempt(
        self,
        session_id: str,
        attempt_number: int,
        failed_action: str = None,
        reason: str = None
    ):
        """✅ LOG 2: Liveness attempt (per retry)"""
        if self.system_log_repo:
            try:
                await self.system_log_repo.add_log(SystemLog(
                    type="liveness",
                    stage="attempt",
                    session_id=session_id,
                    attempt_number=attempt_number,
                    failed_action=failed_action,
                    reason=reason or "timeout"
                ))
            except Exception as e:
                print(f"⚠️ Failed to log liveness attempt: {e}")
    
    async def log_liveness_result(
        self,
        session_id: str,
        user_id: str,
        passed: bool,
        attempts_used: int = 1,
        final_failed_action: str = None,
        duration_ms: int = None
    ):
        """✅ LOG 3: Liveness result (FINAL)"""
        if self.system_log_repo:
            try:
                await self.system_log_repo.add_log(SystemLog(
                    type="liveness",
                    stage="passed" if passed else "failed",
                    session_id=session_id,
                    user_id=user_id,
                    attempts_used=attempts_used,
                    final_failed_action=final_failed_action,
                    duration_ms=duration_ms
                ))
            except Exception as e:
                print(f"⚠️ Failed to log liveness result: {e}")