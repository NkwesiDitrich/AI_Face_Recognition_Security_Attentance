from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional

# ---- MongoDB Configuration ----
MONGO_DETAILS = "mongodb://localhost:27017"   # Replace if using Atlas
DATABASE_NAME = "face_attendance_db"

# Global variables
client: Optional[AsyncIOMotorClient] = None
database = None


async def connect_to_mongo():
    """Initializes the MongoDB connection."""
    global client, database
    print("Connecting to MongoDB...")

    try:
        client = AsyncIOMotorClient(MONGO_DETAILS)
        database = client.get_database(DATABASE_NAME)
        print("Successfully connected to MongoDB!")
    except Exception as e:
        print(f"Could not connect to MongoDB: {e}")


async def close_mongo_connection():
    """Closes the MongoDB connection."""
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")


def get_database():
    """Returns database instance for repositories."""
    return database
