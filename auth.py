import streamlit as st
from apis.google import setup_google_sheets, fetch_auth_data

SHEET_ID = "11RbGbkxKeIqrjweIClMh2a14hwt1-wWP0tKkAI7gvIQ"
SHEET_NAME = "Clients"

def authenticate_user(username, password, auth_data):
    """Check if the username and password match."""
    for record in auth_data:
        if record['Username'] == username and record['Password'] == password:
            return record['Client code']
    return None

def login(secrets, cookies):
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

            try:
                cookies.set('username', username)
                cookies.set('client_code', client_code)
                cookies.set('logged_in', True)
            except Exception as e:
                st.warning("Unable to set cookies. Your session will not persist after closing the browser.")
                st.write(f"Error details: {e}")

            st.rerun()
        else:
            st.error("Invalid username or password.")

def logout(cookies):
    """Handle user logout."""
    # Clear session state keys
    st.session_state.pop('username', None)
    st.session_state.pop('client_code', None)
    st.session_state.pop('logged_in', None)

    # Remove cookies
    cookies.remove('username')
    cookies.remove('client_code')
    cookies.remove('logged_in')

    # Signal rerun
    st.session_state.trigger_rerun = True

def get_current_user(cookies):
    """Retrieve the current user from session state or cookies."""
    # Check if user is already logged in
    if st.session_state.get("logged_in", False):
        return st.session_state.username, st.session_state.client_code

    # Handle missing cookies gracefully
    try:
        # Check cookies for persistent login
        username = cookies.get('username') or None
        client_code = cookies.get('client_code') or None
        logged_in = cookies.get('logged_in') or False
    except TypeError:
        # If the cookies object is not properly initialized
        username = None
        client_code = None
        logged_in = False

    if logged_in and username and client_code:
        # Restore session state from cookies
        st.session_state.username = username
        st.session_state.client_code = client_code
        st.session_state.logged_in = True
        return username, client_code

    return None, None