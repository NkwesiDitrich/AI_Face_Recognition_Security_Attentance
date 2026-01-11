# backend/app/domains/user/models.py

"""
User Domain Model
Represents the User entity in the system
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from bson import ObjectId


class User(BaseModel):
    """
    User domain model - represents a user in the face recognition system
    """

    # ✅ IMPORTANT: accept ObjectId from Mongo, but expose as string in responses
    id: Optional[Any] = Field(default=None, alias="_id")

    name: str = Field(..., min_length=1, description="User's full name")
    employee_id: str = Field(..., min_length=1, description="Unique employee ID")
    access_level: str = Field(default="employee", description="Access level")
    status: str = Field(default="active", description="User status: active or inactive")
    face_encodings: List[float] = Field(default_factory=list, description="Face encoding vector")
    # ✅ REMOVED: image_base64 - images should not be stored in database (unprofessional, storage inefficient)

    # ✅ Pydantic v2 config
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,  # allow ObjectId
        json_encoders={ObjectId: str},  # convert ObjectId -> string in JSON
    )

    def model_dump(self, **kwargs):
        """
        ✅ Ensure we never dump _id=None (so Mongo auto-generates one).
        """
        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True

        data = super().model_dump(**kwargs)

        # If _id exists but is None remove it
        if data.get("_id") is None:
            data.pop("_id", None)

        return data