from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# ---- MongoDB Configuration (production-ready via env) ----
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGO_URL", "mongodb://localhost:27017/face_attendance_db")
DATABASE_NAME = os.getenv("DATABASE_NAME", "face_attendance_db")

# Global variables
client: Optional[AsyncIOMotorClient] = None
database = None


async def connect_to_mongo():
    """Initializes the MongoDB connection."""
    global client, database
    print("Connecting to MongoDB...")

    try:
        client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        await client.admin.command('ping')
        database = client.get_database(DATABASE_NAME)
        print("Successfully connected to MongoDB!")
    except Exception as e:
        print(f"❌ ERROR: Could not connect to MongoDB: {e}")
        safe_uri = MONGO_URI.split("@")[-1] if "@" in MONGO_URI else MONGO_URI
        print(f"   Check MONGO_URI. Host: {safe_uri[:60]}...")
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
