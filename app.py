import streamlit as st
from auth import login, logout, get_current_user
from views import monthly, xero

st.set_page_config(page_title="Support Reporter", page_icon="🧮", layout="wide")

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Check the user's authentication
username, client_code = get_current_user()

if not st.session_state.logged_in:
    login(st.secrets["gcp_service_account"])
else:
    # User is logged in
    st.header(f"Welcome, {client_code}!")
    
    if username == "made" and client_code == "admin":
        # Define the tabs for admin users
        tabs = st.tabs(["Monthly report", "Xero export"])

        # Monthly Report Tab
        with tabs[0]:
            st.subheader("Monthly report")
            st.info("Want to give access to this report to a client? Add credentials for them [here](https://docs.google.com/spreadsheets/d/11RbGbkxKeIqrjweIClMh2a14hwt1-wWP0tKkAI7gvIQ/edit?gid=0#gid=0).")
            monthly.display_monthly_report(client_code)

        # Xero Export Tab
        with tabs[1]:
            st.subheader("Xero export")
            xero.display_xero_exporter()

    else:
        # Non-admin users only get the monthly report
        monthly.display_monthly_report(client_code)
    
    st.divider()
    logout()