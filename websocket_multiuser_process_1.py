import os
import asyncio
import subprocess
import threading
import time
from typing import Tuple, Dict

import polars as pl
from polars.exceptions import ComputeError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json

from starlette.websockets import WebSocketState

app = FastAPI()

class UserSession:
    """Class to manage the process and data sending for each user"""

    def __init__(self, websocket: WebSocket, file_key: str):
        self.websocket = websocket
        self.file_key = file_key
        self.thread = None
        self.thread_flag = False

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
                else:
                    json_data = json.dumps({})
                
                asyncio.run(self.send_personal_message(json_data))
                time.sleep(5)  # Sleep for 5 seconds
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
        manager.disconnect(self.websocket)

class ConnectionManager:
    """Class defining socket events"""

    def __init__(self):
        self.active_connections: Dict[WebSocket, UserSession] = {}
        self.processes: Dict[str, Tuple[subprocess.Popen, int]] = {}

    async def connect(self, websocket: WebSocket, file_key: str):
        await websocket.accept()
        user_session = UserSession(websocket, file_key)
        self.active_connections[websocket] = user_session
        self.increment_process_ref_count(file_key)

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            user_session = self.active_connections[websocket]
            file_key = user_session.file_key
            self.decrement_process_ref_count(file_key)
            user_session.disconnect()
            del self.active_connections[websocket]

    def increment_process_ref_count(self, file_key: str):
        if file_key not in self.processes:
            process = subprocess.Popen(["nohup", "python", "main.py", file_key.split(":")[1], file_key.split(":")[0], "--offset", "5"])
            self.processes[file_key] = (process, 1)
            print(f"Started process {process.pid} for {file_key}")
        else:
            process, ref_count = self.processes[file_key]
            self.processes[file_key] = (process, ref_count + 1)
            print(f"Incremented ref count for {file_key} to {ref_count + 1}")

    def decrement_process_ref_count(self, file_key: str):
        if file_key in self.processes:
            process, ref_count = self.processes[file_key]
            if ref_count == 1:
                print(f"Killing process {process.pid} for {file_key}")
                process.kill()
                del self.processes[file_key]
            else:
                self.processes[file_key] = (process, ref_count - 1)
                print(f"Decremented ref count for {file_key} to {ref_count - 1}")

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        while True:
            message = await websocket.receive_text()
            file_info = json.loads(message)
            file_folder = file_info.get("fileFolder")
            file_name = file_info.get("fileName")

            if not file_folder or not file_name:
                print("Missing fileFolder or fileName in received data")
                await manager.active_connections[websocket].send_personal_message(json.dumps({"error": "Missing fileFolder or fileName in received data"}))
                continue

            file_key = f"{file_folder}:{file_name}"
            await manager.connect(websocket, file_key)
            user_session = manager.active_connections[websocket]
            file_path = os.path.join(file_folder, file_name)
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
