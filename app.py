import streamlit as st
import urllib.parse

from views.monthly import display_monthly_report
from views.xero import display_xero_exporter
from views.ticket_finder import display_ticket_finder
from views.supportbot import display_supportbot
from auth import login, hash_client_code, validate_query_param_login

# Configure Streamlit
st.set_page_config(page_title="Made Media Support Reporter", page_icon="🧮", layout="wide")

# Session state initialization
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Check for query parameter-based login
query_params = st.query_params
if not st.session_state.logged_in and "login_token" in query_params:
    client_code = validate_query_param_login(query_params, st.secrets["auth_secret"])
    if client_code:
        st.session_state.username = "query_param"
        st.session_state.client_code = client_code
        st.session_state.logged_in = True

# Authentication and session handling
if not st.session_state.logged_in:
    # Handle login
    username, client_code = login(st.secrets["gcp_service_account"])
    if username and client_code:
        st.session_state.username = username
        st.session_state.client_code = client_code
        st.session_state.logged_in = True
        st.query_params["login_token"] = hash_client_code(client_code, st.secrets["auth_secret"])
        st.rerun()

if st.session_state.logged_in:
    # Sidebar containers
    with st.sidebar:
        filters_container = st.container()
        with st.container():
            st.header(f"Welcome, {st.session_state.client_code}!")
            if st.button("Logout"):
                st.session_state.logged_in = False
                st.session_state.username = None
                st.session_state.client_code = None
                st.rerun()

    # Define the pages as functions
    def monthly_report():
        st.title("Monthly report")
        display_monthly_report(st.session_state.client_code)

    def ticket_finder():
        st.title("Ticket finder")
        display_ticket_finder(st.session_state.client_code, filters_container)

    def xero_export():
        st.title("Xero export")
        display_xero_exporter(st.session_state.client_code)

    def supportbot():
        st.title("Support bot")
        display_supportbot()

    # Page navigation configuration
    pages = [
        st.Page(monthly_report, title="Monthly hours", icon="🧮"),
        st.Page(ticket_finder, title="Ticket finder", icon="🔍"),
    ]

    if st.session_state.client_code == "admin":
        pages.append(st.Page(xero_export, title="Xero export", icon="💸"))
        pages.append(st.Page(supportbot, title="Support bot", icon="🤖"))

    # Navigation
    selected_page = st.navigation(pages)
    selected_page.run()