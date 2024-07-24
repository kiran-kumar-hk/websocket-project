from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from git import Repo
import pandas as pd
import tempfile
import os
import shutil
import io

app = FastAPI()

# Global variable to keep track of the GitCSVEditor instance
editor = None


class GitCSVEditor:
    def __init__(self, repo_url, branch_name, filename):
        self.repo_url = repo_url
        self.branch_name = branch_name
        self.filename = filename
        self.repo_dir = tempfile.mkdtemp()
        self.repo = Repo.clone_from(self.repo_url, self.repo_dir)
        self.repo.git.checkout(self.branch_name)
        self.filepath = os.path.join(self.repo_dir, self.filename)
        self.df = pd.read_csv(self.filepath)

    def get_dataframe(self):
        return self.df

    def save_changes(self, new_data):
        self.df = pd.DataFrame(new_data)
        self.df.to_csv(self.filepath, index=False)

    def push_changes(self):
        self.repo.index.add([self.filepath])
        self.repo.index.commit("Updated CSV file")
        origin = self.repo.remote(name='origin')
        origin.push()


class CSVData(BaseModel):
    data: list


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse("""
    <html>
        <head>
            <title>CSV Editor</title>
        </head>
        <body>
            <h1>CSV Editor</h1>
            <form action="/clone" method="post">
                <label for="repoUrl">Repository URL:</label>
                <input type="text" id="repoUrl" name="repoUrl" required>
                <br>
                <label for="branchName">Branch Name:</label>
                <input type="text" id="branchName" name="branchName" required>
                <br>
                <label for="filename">CSV Filename:</label>
                <input type="text" id="filename" name="filename" required>
                <br>
                <input type="submit" value="Clone Repository">
            </form>

            <h2>Edit CSV Data</h2>
            <form action="/get-data" method="get">
                <input type="submit" value="Load Data">
            </form>

            <form action="/save" method="post">
                <textarea name="data" id="data" rows="10" cols="50" placeholder="Edit CSV data here" required></textarea>
                <br>
                <input type="submit" value="Save Changes">
            </form>

            <form action="/push" method="post">
                <input type="submit" value="Push Changes">
            </form>
        </body>
    </html>
    """)


@app.post("/clone")
async def clone_repo(repoUrl: str = Form(...), branchName: str = Form(...), filename: str = Form(...)):
    global editor
    try:
        editor = GitCSVEditor(repoUrl, branchName, filename)
        return JSONResponse(content={"message": "Repository cloned and branch checked out successfully."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-data")
async def get_data():
    global editor
    try:
        if editor is None:
            raise HTTPException(status_code=400, detail="Editor not initialized.")

        df = editor.get_dataframe()
        csv_data = df.to_csv(index=False)
        return HTMLResponse(content=f"""
        <html>
            <body>
                <h2>Edit CSV Data</h2>
                <form action="/save" method="post">
                    <textarea name="data" id="data" rows="10" cols="50" required>{csv_data}</textarea>
                    <br>
                    <input type="submit" value="Save Changes">
                </form>
                <form action="/push" method="post">
                    <input type="submit" value="Push Changes">
                </form>
            </body>
        </html>
        """)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/save")
async def save_data(data: str = Form(...)):
    global editor
    try:
        if editor is None:
            raise HTTPException(status_code=400, detail="Editor not initialized.")

        df = pd.read_csv(io.StringIO(data))
        editor.save_changes(df.to_dict(orient='records'))
        return JSONResponse(content={"message": "Changes saved successfully."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/push")
async def push_data():
    global editor
    try:
        if editor is None:
            raise HTTPException(status_code=400, detail="Editor not initialized.")

        editor.push_changes()
        return JSONResponse(content={"message": "Changes pushed successfully."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Cleanup temporary directory
@app.on_event("shutdown")
def cleanup():
    global editor
    if editor and os.path.exists(editor.repo_dir):
        shutil.rmtree(editor.repo_dir)

# Run the app with: uvicorn app:app --reload
