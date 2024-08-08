import streamlit as st
import pandas as pd
import gitlab
import tempfile
import os
import shutil
import subprocess


# Helper class to manage Git and CSV operations
class GitCSVEditor:
    def __init__(self, repo_url, branch_name, filename, username, token):
        self.repo_url = repo_url
        self.branch_name = branch_name
        self.filename = filename
        self.username = username
        self.token = token
        self.repo_dir = tempfile.TemporaryDirectory()
        self.clone_repo()
        self.filepath = os.path.join(self.repo_dir.name, self.filename)
        self.df = pd.read_csv(self.filepath)

    def run_git_command(self, command):
        try:
            result = subprocess.run(command, cwd=self.repo_dir.name, capture_output=True, text=True, check=True)
            return result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            return None, e.stderr

    def clone_repo(self):
        repo_url_with_auth = f"https://{self.username}:{self.token}@{self.repo_url.split('https://')[-1]}"
        stdout, stderr = self.run_git_command(
            ["git", "clone", "-b", self.branch_name, repo_url_with_auth, self.repo_dir.name])
        if stderr:
            st.error(f"Error cloning repo: {stderr}")

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
        stdout, stderr = self.run_git_command(["git", "push", "origin", self.branch_name])
        if stderr:
            st.error(f"Error pushing changes: {stderr}")
        else:
            st.success("Changes pushed to the repository.")
            st.write(stdout)


# Function to handle errors in rmtree
def handle_remove_readonly(func, path, exc):
    exc_type, exc_value, exc_tb = exc
    if func in (os.rmdir, os.remove, os.unlink) and exc_type is PermissionError:
        os.chmod(path, 0o777)
        func(path)
    else:
        raise


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


# Streamlit app layout
st.title("CSV File Editor with GitLab Integration")

repo_url = st.text_input("Repository URL", "https://gitlab.com/namma-group1/File_Editor.git")
username = st.text_input("GitLab Username")
token = st.text_input("Personal Access Token", type="password")

if repo_url and token and username:
    branches = fetch_branches(repo_url, username, token)
    st.write(f"Fetched branches: {branches}")  # Debug output to verify branches
    if not branches:
        st.error("No branches found or failed to fetch branches.")
    selected_branch = st.selectbox("Select Branch", [""] + branches)

    if selected_branch:
        try:
            with tempfile.TemporaryDirectory() as temp_repo_dir:
                repo_url_with_auth = f"https://{username}:{token}@{repo_url.split('https://')[-1]}"
                st.write(f"Repo URL with auth: {repo_url_with_auth}")
                subprocess.run(["git", "clone", "-b", selected_branch, repo_url_with_auth, temp_repo_dir], check=True)
                csv_files = [f for f in os.listdir(temp_repo_dir) if f.endswith('.csv')]
                st.write(f"CSV files: {csv_files}")
                if not csv_files:
                    st.error("No CSV files found in the selected branch.")
                    st.stop()
        except subprocess.CalledProcessError as e:
            st.error(f"Failed to clone repository: {e.stderr}")
            st.stop()

        selected_file = st.selectbox("Select CSV File", csv_files)

        if selected_file:
            try:
                editor = GitCSVEditor(repo_url, selected_branch, selected_file, username, token)
                st.session_state.editor = editor
            except Exception as e:
                st.error(f"Failed to initialize editor: {e}")
                st.stop()

            if 'editor' in st.session_state:
                editor = st.session_state.editor
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


# Cleanup function (to be called manually after app shutdown)
def cleanup():
    if 'editor' in st.session_state:
        st.session_state.editor.repo_dir.cleanup()
        del st.session_state.editor


# Note: Cleanup needs to be called manually in your environment after app shutdown

# Example usage of cleanup function after app shutdown
cleanup()
