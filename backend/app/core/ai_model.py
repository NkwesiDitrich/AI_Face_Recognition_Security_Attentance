# backend/app/core/ai_model.py

from deepface import DeepFace
from typing import Any, Dict

# Global dictionary to store model references
ai_model: Dict[str, Any] = {}


def load_ai_models():
    """Loads the necessary AI models into memory (DeepFace, Liveness, etc.)."""
    global ai_model
    print("Loading AI Models...")

    try:
        # Pre-load the 'Emotion' model used for liveness check
        print("Pre-loading DeepFace Emotion model...")
        ai_model["emotion_model"] = DeepFace.build_model('Emotion')
        print("DeepFace Emotion model loaded.")

        # Pre-load the 'ArcFace' model used for recognition
        # ArcFace is more robust than VGG-Face for security systems
        print("Pre-loading DeepFace ArcFace model...")
        ai_model["recognition_model"] = DeepFace.build_model('ArcFace')
        ai_model["recognition_model_name"] = "ArcFace"
        print("DeepFace ArcFace model loaded.")

        print("All DeepFace models configured successfully.")

    except Exception as e:
        print(f"Error loading AI models: {e}")


async def get_ai_model():
    """Returns the AI model configuration/instance."""
    return ai_model