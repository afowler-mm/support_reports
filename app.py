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
        tabs = st.tabs(["Monthly Report", "Xero Export"])

        # Monthly Report Tab
        with tabs[0]:
            st.subheader("Monthly Report")
            monthly.display_monthly_report(client_code)

        # Xero Export Tab
        with tabs[1]:
            st.subheader("Xero Export")
            xero.display_xero_exporter()

    else:
        # Non-admin users only get the monthly report
        monthly.display_monthly_report(client_code)
    
    st.divider()
    logout()