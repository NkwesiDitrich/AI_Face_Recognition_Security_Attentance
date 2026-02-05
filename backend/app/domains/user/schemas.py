"""
User Schemas (Pydantic Models)
Used for request/response validation in FastAPI
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId


class UserCreate(BaseModel):
    """Schema for creating a new user (enrollment)"""
    name: str = Field(..., min_length=1, description="User's full name")
    employee_id: Optional[str] = Field(default=None, description="Unique employee ID (auto-generated if not provided)")
    access_level: str = Field(default="employee", description="Access level (employee, manager, admin)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "employee_id": "EMP001",
                "access_level": "employee"
            }
        }


class UserOut(BaseModel):
    """Schema for user response (output)"""
    id: str = Field(..., description="MongoDB ObjectId as string")
    name: str = Field(..., description="User's full name")
    employee_id: str = Field(..., description="Unique employee ID")
    access_level: str = Field(..., description="Access level")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "John Doe",
                "employee_id": "EMP001",
                "access_level": "employee"
            }
        }


class UserUpdate(BaseModel):
    """Schema for updating user information"""
    name: Optional[str] = Field(None, min_length=1, description="User's full name")
    employee_id: Optional[str] = Field(None, min_length=1, description="Unique employee ID")
    access_level: Optional[str] = Field(None, description="Access level")
    status: Optional[str] = Field(None, description="User status: active or inactive")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Jane Doe",
                "access_level": "manager"
            }
        }