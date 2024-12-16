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

def login(secrets):
    """Display login form and return credentials if valid."""
    st.header("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        client = setup_google_sheets(secrets)
        auth_data = fetch_auth_data(client, SHEET_ID, SHEET_NAME)

        client_code = authenticate_user(username, password, auth_data)
        if client_code:
            return username, client_code
        else:
            st.error("Invalid username or password.")
    return None, None