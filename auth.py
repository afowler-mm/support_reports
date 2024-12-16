import streamlit as st
from apis.google import setup_google_sheets, fetch_auth_data
import hashlib

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

def hash_client_code(client_code, secret_key):
    """Hash the client code with a secret key."""
    return hashlib.sha256(f"{client_code}{secret_key}".encode()).hexdigest()

def validate_query_param_login(query_params, secret_key):
    """Validate the login based on the query parameter."""
    if "login_token" in query_params:
        login_token = query_params["login_token"]
        # Assume `client_code` is retrievable from the valid hash
        for client_code in fetch_all_client_codes():  # Replace with your method to fetch all valid client codes
            expected_hash = hash_client_code(client_code, secret_key)
            if login_token == expected_hash:
                return client_code
    return None

def fetch_all_client_codes():
    """Fetch all valid client codes from the Google Sheet."""
    client = setup_google_sheets(st.secrets["gcp_service_account"])
    auth_data = fetch_auth_data(client, SHEET_ID, SHEET_NAME)
    return [record["Client code"] for record in auth_data]