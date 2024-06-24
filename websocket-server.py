import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

class ConnectionManager:
    """Class defining socket events"""
    def __init__(self):
        """init method, keeping track of connections"""
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        """connect event"""
        await websocket.accept()
        self.active_connections.append(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Direct Message"""
        await websocket.send_text(message)

    def disconnect(self, websocket: WebSocket):
        """disconnect event"""
        self.active_connections.remove(websocket)

manager = ConnectionManager()

async def send_file_data(websocket: WebSocket, file_path: str):
    while True:
        if websocket not in manager.active_connections:
            break
        try:
            with open(file_path, 'r') as file:
                data = file.read()
            await manager.send_personal_message(data, websocket)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            break

@app.websocket("/ws/{file_name}")
async def websocket_endpoint(websocket: WebSocket, file_name: str):
    await manager.connect(websocket)
    file_path = os.path.join('files', file_name)
    try:
        await send_file_data(websocket, file_path)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        manager.disconnect(websocket)

@app.get("/")
async def get():
    return HTMLResponse("""
    <html>
        <head>
            <title>WebSocket File Streaming</title>
        </head>
        <body>
            <h1>WebSocket File Streaming</h1>
            <input type="text" id="fileName" placeholder="Enter file name (e.g., file1.txt)" />
            <button onclick="connectWebSocket()">Connect</button>
            <pre id="output"></pre>
            <script>
                var ws;
                function connectWebSocket() {
                    var fileName = document.getElementById("fileName").value;
                    ws = new WebSocket(`ws://127.0.0.1:8000/ws/${fileName}`);
                    ws.onmessage = function(event) {
                        document.getElementById("output").textContent = event.data;
                    };
                    ws.onclose = function(event) {
                        alert("WebSocket connection closed");
                    };
                }
            </script>
        </body>
    </html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
