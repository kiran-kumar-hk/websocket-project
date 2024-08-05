import streamlit as st
import pandas as pd
from git import Repo, GitCommandError
import gitlab
import tempfile
import os
import shutil

# Helper class to manage Git and CSV operations
class GitCSVEditor:
    def __init__(self, repo_url, branch_name, filename, username, token):
        self.repo_url = repo_url
        self.branch_name = branch_name
        self.filename = filename
        self.username = username
        self.token = token
        self.repo_dir = tempfile.mkdtemp()
        self.clone_repo()
        self.filepath = os.path.join(self.repo_dir, self.filename)
        self.df = pd.read_csv(self.filepath)

    def clone_repo(self):
        # Clone the repository using git command
        repo_url_with_auth = f"https://{self.username}:{self.token}@{self.repo_url.split('https://')[-1]}"
        self.repo = Repo.clone_from(repo_url_with_auth, self.repo_dir)
        self.repo.git.checkout(self.branch_name)

    def get_dataframe(self):
        return self.df

    def save_changes(self, new_data):
        self.df = pd.DataFrame(new_data)
        self.df.to_csv(self.filepath, index=False)

    def push_changes(self):
        try:
            self.repo.git.add(self.filepath)
            self.repo.index.commit("Updated CSV file")
            origin = self.repo.remote(name='origin')
            push_info = origin.push()
            st.write(push_info)  # Display push information for debugging
            st.success("Changes pushed to the repository.")
        except GitCommandError as e:
            st.error(f"Failed to push changes: {e}")
        except Exception as e:
            st.error(f"An unexpected error occurred during push: {e}")

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
        st.write(f"Project: {project}")
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

repo_url = st.text_input("Repository URL", "https://gitlab.com/username/repository.git")
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
            temp_repo_dir = tempfile.mkdtemp()
            repo_url_with_auth = f"https://{username}:{token}@{repo_url.split('https://')[-1]}"
            st.write(f"Repo URL with auth: {repo_url_with_auth}")
            repo = Repo.clone_from(repo_url_with_auth, temp_repo_dir)
            st.write(f"Cloned repo: {repo}")
            repo.git.checkout(selected_branch)
            csv_files = [f for f in os.listdir(temp_repo_dir) if f.endswith('.csv')]
            st.write(f"CSV files: {csv_files}")
            if not csv_files:
                st.error("No CSV files found in the selected branch.")
                shutil.rmtree(temp_repo_dir, onerror=handle_remove_readonly)
                st.stop()
        except GitCommandError as e:
            st.error(f"Failed to clone repository: {e}")
            shutil.rmtree(temp_repo_dir, onerror=handle_remove_readonly)
            st.stop()

        selected_file = st.selectbox("Select CSV File", csv_files)

        if selected_file:
            try:
                editor = GitCSVEditor(repo_url, selected_branch, selected_file, username, token)
                st.session_state.editor = editor
                shutil.rmtree(temp_repo_dir, onerror=handle_remove_readonly)
            except Exception as e:
                st.error(f"Failed to initialize editor: {e}")
                shutil.rmtree(temp_repo_dir, onerror=handle_remove_readonly)
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

                # Push button
                if st.button("Push"):
                    editor.push_changes()

# Cleanup function (to be called manually after app shutdown)
# def cleanup():
#     if 'editor' in st.session_state:
#         shutil.rmtree(st.session_state.editor.repo_dir, onerror=handle_remove_readonly)
#         del st.session_state.editor
# 
# # Note: Cleanup needs to be called manually in your environment after app shutdown
# 
# # Example usage of cleanup function after app shutdown
# cleanup()
