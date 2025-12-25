# backend/app/domains/user/service.py

"""
User Service Layer
Business logic for user enrollment and face recognition

FINAL (based on your Investigation Report):
- Model: Facenet512 (512-dim embeddings)
- Distance metric: Cosine distance (with L2 normalization)
- Thresholds: from your thresholds file (Facenet512 cosine threshold = 0.30)
- Multi-sample enrollment: create multiple slightly varied samples and average embeddings
- Strict quality control: blur + brightness checks before embedding
- Strict face detection: do NOT accept garbage embeddings
"""

from typing import Optional, List, Union, Dict, Any, Tuple
import numpy as np
import cv2
import os
import tempfile
import base64

from deepface import DeepFace
from fastapi.concurrency import run_in_threadpool

from app.domains.user.models import User
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.repository import UserRepository


# ---------------------------
# Model / Threshold settings
# ---------------------------
MODEL_NAME = "Facenet512"

# From your thresholds file: Facenet512 cosine threshold = 0.30
# If cosine_distance < 0.30 => considered SAME person.
DUPLICATE_COSINE_THRESHOLD = 0.30

# Recognition can be a bit looser or same; start same for now
RECOGNITION_COSINE_THRESHOLD = 0.30

# Detection backends to try (opencv is fastest & most reliable on emulator)
DETECTOR_BACKENDS = ["opencv", "retinaface", "mtcnn"]

# Minimum embedding length sanity check (Facenet512 should be 512)
MIN_EMBEDDING_LENGTH = 200

# Multi-sample enrollment count (your report recommends 3–5)
N_ENROLL_SAMPLES = 3

# Quality control thresholds
MIN_BRIGHTNESS = 40     # too dark below this
MAX_BRIGHTNESS = 220    # too bright above this
MAX_BLUR_LAPLACIAN = 40 # smaller = blurrier (tune if too strict)


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    # -----------------------------
    # Utility: metrics
    # -----------------------------
    def _l2_normalize(self, vec: List[float]) -> np.ndarray:
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        return arr if norm == 0 else arr / norm

    def _cosine_distance(self, a: np.ndarray, b: np.ndarray) -> float:
        # cosine distance = 1 - cosine similarity
        return float(1.0 - np.dot(a, b))

    # -----------------------------
    # Utility: quality checks
    # -----------------------------
    def _brightness_ok(self, img_bgr: np.ndarray) -> bool:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        mean_val = float(np.mean(gray))
        return MIN_BRIGHTNESS <= mean_val <= MAX_BRIGHTNESS

    def _blur_ok(self, img_bgr: np.ndarray) -> bool:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F).var()
        return lap >= MAX_BLUR_LAPLACIAN

    def _quality_ok(self, img_bgr: np.ndarray) -> bool:
        if not self._brightness_ok(img_bgr):
            return False
        if not self._blur_ok(img_bgr):
            return False
        return True

    # -----------------------------
    # Utility: DeepFace output parsing
    # -----------------------------
    def _parse_embedding(self, represent_output: Any) -> Optional[List[float]]:
        """
        Supports DeepFace variants:
        - list[dict] with embedding key
        - list[float] directly
        """
        if represent_output is None:
            return None

        if isinstance(represent_output, np.ndarray):
            emb = represent_output.flatten().tolist()
            return emb if len(emb) >= MIN_EMBEDDING_LENGTH else None

        if isinstance(represent_output, list) and len(represent_output) > 0:
            first = represent_output[0]

            if isinstance(first, dict) and "embedding" in first:
                emb = first["embedding"]
                if isinstance(emb, np.ndarray):
                    emb = emb.flatten().tolist()
                if isinstance(emb, list) and len(emb) >= MIN_EMBEDDING_LENGTH:
                    return [float(x) for x in emb]
                return None

            if isinstance(first, (int, float, np.number)):
                # embedding is directly the list
                if len(represent_output) >= MIN_EMBEDDING_LENGTH:
                    return [float(x) for x in represent_output]
                return None

        return None

    # -----------------------------
    # Detection strategy: rotations
    # -----------------------------
    def _rotations(self, img_bgr: np.ndarray) -> List[np.ndarray]:
        return [
            img_bgr,
            cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE),
            cv2.rotate(img_bgr, cv2.ROTATE_180),
            cv2.rotate(img_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE),
        ]

    # -----------------------------
    # Core embedding extraction (STRICT)
    # -----------------------------
    async def _extract_embedding_strict(self, img_bgr: np.ndarray) -> Optional[List[float]]:
        """
        Strict extraction:
        - Reject poor-quality images (blur/brightness)
        - Try multiple detectors and rotations with enforce_detection=True
        - DO NOT fallback to enforce_detection=False for enrollment (prevents garbage embeddings)
        """
        if not self._quality_ok(img_bgr):
            print("❌ Quality check failed (blur/brightness).")
            return None

        # Save temp file because some DeepFace builds are more stable with file paths
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            temp_path = tmp.name

        try:
            for rotated in self._rotations(img_bgr):
                cv2.imwrite(temp_path, rotated)

                for backend in DETECTOR_BACKENDS:
                    try:
                        represent_output = await run_in_threadpool(
                            DeepFace.represent,
                            img_path=temp_path,
                            model_name=MODEL_NAME,
                            detector_backend=backend,
                            enforce_detection=True,  # strict
                            align=True,
                        )
                        emb = self._parse_embedding(represent_output)
                        if emb and len(emb) >= MIN_EMBEDDING_LENGTH:
                            return emb
                    except Exception as e:
                        # Try next backend/rotation
                        continue

            return None

        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass

    # -----------------------------
    # Multi-sample enrollment averaging
    # -----------------------------
    def _augment_samples(self, img_bgr: np.ndarray) -> List[np.ndarray]:
        """
        Creates N slightly varied samples (brightness/contrast changes)
        to simulate multi-sample enrollment without changing Flutter.
        This stabilizes the final embedding as your report recommends.
        """
        samples = [img_bgr]

        # Slight brighten
        bright = cv2.convertScaleAbs(img_bgr, alpha=1.05, beta=10)
        samples.append(bright)

        # Slight darken
        dark = cv2.convertScaleAbs(img_bgr, alpha=1.05, beta=-10)
        samples.append(dark)

        return samples[:N_ENROLL_SAMPLES]

    async def _extract_master_embedding(self, image_data: bytes) -> Optional[List[float]]:
        """
        Implements report formula:
        E_master = (1/N) * sum(E_i)
        Then L2-normalize the result.
        """
        nparr = np.frombuffer(image_data, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img_bgr is None:
            print("❌ OpenCV failed to decode image.")
            return None

        embeddings: List[np.ndarray] = []

        for sample in self._augment_samples(img_bgr):
            emb = await self._extract_embedding_strict(sample)
            if emb:
                embeddings.append(self._l2_normalize(emb))

        if len(embeddings) < 2:
            print("❌ Not enough valid samples to build a stable master embedding.")
            return None

        # Average embeddings
        avg = np.mean(np.stack(embeddings, axis=0), axis=0)

        # Normalize again
        avg_norm = avg / (np.linalg.norm(avg) + 1e-8)

        return avg_norm.astype(np.float32).tolist()

    # -----------------------------
    # Duplicate detection
    # -----------------------------
    async def _check_duplicate_enrollment(self, new_encoding: List[float]) -> Optional[User]:
        existing_users = await self.user_repo.get_all_encodings()
        if not existing_users:
            return None

        new_vec = self._l2_normalize(new_encoding)

        best_match = None  # (user, dist)
        for user in existing_users:
            if not user.face_encodings:
                continue

            if len(user.face_encodings) != len(new_encoding):
                continue

            known_vec = self._l2_normalize(user.face_encodings)
            dist = self._cosine_distance(new_vec, known_vec)

            if best_match is None or dist < best_match[1]:
                best_match = (user, dist)

        if best_match:
            user, dist = best_match
            print(f"🧪 Best duplicate candidate: '{user.name}' cosine_distance={dist:.4f}")

            if dist < DUPLICATE_COSINE_THRESHOLD:
                print(f"⚠️ DUPLICATE DETECTED: matches '{user.name}' (cosine_distance={dist:.4f})")
                return user

        return None

    # -----------------------------
    # Enrollment
    # -----------------------------
    async def enroll_user(
        self,
        user_data: UserCreate,
        image_data: bytes
    ) -> Union[UserOut, Dict[str, Any], None]:

        print(f"📸 Extracting master embedding for user: {user_data.name}")
        encoding = await self._extract_master_embedding(image_data)

        if not encoding:
            print(f"❌ Face detection/encoding failed for {user_data.name}")
            return None

        print("🔍 Checking for duplicate enrollment...")
        duplicate_user = await self._check_duplicate_enrollment(encoding)

        if duplicate_user:
            return {
                "error": "duplicate",
                "message": f"Face already registered as {duplicate_user.name}",
                "existing_user_id": str(duplicate_user.id),
                "existing_user_name": duplicate_user.name,
                "existing_employee_id": duplicate_user.employee_id,
            }

        image_base64 = base64.b64encode(image_data).decode("utf-8")

        new_user = User(
            name=user_data.name,
            employee_id=user_data.employee_id,
            access_level=user_data.access_level,
            face_encodings=encoding,
            image_base64=image_base64,
        )

        saved_user = await self.user_repo.add_user(new_user)

        return UserOut(
            id=str(saved_user.id),
            name=saved_user.name,
            employee_id=saved_user.employee_id,
            access_level=saved_user.access_level,
        )

    # -----------------------------
    # Search / recognition
    # -----------------------------
    async def search_user(self, image_data: bytes) -> Optional[UserOut]:
        encoding = await self._extract_master_embedding(image_data)
        if not encoding:
            return None

        known_users = await self.user_repo.get_all_encodings()
        if not known_users:
            return None

        target_vec = self._l2_normalize(encoding)

        best_match = None
        for user in known_users:
            if not user.face_encodings:
                continue

            if len(user.face_encodings) != len(encoding):
                continue

            known_vec = self._l2_normalize(user.face_encodings)
            dist = self._cosine_distance(target_vec, known_vec)

            if dist < RECOGNITION_COSINE_THRESHOLD:
                if best_match is None or dist < best_match[1]:
                    best_match = (user, dist)

        if best_match:
            matched_user, dist = best_match
            return UserOut(
                id=str(matched_user.id),
                name=matched_user.name,
                employee_id=matched_user.employee_id,
                access_level=matched_user.access_level,
            )

        return None