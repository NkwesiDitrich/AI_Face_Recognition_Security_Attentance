from deepface import DeepFace
from typing import Any, Dict

# Global dictionary to store model references
ai_model: Dict[str, Any] = {}


async def load_ai_models():
    """Loads the necessary AI models into memory (DeepFace, Liveness, etc.)."""
    global ai_model
    print("Loading AI Models...")

    try:
        # We tell DeepFace what recognition model we will use.
        # Actual model will be lazy-loaded on first recognition request.
        ai_model["recognition_model_name"] = "VGG-Face"

        # Placeholder for liveness model
        # ai_model["liveness"] = load_tensorflow_model("liveness_model.h5")

        print("DeepFace models configured successfully.")

    except Exception as e:
        print(f"Error loading AI models: {e}")


async def get_ai_model():
    """Returns the AI model configuration/instance."""
    return ai_model
