import streamlit as st
from auth import login, logout, get_current_user
from views import monthly, xero, ticket_finder

st.set_page_config(page_title="Made Media support reporter", page_icon="🧮", layout="wide")

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Check the user's authentication
username, client_code = get_current_user()

if not st.session_state.logged_in:
    login(st.secrets["gcp_service_account"])
else:
    st.header(f"Welcome, {client_code}!")

    tabs_config = [
        {"label": "Monthly report", "view": monthly.display_monthly_report},
        {"label": "Ticket finder", "view": ticket_finder.display_ticket_finder}
    ]

    if username == "made" and client_code == "admin":
        tabs_config.append({"label": "Xero export", "view": xero.display_xero_exporter})

    tabs = st.tabs([tab["label"] for tab in tabs_config])

    for tab, config in zip(tabs, tabs_config):
        with tab:
            config["view"](client_code)
    
    st.divider()
    logout()