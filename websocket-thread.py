import os
import asyncio
import subprocess
import threading
import polars as pl
from polars.exceptions import ComputeError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json
from starlette.websockets import WebSocketState

app = FastAPI()

class UserSession:
    """Class to manage the process and data sending for each user"""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.process = None
        self.thread = None
        self.thread_flag = False

    def start_process(self, file_name: str, file_folder: str):
        """Start the subprocess"""
        if self.process:
            self.kill_process()

        self.process = subprocess.Popen(["nohup", "python", "main.py", file_name, file_folder])
        print(f"Started process with PID: {self.process.pid}")

    def kill_process(self):
        """Kill the subprocess"""
        if self.process:
            print(f"Killing process with PID: {self.process.pid}")
            self.process.kill()
            self.process = None

    def start_thread(self, file_path: str):
        """Start the data sending thread"""
        if self.thread:
            self.thread_flag = False
            self.thread.join()

        self.thread_flag = True
        self.thread = threading.Thread(target=self.send_file_data, args=(file_path,))
        self.thread.start()

    def stop_thread(self):
        """Stop the data sending thread"""
        if self.thread:
            self.thread_flag = False
            self.thread.join()
            self.thread = None

    def send_file_data(self, file_path: str):
        """Read file and send data via WebSocket"""
        while self.thread_flag:
            try:
                print("Sending data")
                json_data = json.dumps({})
                if os.path.isfile(file_path):
                    try:
                        df = pl.read_csv(file_path)
                        df = df.with_columns([
                            pl.col(column).apply(lambda x: None if x is None or (isinstance(x, float) and x != x) else x)
                            for column in df.columns
                        ])
                        if df.is_empty():
                            json_data = json.dumps({})
                        else:
                            data = df.to_dict(as_series=False)
                            json_data = json.dumps(data)
                    except ComputeError:
                        json_data = json.dumps({})
                asyncio.run(self.send_personal_message(json_data))
                time.sleep(2)
            except WebSocketDisconnect:
                print(f"WebSocket disconnect detected for file {file_path}")
                self.stop_thread()
                break
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                self.stop_thread()
                break

    async def send_personal_message(self, message: str):
        """Send a message via WebSocket"""
        try:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(message)
            else:
                self.disconnect()
        except Exception as e:
            print(f"Exception while sending data: {e}")
            self.disconnect()

    def disconnect(self):
        """Clean up on disconnect"""
        self.stop_thread()
        self.kill_process()


class ConnectionManager:
    """Class defining socket events"""

    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = UserSession(websocket)

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections[websocket].disconnect()
            del self.active_connections[websocket]


manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    user_session = manager.active_connections[websocket]

    try:
        while True:
            message = await websocket.receive_text()
            file_info = json.loads(message)
            file_folder = file_info.get("fileFolder")
            file_name = file_info.get("fileName")

            if not file_folder or not file_name:
                print("Missing fileFolder or fileName in received data")
                await user_session.send_personal_message(json.dumps({"error": "Missing fileFolder or fileName in received data"}))
                continue

            file_path = os.path.join(file_folder, file_name)
            user_session.start_process(file_name, file_folder)
            user_session.start_thread(file_path)
    except WebSocketDisconnect:
        print("WebSocket disconnect detected")
    finally:
        await manager.disconnect(websocket)

@app.get("/")
async def get():
    return HTMLResponse("""
    <html>
        <head>
            <title>WebSocket File Streaming</title>
        </head>
        <body>
            <h1>WebSocket File Streaming</h1>
            <input type="text" id="fileFolder" placeholder="Enter file folder (e.g., files)" />
            <input type="text" id="fileName" placeholder="Enter file name (e.g., abc.csv)" />
            <button onclick="connectWebSocket()">Connect</button>
            <pre id="output"></pre>
            <script>
                var ws;

                function connectWebSocket() {
                    var fileFolder = document.getElementById("fileFolder").value;
                    var fileName = document.getElementById("fileName").value;

                    if (ws) {
                        ws.close();
                    }
                    ws = new WebSocket(`ws://127.0.0.1:8000/ws`);

                    ws.onopen = function(event) {
                        ws.send(JSON.stringify({fileFolder: fileFolder, fileName: fileName}));
                    };

                    ws.onmessage = function(event) {
                        try {
                            document.getElementById("output").textContent = JSON.stringify(JSON.parse(event.data), null, 2);
                        } catch (e) {
                            console.error("Invalid JSON received", e);
                        }
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
