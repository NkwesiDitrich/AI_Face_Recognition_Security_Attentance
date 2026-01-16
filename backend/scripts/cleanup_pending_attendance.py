"""
Script to clean up old attendance records with "pending" liveness status.
These are records created before the fix that prevented creating records for failed liveness.
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_DETAILS = "mongodb://localhost:27017"
DATABASE_NAME = "face_attendance_db"

async def cleanup_pending_records():
    """Remove all attendance records with 'pending' liveness status or invalid liveness values"""
    client = AsyncIOMotorClient(MONGO_DETAILS)
    db = client[DATABASE_NAME]
    collection = db["attendance_logs"]
    
    # Check for records with "pending" liveness
    pending_count = await collection.count_documents({"liveness": "pending"})
    print(f"Found {pending_count} attendance records with 'pending' liveness status")
    
    # Check for records with missing liveness field
    missing_liveness_count = await collection.count_documents({"liveness": {"$exists": False}})
    print(f"Found {missing_liveness_count} attendance records with missing 'liveness' field")
    
    # Check for records with invalid/null/empty liveness values
    invalid_count = await collection.count_documents({
        "$or": [
            {"liveness": None},
            {"liveness": ""},
            {"liveness": {"$nin": ["passed", "failed"]}}
        ]
    })
    print(f"Found {invalid_count} attendance records with invalid/null/empty liveness values")
    
    total_to_delete = pending_count + missing_liveness_count + invalid_count
    
    if total_to_delete == 0:
        print("[OK] No records to clean up!")
        client.close()
        return 0
    
    # Delete all records with "pending" liveness
    result1 = await collection.delete_many({"liveness": "pending"})
    
    # Delete all records with missing liveness field
    result2 = await collection.delete_many({"liveness": {"$exists": False}})
    
    # Delete all records with invalid/null/empty liveness values (excluding "passed" and "failed")
    result3 = await collection.delete_many({
        "$or": [
            {"liveness": None},
            {"liveness": ""},
            {"liveness": {"$nin": ["passed", "failed"]}}
        ]
    })
    
    total_deleted = result1.deleted_count + result2.deleted_count + result3.deleted_count
    print(f"[OK] Cleaned up {total_deleted} attendance records:")
    print(f"   - {result1.deleted_count} records with 'pending' liveness")
    print(f"   - {result2.deleted_count} records with missing 'liveness' field")
    print(f"   - {result3.deleted_count} records with invalid/null/empty liveness")
    client.close()
    return total_deleted

if __name__ == "__main__":
    try:
        deleted = asyncio.run(cleanup_pending_records())
        print(f"\n[OK] Cleanup complete. Deleted {deleted} records.")
    except Exception as e:
        print(f"\n[ERROR] Error during cleanup: {e}")
        print("Make sure MongoDB is running on mongodb://localhost:27017")
        sys.exit(1)
