import streamlit as st
from auth import login, logout, get_current_user
from views import monthly

# Streamlit app configuration
st.set_page_config(page_title="Support Reporter", page_icon="🧮", layout="wide")

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Check authentication
username, client_code = get_current_user()

if not st.session_state.logged_in:
    login(st.secrets["gcp_service_account"])
else:
    # User is logged in
    st.header(f"Welcome, {client_code}!")

    tab1, tab2 = st.tabs(["Monthly Report", "Ticket Finder"])
    with tab1:
        monthly.display_monthly_report(client_code)
    with tab2:
        st.write(f"Ticket finder for {client_code}")
        
    logout()