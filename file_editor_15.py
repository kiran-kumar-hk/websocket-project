import streamlit as st
import os
import subprocess
import shutil
import gitlab
import pandas as pd
import glob
import json
from datetime import datetime
import atexit

# Hard-coded repository details
REPO_URL = "http://scgh/fip/irsvr/resource.git"
USERNAME = "your_username"
TOKEN = "your_token"

# Load configuration file
with open('config.json', 'r') as f:
    config = json.load(f)


# Function to create and clone repository into a local directory with timestamp
def clone_repo(repo_url, username, token, branch_name):
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


# Function to switch branch
def switch_branch(repo_dir, branch_name):
    try:
        subprocess.run(["git", "checkout", branch_name], cwd=repo_dir, check=True)
        subprocess.run(["git", "pull", "origin", branch_name], cwd=repo_dir, check=True)
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to switch to branch {branch_name}: {e.stderr}")
        return False
    return True


# Helper class to manage Git and CSV operations
class GitCSVEditor:
    def __init__(self, repo_dir, filename, config):
        self.repo_dir = repo_dir
        self.filename = filename
        self.filepath = os.path.join(self.repo_dir, self.filename)
        self.df = pd.read_csv(self.filepath, header=None if config.get(filename, 1) == 0 else 'infer')
        self.num_headers = config.get(filename, 1)

    def run_git_command(self, command):
        try:
            result = subprocess.run(command, cwd=self.repo_dir, capture_output=True, text=True, check=True)
            return result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            return None, e.stderr

    def get_dataframe(self):
        return self.df

    def save_changes(self, new_data):
        header = None if self.num_headers == 0 else list(range(self.num_headers))
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


# Ensure cleanup when the script exits
atexit.register(cleanup)


def cleanup():
    if 'repo_dir' in st.session_state and os.path.exists(st.session_state.repo_dir):
        shutil.rmtree(st.session_state.repo_dir)
        del st.session_state.repo_dir
    st.write("Cleanup completed.")


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
    selected_branch = st.selectbox("Select Branch", [""] + branches)

    if selected_branch:
        if 'repo_dir' not in st.session_state:
            repo_dir = clone_repo(REPO_URL, USERNAME, TOKEN, selected_branch)
            if repo_dir:
                st.session_state.repo_dir = repo_dir
                st.session_state.selected_branch = selected_branch
                st.write(f"Repository cloned to: {repo_dir}")
            else:
                st.session_state.repo_dir = None
        elif st.session_state.selected_branch != selected_branch:
            repo_dir = st.session_state.repo_dir
            if switch_branch(repo_dir, selected_branch):
                st.session_state.selected_branch = selected_branch
                st.write(f"Switched to branch: {selected_branch}")
            else:
                st.session_state.repo_dir = None

        if 'repo_dir' in st.session_state and st.session_state.repo_dir:
            csv_files = glob.glob(os.path.join(st.session_state.repo_dir, "**/*.csv"), recursive=True)
            csv_files = [os.path.relpath(file, st.session_state.repo_dir) for file in csv_files]
            if not csv_files:
                st.error("No CSV files found in the selected branch.")
            else:
                selected_file = st.selectbox("Select CSV File", csv_files)
                if selected_file:
                    editor = GitCSVEditor(st.session_state.repo_dir, selected_file, config)
                    df = editor.get_dataframe()

                    num_headers = config.get(selected_file, 1)
                    if num_headers > 0:
                        non_editable_headers = df.iloc[:num_headers]
                        editable_data = df.iloc[num_headers:]
                    else:
                        non_editable_headers = pd.DataFrame()
                        editable_data = df

                    st.write("Edit the CSV data below:")

                    # Display non-editable headers
                    if not non_editable_headers.empty:
                        st.dataframe(non_editable_headers)

                    # Edit the editable data
                    edited_data = st.text_area("Editable Data", value=editable_data.to_csv(index=False, header=False),
                                               height=200)
                    edited_df = pd.read_csv(pd.compat.StringIO(edited_data),
                                            header=None if num_headers == 0 else 'infer')

                    # Combine non-editable headers and edited data
                    if not non_editable_headers.empty:
                        new_df = pd.concat([non_editable_headers, edited_df], ignore_index=True)
                    else:
                        new_df = edited_df

                    # Save button
                    if st.button("Save"):
                        editor.save_changes(new_df)
                        st.success("File saved successfully.")

                    # Push button (merged with add and commit)
                    if st.button("Add, Commit, and Push"):
                        editor.save_changes(new_df)
                        editor.add_commit_push_changes()

# Ensure cloned folders are deleted daily using crontab settings
cron_job_command = "find /path/to/cloned/repos -type d -mtime +1 -exec rm -rf {} +"
subprocess.run(f'(crontab -l ; echo "0 0 * * * {cron_job_command}") | crontab -', shell=True)
