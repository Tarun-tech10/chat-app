from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime
import json
import sqlite3
import uuid
import os

app = FastAPI()

# Enable CORS for React frontend
# Get allowed origins from environment variable, default to localhost for development
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
def init_db():
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# Pydantic models
class User(BaseModel):
    id: str
    username: str

class Message(BaseModel):
    id: str
    user_id: str
    username: str
    content: str
    timestamp: str

class MessageCreate(BaseModel):
    username: str
    content: str

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
    
    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
    
    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

manager = ConnectionManager()

# Database operations
def create_user(username: str) -> User:
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    
    user_id = str(uuid.uuid4())
    try:
        cursor.execute(
            "INSERT INTO users (id, username) VALUES (?, ?)",
            (user_id, username)
        )
        conn.commit()
        conn.close()
        return User(id=user_id, username=username)
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")

def get_or_create_user(username: str) -> User:
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    
    if user:
        conn.close()
        return User(id=user[0], username=user[1])
    else:
        conn.close()
        return create_user(username)

def save_message(user_id: str, username: str, content: str) -> Message:
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    
    message_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO messages (id, user_id, username, content) VALUES (?, ?, ?, ?)",
        (message_id, user_id, username, content)
    )
    conn.commit()
    
    cursor.execute(
        "SELECT id, user_id, username, content, timestamp FROM messages WHERE id = ?",
        (message_id,)
    )
    message_data = cursor.fetchone()
    conn.close()
    
    return Message(
        id=message_data[0],
        user_id=message_data[1],
        username=message_data[2],
        content=message_data[3],
        timestamp=message_data[4]
    )

def get_chat_history(limit: int = 50) -> List[Message]:
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, user_id, username, content, timestamp FROM messages ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    )
    messages = cursor.fetchall()
    conn.close()
    
    return [Message(
        id=msg[0],
        user_id=msg[1],
        username=msg[2],
        content=msg[3],
        timestamp=msg[4]
    ) for msg in reversed(messages)]

# API endpoints
@app.get("/")
async def root():
    return {"message": "Real-time Chat API"}

@app.post("/users", response_model=User)
async def register_user(username: str):
    return create_user(username)

@app.get("/users/{username}", response_model=User)
async def get_user(username: str):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(id=user[0], username=user[1])

@app.get("/messages", response_model=List[Message])
async def get_messages(limit: int = 50):
    return get_chat_history(limit)

# WebSocket endpoint
@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    # Get or create user
    user = get_or_create_user(username)
    
    await manager.connect(websocket, user.id)
    
    # Send chat history to the new user
    history = get_chat_history(20)
    await websocket.send_text(json.dumps({
        "type": "history",
        "messages": [msg.dict() for msg in history]
    }))
    
    # Notify others that user joined
    await manager.broadcast(json.dumps({
        "type": "user_joined",
        "username": username
    }))
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "message":
                content = message_data.get("content", "")
                if content.strip():
                    # Save message to database
                    message = save_message(user.id, username, content)
                    
                    # Broadcast to all connected clients
                    await manager.broadcast(json.dumps({
                        "type": "new_message",
                        "message": message.dict()
                    }))
    
    except WebSocketDisconnect:
        manager.disconnect(user.id)
        await manager.broadcast(json.dumps({
            "type": "user_left",
            "username": username
        }))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
