from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import asyncio

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
        client = AsyncIOMotorClient(MONGO_DETAILS, serverSelectionTimeoutMS=5000)
        # Test the connection
        await client.admin.command('ping')
        database = client.get_database(DATABASE_NAME)
        print("Successfully connected to MongoDB!")
    except Exception as e:
        print(f"❌ ERROR: Could not connect to MongoDB: {e}")
        print(f"   Make sure MongoDB is running on {MONGO_DETAILS}")
        print(f"   Start MongoDB service or run: mongod")
        raise  # Re-raise to stop server if MongoDB is not available


async def close_mongo_connection():
    """Closes the MongoDB connection gracefully."""
    global client
    if client:
        try:
            # Close the connection gracefully (synchronous operation, very fast)
            # Motor's close() is non-blocking and safe to call
            client.close()
            print("MongoDB connection closed.")
        except asyncio.CancelledError:
            # If cancelled during reload, just close without waiting
            if client:
                client.close()
            raise  # Re-raise to allow proper cleanup
        except Exception as e:
            # Ignore other errors during shutdown - connection might already be closed
            print(f"⚠️ Error closing MongoDB connection (non-critical): {e}")
        finally:
            client = None


def get_database():
    """Returns database instance for repositories."""
    return database
