import streamlit as st
from views.monthly import display_monthly_report
from views.xero import display_xero_exporter
from views.ticket_finder import display_ticket_finder
from auth import login, logout, get_current_user

# Configure Streamlit
st.set_page_config(page_title="Made Media Support Reporter", page_icon="🧮", layout="wide")

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Authentication
username, client_code = get_current_user()

if not st.session_state.logged_in:
    login(st.secrets["gcp_service_account"])
else:
    # Sidebar containers
    with st.sidebar:
        # Filters container is rendered first
        filters_container = st.container(key="filters_container")
        
        # Welcome and logout button container
        with st.container():
            st.header(f"Welcome, {client_code}!")
            st.button("Logout", on_click=logout)

    # Define the pages as functions
    def monthly_report():
        st.title("Monthly report")
        display_monthly_report(client_code)

    def ticket_finder():
        st.title("Ticket finder")
        display_ticket_finder(client_code, filters_container)

    def xero_export():
        st.title("Xero export")
        display_xero_exporter(client_code)

    # Page navigation configuration
    pages = [
        st.Page(monthly_report, title="Monthly hours", icon="🧮"),
        st.Page(ticket_finder, title="Ticket finder", icon="🔍"),
    ]

    if username == "made" and client_code == "admin":
        pages.append(st.Page(xero_export, title="Xero export", icon="💸"))

    # Navigation
    selected_page = st.navigation(pages)
    selected_page.run()