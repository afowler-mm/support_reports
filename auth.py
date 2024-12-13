from streamlit_cookies_controller import CookieController
import streamlit as st
from apis.google import setup_google_sheets, fetch_auth_data

SHEET_ID = "11RbGbkxKeIqrjweIClMh2a14hwt1-wWP0tKkAI7gvIQ"
SHEET_NAME = "Clients"

# Initialize cookie controller
cookies = CookieController()

def authenticate_user(username, password, auth_data):
    """Check if the username and password match."""
    for record in auth_data:
        if record['Username'] == username and record['Password'] == password:
            return record['Client code']
    return None

def login(secrets):
    """Handle user login."""
    st.header("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        client = setup_google_sheets(secrets)
        auth_data = fetch_auth_data(client, SHEET_ID, SHEET_NAME)

        client_code = authenticate_user(username, password, auth_data)
        if client_code:
            # Save login details in session state and cookies
            st.session_state.username = username
            st.session_state.client_code = client_code
            st.session_state.logged_in = True
            
            cookies.set('username', username)
            cookies.set('client_code', client_code)
            cookies.set('logged_in', True)
            
            st.rerun()
        else:
            st.error("Invalid username or password.")

def logout():
    """Handle user logout."""
    if st.button("Logout"):
        # Clear session state and remove cookies
        for key in ['username', 'client_code', 'logged_in']:
            if key in st.session_state:
                del st.session_state[key]
        
        cookies.remove('username')
        cookies.remove('client_code')
        cookies.remove('logged_in')
        
        st.rerun()

def get_current_user():
    """Retrieve the current user from session state or cookies."""
    # Check if user is already logged in
    if st.session_state.get("logged_in", False):
        return st.session_state.username, st.session_state.client_code

    # Check cookies for persistent login
    username = cookies.get('username')
    client_code = cookies.get('client_code')
    logged_in = cookies.get('logged_in')

    if logged_in and username and client_code:
        # Restore session state from cookies
        st.session_state.username = username
        st.session_state.client_code = client_code
        st.session_state.logged_in = True
        return username, client_code

    return None, None