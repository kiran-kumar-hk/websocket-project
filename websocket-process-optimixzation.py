import os
import asyncio
import subprocess
import threading
import time

import polars as pl
from polars.exceptions import ComputeError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json

from starlette.websockets import WebSocketState

app = FastAPI()

class UserSession:
    """Class to manage the process and data sending for each user"""

    def __init__(self, websocket: WebSocket, file_name: str, file_folder: str):
        self.websocket = websocket
        self.file_name = file_name
        self.file_folder = file_folder
        self.file_path = os.path.join(file_folder, file_name)
        self.thread = None
        self.thread_flag = False

    def start_thread(self):
        """Start the data sending thread"""
        if self.thread:
            self.thread_flag = False
            self.thread.join()

        self.thread_flag = True
        self.thread = threading.Thread(target=self.send_file_data)
        self.thread.start()

    def stop_thread(self):
        """Stop the data sending thread"""
        if self.thread:
            self.thread_flag = False
            self.thread.join()
            self.thread = None

    def send_file_data(self):
        """Read file and send data via WebSocket"""
        while self.thread_flag:
            try:
                print("Sending data")
                json_data = json.dumps({})
                if os.path.isfile(self.file_path):
                    try:
                        df = pl.read_csv(self.file_path)
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
                print(f"WebSocket disconnect detected for file {self.file_path}")
                self.stop_thread()
                break
            except Exception as e:
                print(f"Error reading file {self.file_path}: {e}")
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
        manager.decrement_connection(self.file_name, self.file_folder, self.websocket)


class ConnectionManager:
    """Class defining socket events"""

    def __init__(self):
        self.active_connections = {}
        self.active_processes = {}
        self.lock = threading.Lock()

    async def connect(self, websocket: WebSocket, file_name: str, file_folder: str):
        await websocket.accept()
        file_key = (file_name, file_folder)
        session = UserSession(websocket, file_name, file_folder)

        with self.lock:
            if file_key not in self.active_processes:
                self.start_process(file_name, file_folder)
                self.active_processes[file_key] = {'process': None, 'ref_count': 0}
            self.active_processes[file_key]['ref_count'] += 1

        self.active_connections[websocket] = session
        session.start_thread()

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            session = self.active_connections[websocket]
            session.disconnect()
            del self.active_connections[websocket]

    def decrement_connection(self, file_name: str, file_folder: str, websocket: WebSocket):
        file_key = (file_name, file_folder)
        with self.lock:
            if file_key in self.active_processes:
                self.active_processes[file_key]['ref_count'] -= 1
                if self.active_processes[file_key]['ref_count'] == 0:
                    self.stop_process(file_key)

    def start_process(self, file_name: str, file_folder: str):
        file_key = (file_name, file_folder)
        process = subprocess.Popen(["nohup", "python", "main.py", file_name, file_folder])
        print(f"Started process for {file_key} with PID: {process.pid}")
        self.active_processes[file_key]['process'] = process

    def stop_process(self, file_key):
        process = self.active_processes[file_key]['process']
        if process:
            print(f"Stopping process for {file_key} with PID: {process.pid}")
            process.kill()
            self.active_processes[file_key]['process'] = None
        del self.active_processes[file_key]


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
                await websocket.send_text(json.dumps({"error": "Missing fileFolder or fileName in received data"}))
                continue

            await manager.connect(websocket, file_name, file_folder)
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
