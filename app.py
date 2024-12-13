import streamlit as st
from auth import login, logout, get_current_user
from views import monthly

st.set_page_config(page_title="Support Reporter", page_icon="🧮", layout="wide")

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

username, client_code = get_current_user()

if not st.session_state.logged_in:
    login(st.secrets["gcp_service_account"])
else:
    # User is logged in              
    st.header(f"Welcome, {client_code}!")

    monthly.display_monthly_report(client_code)

    st.divider()        
    logout()