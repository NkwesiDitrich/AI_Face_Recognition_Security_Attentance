"""
Script to create the first admin user
Run this script once to create an initial admin account
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.domains.admin.models import Admin

MONGO_DETAILS = "mongodb://localhost:27017"
DATABASE_NAME = "face_attendance_db"


async def create_admin():
    """Create the first admin user"""
    client = AsyncIOMotorClient(MONGO_DETAILS)
    db = client[DATABASE_NAME]
    collection = db["admins"]
    
    # Check if any admin exists
    existing = await collection.find_one({})
    if existing:
        print("⚠️  Admin user already exists. Use the login page instead.")
        return
    
    # Get admin details from user
    print("=" * 50)
    print("Creating First Admin User")
    print("=" * 50)
    
    email = input("Enter admin email: ").strip()
    name = input("Enter admin name: ").strip()
    password = input("Enter admin password (min 6 characters): ").strip()
    role = input("Enter role (super_admin/admin/viewer) [default: super_admin]: ").strip() or "super_admin"
    
    if len(password) < 6:
        print("❌ Password must be at least 6 characters")
        return
    
    # Check if email already exists
    existing_email = await collection.find_one({"email": email})
    if existing_email:
        print(f"❌ Email {email} already exists")
        return
    
    # Create admin
    admin = Admin(
        email=email,
        name=name,
        password_hash=Admin.hash_password(password),
        role=role,
        is_active=True
    )
    
    admin_dict = admin.model_dump(by_alias=True, exclude={"id"})
    result = await collection.insert_one(admin_dict)
    
    print(f"\n✅ Admin user created successfully!")
    print(f"   ID: {result.inserted_id}")
    print(f"   Email: {email}")
    print(f"   Name: {name}")
    print(f"   Role: {role}")
    print(f"\nYou can now login at the admin dashboard.")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(create_admin())
