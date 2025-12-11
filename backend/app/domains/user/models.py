# backend/app/domains/user/models.py

"""
User Domain Model
Represents the User entity in the system
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId


class User(BaseModel):
    """
    User domain model - represents a user in the face recognition system
    """
    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId")
    name: str = Field(..., min_length=1, description="User's full name")
    employee_id: str = Field(..., min_length=1, description="Unique employee ID")
    access_level: str = Field(default="employee", description="Access level")
    face_encodings: List[float] = Field(default_factory=list, description="Face encoding vector from DeepFace")
    image_base64: Optional[str] = Field(None, description="Base64 encoded image data for Admin display") # <-- NEW FIELD

    class Config:
        populate_by_name = True  # Allow both 'id' and '_id'
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439011",
                "name": "John Doe",
                "employee_id": "EMP001",
                "access_level": "employee",
                "face_encodings": [0.1, 0.2, 0.3, -0.1],
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwAAAAC"
            }
        }

    def dict(self, **kwargs):
        """Override dict to handle ObjectId serialization"""
        data = super().dict(**kwargs)
        if self.id and "_id" not in data:
            data["_id"] = self.id
        return data
