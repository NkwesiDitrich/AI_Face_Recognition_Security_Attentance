from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from app.domains.user.schemas import UserOut




app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# MongoDB CONNECTION
# -----------------------------
MONGO_URI = "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URI)
db = client["face_security"]
users_collection = db["users"]


# ------------------------------------------------------------
# UTIL: Convert MongoDB document to UserOut format
# ------------------------------------------------------------
def user_doc_to_out(doc) -> UserOut:
    return UserOut(
        id=str(doc["_id"]),
        name=doc["name"],
        employee_id=doc["employee_id"],
        access_level=doc.get("access_level", "employee")
    )


# ------------------------------------------------------------
# ROUTE: Create a new user
# ------------------------------------------------------------
@app.post("/users", response_model=UserOut)
async def create_user(data: UserCreate):
    # Convert UserCreate → User model
    new_user = User(**data.model_dump())

    result = await users_collection.insert_one(new_user.model_dump(by_alias=True))
    created = await users_collection.find_one({"_id": result.inserted_id})

    return user_doc_to_out(created)


# ------------------------------------------------------------
# ROUTE: Get all users
# ------------------------------------------------------------
@app.get("/users", response_model=List[UserOut])
async def get_all_users():
    docs = users_collection.find({})
    users = []
    async for d in docs:
        users.append(user_doc_to_out(d))
    return users


# ------------------------------------------------------------
# ROUTE: Get one user by ID
# ------------------------------------------------------------
@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    doc = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")

    return user_doc_to_out(doc)


# ------------------------------------------------------------
# ROUTE: Update user
# ------------------------------------------------------------
@app.put("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, data: UserCreate):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    update_data = {k: v for k, v in data.model_dump().items()}

    updated = await users_collection.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": update_data},
        return_document=True
    )

    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    return user_doc_to_out(updated)


# ------------------------------------------------------------
# ROUTE: Delete user
# ------------------------------------------------------------
@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await users_collection.delete_one({"_id": ObjectId(user_id)})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted successfully"}
