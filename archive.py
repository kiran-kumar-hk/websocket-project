import streamlit as st
import subprocess
import tempfile
import os

def asof(aa, bb, cc, path):
    cmd = ['python', 'run', 'archive_file.py', '--aa', aa, '--bb', bb, '--cc', cc, '--path', path]
    subprocess.run(cmd)

def eod(aa, path):
    cmd = ['python', 'run', 'archive_file.py', '--aa', aa, '--path', path]
    subprocess.run(cmd)

def sdd(dd, ee, path):
    cmd = ['python', 'run', 'archive_file.py', '--dd', dd, '--ee', ee, '--path', path]
    subprocess.run(cmd)

def jhd(ff, path):
    cmd = ['python', 'run', 'archive_file.py', '--ff', ff, '--path', path]
    subprocess.run(cmd)

def process_option(option, inputs, path):
    if option == 'asof':
        asof(inputs['aa'], inputs['bb'], inputs['cc'], path)
    elif option == 'eod':
        eod(inputs['aa'], path)
    elif option == 'sdd':
        sdd(inputs['dd'], inputs['ee'], path)
    elif option == 'jhd':
        jhd(inputs['ff'], path)

def main():
    st.title("File Download App")

    # Initialize temporary directory
    if 'temp_dir' not in st.session_state:
        st.session_state['temp_dir'] = tempfile.mkdtemp()
    path = st.session_state['temp_dir']

    # Dropdown menu for options
    option = st.selectbox('Select an option', ['asof', 'eod', 'sdd', 'jhd'])

    inputs = {}
    if option == 'asof':
        # Input fields for 'asof'
        inputs['aa'] = st.text_input('Enter aa')
        inputs['bb'] = st.text_input('Enter bb')
        inputs['cc'] = st.text_input('Enter cc')
    elif option == 'eod':
        # Input field for 'eod'
        inputs['aa'] = st.text_input('Enter aa')
    elif option == 'sdd':
        # Input fields for 'sdd'
        inputs['dd'] = st.text_input('Enter dd')
        inputs['ee'] = st.text_input('Enter ee')
    elif option == 'jhd':
        # Input field for 'jhd'
        inputs['ff'] = st.text_input('Enter ff')

    # Process button
    if st.button('Download'):
        # Check if all required inputs are provided
        if all(inputs.values()):
            with st.spinner('Processing...'):
                process_option(option, inputs, path)
            files = os.listdir(path)
            if files:
                file_path = os.path.join(path, files[0])  # Assuming only one file is generated
                with open(file_path, 'rb') as f:
                    st.download_button('Click here to download your file', f, file_name=files[0])
            else:
                st.error('No file was generated.')
        else:
            st.error('Please fill in all required fields.')

if __name__ == '__main__':
    main()
