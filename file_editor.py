import streamlit as st
import pandas as pd
from git import Repo, GitCommandError
import tempfile
import os
import shutil

# Helper class to manage Git and CSV operations
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

# Function to fetch branches
def fetch_branches(repo_url):
    try:
        repo_dir = tempfile.mkdtemp()
        repo = Repo.clone_from(repo_url, repo_dir)
        branches = [branch.name for branch in repo.branches]
        shutil.rmtree(repo_dir)
        return branches
    except GitCommandError as e:
        st.error(f"Failed to fetch branches: {e}")
        return []

# Streamlit app layout
st.title("CSV File Editor with Git Integration")

repo_url = st.text_input("Repository URL", "https://github.com/kiran-kumar-hk/resourcesettings.git")

if repo_url:
    branches = fetch_branches(repo_url)
    selected_branch = st.selectbox("Select Branch", [""] + branches)

    if selected_branch:
        try:
            editor = GitCSVEditor(repo_url, selected_branch, "")
            st.session_state.editor = editor
        except GitCommandError as e:
            st.error(f"Failed to clone repository: {e}")
            st.stop()

        if 'editor' in st.session_state:
            editor = st.session_state.editor
            csv_files = [f for f in os.listdir(editor.repo_dir) if f.endswith('.csv')]
            selected_file = st.selectbox("Select CSV File", csv_files)

            if selected_file:
                editor.filename = selected_file
                editor.filepath = os.path.join(editor.repo_dir, editor.filename)
                editor.df = pd.read_csv(editor.filepath)
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
def cleanup():
    if 'editor' in st.session_state:
        shutil.rmtree(st.session_state.editor.repo_dir)
        del st.session_state.editor

# Note: Cleanup needs to be called manually in your environment after app shutdown
