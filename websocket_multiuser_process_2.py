import os
import asyncio
import subprocess
import threading
import time
import json

import polars as pl
from polars.exceptions import ComputeError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from starlette.websockets import WebSocketState

app = FastAPI()

class ProcessManager:
    """Class to manage processes and associated user sessions"""

    def __init__(self):
        self.processes = {}

    def start_process(self, process_key: str, file_name: str, file_folder: str):
        """Start the subprocess if not already running"""
        if process_key not in self.processes:
            process = subprocess.Popen(["nohup", "python", "main.py", file_name, file_folder])
            self.processes[process_key] = {
                "process": process,
                "sessions": []
            }
            print(f"Started process {process_key} with PID: {process.pid}")

    def stop_process(self, process_key: str):
        """Stop the subprocess if no more sessions are using it"""
        if process_key in self.processes:
            if len(self.processes[process_key]["sessions"]) == 0:
                process = self.processes[process_key]["process"]
                print(f"Killing process {process_key} with PID: {process.pid}")
                process.kill()
                del self.processes[process_key]

    def add_session(self, process_key: str, session: 'UserSession'):
        """Add a session to the process"""
        if process_key in self.processes:
            self.processes[process_key]["sessions"].append(session)

    def remove_session(self, process_key: str, session: 'UserSession'):
        """Remove a session from the process"""
        if process_key in self.processes:
            self.processes[process_key]["sessions"].remove(session)
            self.stop_process(process_key)


class UserSession:
    """Class to manage the data sending for each user"""

    def __init__(self, websocket: WebSocket, process_key: str):
        self.websocket = websocket
        self.process_key = process_key
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


class ConnectionManager:
    """Class defining socket events"""

    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            user_session = self.active_connections[websocket]
            process_key = user_session.process_key
            process_manager.remove_session(process_key, user_session)
            user_session.disconnect()
            del self.active_connections[websocket]


manager = ConnectionManager()
process_manager = ProcessManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            message = await websocket.receive_text()
            file_info = json.loads(message)
            req_from_id = file_info.get("req_from_id")
            req_to_id = file_info.get("req_to_id")
            offset = file_info.get("offset", 5)
            process_key = f"{req_from_id}-{req_to_id}"

            if not req_from_id or not req_to_id:
                print("Missing req_from_id or req_to_id in received data")
                await websocket.send_text(json.dumps({"error": "Missing req_from_id or req_to_id in received data"}))
                continue

            file_name = f"{req_from_id}-{req_to_id}.csv"
            file_path = os.path.join("path_to_your_files", file_name)  # Replace "path_to_your_files" with the actual path

            if websocket in manager.active_connections:
                user_session = manager.active_connections[websocket]
                if user_session.process_key != process_key:
                    process_manager.remove_session(user_session.process_key, user_session)
                    user_session.process_key = process_key
            else:
                user_session = UserSession(websocket, process_key)
                manager.active_connections[websocket] = user_session

            process_manager.start_process(process_key, file_name, "path_to_your_files")
            process_manager.add_session(process_key, user_session)
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
            <input type="text" id="req_from_id" placeholder="Enter req_from_id" />
            <input type="text" id="req_to_id" placeholder="Enter req_to_id" />
            <input type="number" id="offset" placeholder="Enter offset (default 5)" />
            <button onclick="connectWebSocket()">Connect</button>
            <pre id="output"></pre>
            <script>
                var ws;

                function connectWebSocket() {
                    var req_from_id = document.getElementById("req_from_id").value;
                    var req_to_id = document.getElementById("req_to_id").value;
                    var offset = document.getElementById("offset").value || 5;

                    if (ws) {
                        ws.close();
                    }
                    ws = new WebSocket(`ws://127.0.0.1:8000/ws`);

                    ws.onopen = function(event) {
                        ws.send(JSON.stringify({req_from_id: req_from_id, req_to_id: req_to_id, offset: offset}));
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
