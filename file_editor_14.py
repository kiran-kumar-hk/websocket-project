import streamlit as st
import os
import subprocess
import tempfile
import shutil
import sys
import atexit
import gitlab
import pandas as pd
import glob
from datetime import datetime

# Hard-coded repository details
REPO_URL = "http://scgh/fip/irsvr/resource.git"
USERNAME = "your_username"
TOKEN = "your_token"

def cleanup():
    if 'repo_dir' in st.session_state and os.path.exists(st.session_state.repo_dir):
        shutil.rmtree(st.session_state.repo_dir)
        del st.session_state.repo_dir
    st.write("Cleanup completed.")

atexit.register(cleanup)

# Function to create and clone repository into a local directory with timestamp
def clone_repo(repo_url, username, token, branch_name):
    cleanup()  # Ensure cleanup before cloning a new repo
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    local_dir = f"repo_{timestamp}"
    os.makedirs(local_dir, exist_ok=True)
    repo_url_with_auth = f"http://{username}:{token}@{repo_url.split('http://')[-1]}"
    try:
        subprocess.run(["git", "clone", "--branch", branch_name, repo_url_with_auth, local_dir], check=True)
        return local_dir
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to clone repository: {e.stderr}")
        return None

# Function to fetch branches
def fetch_branches(repo_url, username, token):
    st.write("Fetching branches...")
    project_path = '/'.join(repo_url.split('/')[-2:]).replace('.git', '')
    gl = gitlab.Gitlab('http://scgh/fip/irsvr', private_token=token)
    gl.auth()
    try:
        project = gl.projects.get(project_path)
        branches = [branch.name for branch in project.branches.list()]
        return branches
    except gitlab.exceptions.GitlabAuthenticationError as e:
        st.error(f"Authentication error: {e}")
        return []
    except gitlab.exceptions.GitlabGetError as e:
        st.error(f"Failed to fetch branches: {e}")
        return []
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        return []

# Helper class to manage Git and CSV operations
class GitCSVEditor:
    def __init__(self, repo_dir, filename):
        self.repo_dir = repo_dir
        self.filename = filename
        self.filepath = os.path.join(self.repo_dir, self.filename)
        self.df = pd.read_csv(self.filepath, header=None)
        self.has_header = pd.read_csv(self.filepath).columns.str.match('Unnamed').any()

    def run_git_command(self, command):
        try:
            result = subprocess.run(command, cwd=self.repo_dir, capture_output=True, text=True, check=True)
            return result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            return None, e.stderr

    def get_dataframe(self):
        return self.df

    def save_changes(self, new_data):
        header = None if self.has_header else False
        self.df = pd.DataFrame(new_data)
        self.df.to_csv(self.filepath, index=False, header=header)
        # Ensure the file system recognizes the changes
        self.df = pd.read_csv(self.filepath)

    def add_commit_push_changes(self):
        # Add the changes
        stdout, stderr = self.run_git_command(["git", "add", self.filename])
        if stderr:
            st.error(f"Error adding file: {stderr}")
            return

        # Check for changes before committing
        stdout, stderr = self.run_git_command(["git", "status", "--porcelain"])
        if stderr:
            st.error(f"Error checking status: {stderr}")
            return
        if not stdout.strip():
            st.info("No changes to commit.")
            return

        # Commit the changes
        stdout, stderr = self.run_git_command(["git", "commit", "-m", "Updated CSV file"])
        if stderr:
            st.error(f"Error committing changes: {stderr}")
            return

        # Push the changes
        stdout, stderr = self.run_git_command(["git", "push", "origin", "HEAD"])
        if stderr:
            # Check if stderr contains expected informational messages
            if "View merge request for" in stderr or "Changes pushed successfully" in stderr or "To http://scgh/fip/irsvr/resource.git" in stderr:
                st.success("Changes pushed to the repository.")
                st.write(stderr)
            else:
                st.error(f"Error pushing changes: {stderr}")
        else:
            st.success("Changes pushed to the repository.")
            st.write(stdout)

# Streamlit app layout
st.title("CSV File Editor with GitLab Integration")

# Hard-coded repository details
st.write(f"Repository URL: {REPO_URL}")
st.write(f"GitLab Username: {USERNAME}")

# Fetch branches
branches = fetch_branches(REPO_URL, USERNAME, TOKEN)
if not branches:
    st.error("No branches found or failed to fetch branches.")
else:
    selected_branch = st.selectbox("Select Branch", [""] + branches, index=branches.index("resource_editor") + 1 if "resource_editor" in branches else 0)

    if selected_branch:
        if 'repo_dir' not in st.session_state or st.session_state.repo_dir is None:
            repo_dir = clone_repo(REPO_URL, USERNAME, TOKEN, selected_branch)
            if repo_dir:
                st.session_state.repo_dir = repo_dir
                st.write(f"Repository cloned to: {repo_dir}")
        else:
            repo_dir = st.session_state.repo_dir
            st.write(f"Repository cloned to: {repo_dir}")

        csv_files = glob.glob(os.path.join(repo_dir, "**/*.csv"), recursive=True)
        csv_files = [os.path.relpath(file, repo_dir) for file in csv_files]
        if not csv_files:
            st.error("No CSV files found in the selected branch.")
        else:
            selected_file = st.selectbox("Select CSV File", csv_files)
            if selected_file:
                editor = GitCSVEditor(repo_dir, selected_file)
                df = editor.get_dataframe()
                st.write("Edit the CSV data below:")
                edited_df = st.data_editor(df)

                # Save button
                if st.button("Save"):
                    editor.save_changes(edited_df)
                    st.success("File saved successfully.")

                # Push button (merged with add and commit)
                if st.button("Add, Commit, and Push"):
                    editor.save_changes(edited_df)
                    editor.add_commit_push_changes()
