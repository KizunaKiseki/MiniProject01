from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from typing import List
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import shutil
import tempfile

app = FastAPI()

UPLOAD_DIR = Path(tempfile.gettempdir() ) / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# CORS is only for HTTP, not WS, but fine to keep
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/images", StaticFiles(directory=UPLOAD_DIR), name="images")

@app.get("/")
async def root():
    return {"message": "FastAPI WebSocket chat server is running"}

# ? POST /upload-photo
@app.post("/upload-photo")
def upload_photo(file: UploadFile = File(...)):
    image_types = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    
    extension = image_types.get(file.content_type)
    
    if extension is None:
        file.file.close()
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    filename = f"photo_{uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / filename
    
    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save file")
    
    finally:
        file.file.close()
        
    uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()
    
    data = {
        "filename": filename,
        "url": f"/images/{filename}",
        "uploaded_at": uploaded_at
    }
        
    return JSONResponse(content=data, status_code=201)


# ? GET /photos
@app.get("/photos")
def get_photos():
    photos = []
    
    for file_path in UPLOAD_DIR.iterdir():
        if not file_path.is_file():
            continue
        
        if file_path.suffix.lower() not in [".jpg", ".png", ".webp"]:
            continue
        
        uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()
        
        data = {
            "filename": file_path.name,
            "url": f"/images/{file_path.name}",
            "uploaded_at": uploaded_at
        }
        
        photos.append(data)

    return photos


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        # Send the message to all connected clients
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                print("Error sending to a client:", e)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received from client: {data}")

            # Broadcast whatever text we got (we'll send JSON from the frontend)
            await manager.broadcast(data)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print("Unexpected error in websocket:", e)
        manager.disconnect(websocket)
        try:
            await websocket.close()
        except:
            pass

