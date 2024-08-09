import streamlit as st
import pandas as pd
import gitlab
import os
import subprocess

# Hard-coded repository details
REPO_URL = "https://gitlab.com/namma-group1/File_Editor.git"
REPO_DIR = "/path/to/your/cloned/repo"  # Update this path to your local cloned repo
USERNAME = "your_username"
TOKEN = "your_token"

# Helper class to manage Git and CSV operations
class GitCSVEditor:
    def __init__(self, repo_dir, filename):
        self.repo_dir = repo_dir
        self.filename = filename
        self.filepath = os.path.join(self.repo_dir, self.filename)
        self.df = pd.read_csv(self.filepath)

    def run_git_command(self, command):
        try:
            result = subprocess.run(command, cwd=self.repo_dir, capture_output=True, text=True, check=True)
            return result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            return None, e.stderr

    def get_dataframe(self):
        return self.df

    def save_changes(self, new_data):
        self.df = pd.DataFrame(new_data)
        self.df.to_csv(self.filepath, index=False)
        # Ensure the file system recognizes the changes
        self.df = pd.read_csv(self.filepath)

    def add_and_commit_changes(self):
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
        else:
            st.write(stdout)

    def push_changes(self):
        stdout, stderr = self.run_git_command(["git", "push", "origin", "HEAD"])
        if stderr:
            st.error(f"Error pushing changes: {stderr}")
        else:
            st.success("Changes pushed to the repository.")
            st.write(stdout)

# Function to fetch branches
def fetch_branches(repo_url, username, token):
    st.write("Fetching branches...")
    project_path = '/'.join(repo_url.split('/')[-2:]).replace('.git', '')
    st.write(f"Project path: {project_path}")
    gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
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

# Streamlit app layout
st.title("CSV File Editor with GitLab Integration")

# Hard-coded repository details
st.write(f"Repository URL: {REPO_URL}")
st.write(f"Local Repository Path: {REPO_DIR}")
st.write(f"GitLab Username: {USERNAME}")

# Fetch branches
branches = fetch_branches(REPO_URL, USERNAME, TOKEN)
if not branches:
    st.error("No branches found or failed to fetch branches.")
else:
    selected_branch = st.selectbox("Select Branch", [""] + branches)

    if selected_branch and switch_branch(REPO_DIR, selected_branch):
        csv_files = [f for f in os.listdir(REPO_DIR) if f.endswith('.csv')]
        if not csv_files:
            st.error("No CSV files found in the selected branch.")
        else:
            selected_file = st.selectbox("Select CSV File", csv_files)
            if selected_file:
                editor = GitCSVEditor(REPO_DIR, selected_file)
                df = editor.get_dataframe()
                st.write("Edit the CSV data below:")
                edited_df = st.data_editor(df)

                # Save button
                if st.button("Save"):
                    editor.save_changes(edited_df)
                    st.success("File saved successfully.")

                # Add and Commit button
                if st.button("Add and Commit"):
                    editor.add_and_commit_changes()
                    st.success("Changes added and committed successfully.")

                # Push button
                if st.button("Push"):
                    editor.push_changes()
