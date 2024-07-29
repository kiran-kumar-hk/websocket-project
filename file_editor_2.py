import streamlit as st
import pandas as pd
from git import Repo, GitCommandError
import tempfile
import os
import shutil
import time


# Helper class to manage Git and CSV operations
class GitCSVEditor:
    def __init__(self, repo_url, branch_name, filename, token, username):
        self.repo_url = repo_url
        self.branch_name = branch_name
        self.filename = filename
        self.token = token
        self.username = username
        self.repo_dir = tempfile.mkdtemp()
        # Clone the repository using the token for authentication
        self.repo = Repo.clone_from(self.authenticated_url(self.repo_url, self.token, self.username), self.repo_dir)
        self.repo.git.checkout(self.branch_name)
        self.filepath = os.path.join(self.repo_dir, self.filename)
        self.df = pd.read_csv(self.filepath)

    def authenticated_url(self, url, token, username):
        # Modify the repository URL to include the username and token for authentication
        return url.replace("https://", f"https://{username}:{token}@")

    def get_dataframe(self):
        return self.df

    def save_changes(self, new_data):
        self.df = pd.DataFrame(new_data)
        self.df.to_csv(self.filepath, index=False)

    def push_changes(self):
        try:
            self.repo.index.add([self.filepath])
            self.repo.index.commit("Updated CSV file")
            origin = self.repo.remote(name='origin')
            # Use the authenticated URL for pushing changes
            push_info = origin.push(self.authenticated_url(self.repo_url, self.token, self.username))
            st.write(push_info)  # Display push information for debugging
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
def fetch_branches(repo_url, token, username):
    repo_dir = tempfile.mkdtemp()
    try:
        repo = Repo.clone_from(f"https://{username}:{token}@{repo_url.split('https://')[-1]}", repo_dir)
        branches = [branch.name for branch in repo.branches]
        shutil.rmtree(repo_dir, onerror=handle_remove_readonly)
        return branches
    except GitCommandError as e:
        st.error(f"Failed to fetch branches: {e}")
        shutil.rmtree(repo_dir, onerror=handle_remove_readonly)
        return []
    except PermissionError as e:
        st.error(f"Permission error: {e}")
        time.sleep(1)
        try:
            shutil.rmtree(repo_dir, onerror=handle_remove_readonly)
        except Exception as retry_e:
            st.error(f"Failed to clean up temporary directory: {retry_e}")
        return []
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        shutil.rmtree(repo_dir, onerror=handle_remove_readonly)
        return []


# Streamlit app layout
st.title("CSV File Editor with Git Integration")

repo_url = st.text_input("Repository URL", "https://github.com/kiran-kumar-hk/resourcesettings.git")
username = st.text_input("GitHub Username")
token = st.text_input("Personal Access Token", type="password")

if repo_url and token and username:
    branches = fetch_branches(repo_url, token, username)
    st.write(f"Fetched branches: {branches}")  # Debug output to verify branches
    if not branches:
        st.error("No branches found or failed to fetch branches.")
    selected_branch = st.selectbox("Select Branch", [""] + branches)

    if selected_branch:
        try:
            temp_repo_dir = tempfile.mkdtemp()
            repo = Repo.clone_from(f"https://{username}:{token}@{repo_url.split('https://')[-1]}", temp_repo_dir)
            repo.git.checkout(selected_branch)
            csv_files = [f for f in os.listdir(temp_repo_dir) if f.endswith('.csv')]
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
                editor = GitCSVEditor(repo_url, selected_branch, selected_file, token, username)
                st.session_state.editor = editor
                shutil.rmtree(temp_repo_dir, onerror=handle_remove_readonly)
            except GitCommandError as e:
                st.error(f"Failed to initialize editor: {e}")
                shutil.rmtree(temp_repo_dir, onerror=handle_remove_readonly)
                st.stop()

            if 'editor' in st.session_state:
                editor = st.session_state.editor
                df = editor.get_dataframe()
                st.write("Edit the CSV data below:")
                edited_df = st.experimental_data_editor(df)

                # Save button
                if st.button("Save"):
                    editor.save_changes(edited_df)
                    st.success("File saved successfully.")

                # Push button
                if st.button("Push"):
                    editor.push_changes()
                    st.success("Changes pushed to the repository.")

# Cleanup function (to be called manually after app shutdown)
# def cleanup():
#     if 'editor' in st.session_state:
#         shutil.rmtree(st.session_state.editor.repo_dir, onerror=handle_remove_readonly)
#         del st.session_state.editor

# Note: Cleanup needs to be called manually in your environment after app shutdown

# Example usage of cleanup function after app shutdown
# cleanup()
