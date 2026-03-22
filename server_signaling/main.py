from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List, Any
import json

app = FastAPI()

# rooms[room_id] = [websocket1, websocket2]
rooms: Dict[str, List[WebSocket]] = {}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    
    if room_id not in rooms:
        rooms[room_id] = []
    
    if len(rooms[room_id]) >= 2:
        await websocket.send_text(json.dumps({"type": "error", "message": "Room full"}))
        await websocket.close()
        return
        
    rooms[room_id].append(websocket)
    print(f"Client connected to room {room_id}. Total: {len(rooms[room_id])}")
    
    try:
        while True:
            data = await websocket.receive_text()
            # Broadcast to the other person in the room
            targets = [ws for ws in rooms[room_id] if ws != websocket]
            for target in targets:
                await target.send_text(data)
    except WebSocketDisconnect:
        if websocket in rooms[room_id]:
            rooms[room_id].remove(websocket)
        print(f"Client disconnected from room {room_id}. Remaining: {len(rooms[room_id])}")
        if not rooms[room_id]:
            del rooms[room_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
