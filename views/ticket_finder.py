import streamlit as st
import pandas as pd
from apis.freshdesk import freshdesk_api
from utils import date_range_selector
from logic import status_mapping

def display_ticket_finder(client_code: str, filters_container):
    # Date range selection
    date_range = date_range_selector()
    start_date, end_date = date_range["start_date"], date_range["end_date"]
    
    # Fetch and cache tickets
    with st.spinner("Loading tickets..."):
        tickets = get_tickets_within_date_range(start_date, end_date)

    if not tickets:
        st.warning("No tickets found in the selected range.")
        return
    
    with filters_container:
        st.subheader("Filters")
        if client_code == "admin":
            companies = freshdesk_api.get_companies()
            company_options = {c['name']: c['custom_fields'].get('company_code') for c in companies}
            selected_companies = st.multiselect("Select clients", list(company_options.keys()))
            selected_company_codes = [company_options[comp] for comp in selected_companies]
            
            # Show all tickets if no specific clients are selected
            if not selected_company_codes:
                st.info("No clients selected, showing tickets for all clients.")
                selected_company_codes = None
        else:
            # Non-admin users can only see their company's tickets
            selected_company_codes = [client_code]

    # Filter tickets by selected companies
    if selected_company_codes:
        filtered_tickets = [
            ticket for ticket in tickets
            if ticket.get("company_id") and any(
                freshdesk_api.get_company_by_id(ticket["company_id"])["custom_fields"].get("company_code") == code
                for code in selected_company_codes
            )
        ]
    else:
        filtered_tickets = tickets

    if not filtered_tickets:
        st.write("No tickets found for the selected clients.")
        return
    
    # Convert to DataFrame for display
    tickets_df = pd.DataFrame(filtered_tickets)
    tickets_df["created_at"] = pd.to_datetime(tickets_df["created_at"]).dt.strftime('%Y-%m-%d %H:%M:%S')
    tickets_df["updated_at"] = pd.to_datetime(tickets_df["updated_at"]).dt.strftime('%Y-%m-%d %H:%M:%S')

    # Add "CR?" column for change requests
    tickets_df["CR?"] = tickets_df["custom_fields"].apply(lambda x: x.get("change_request", False))

    # Add category column (custom field)
    tickets_df["Category"] = tickets_df["custom_fields"].apply(lambda x: x.get("category", "Unknown"))
    
    with filters_container:
        
        # Add "Change Requests Only" filter
        change_request_only = st.checkbox("Show change requests only", value=False)
        
        # Add text input filter
        search_term = st.text_input("Search tickets (titles and descriptions)", "").strip().lower()
        
        # Add "Category" filter
        category_options = tickets_df["custom_fields"].apply(lambda x: x.get("category", None)).dropna().unique().tolist()
        selected_categories = st.multiselect("Filter by category", category_options)
        
        # Add status filter
        status_options = tickets_df["status"].unique().tolist()
        status_options_readable = [status_mapping.get(status, status) for status in status_options]
        selected_statuses = st.pills("Filter by status", status_options_readable, selection_mode="multi")

        st.divider()

    # Apply text filter to titles and descriptions
    if search_term:
        tickets_df = tickets_df[
            tickets_df["subject"].str.contains(search_term, case=False, na=False) |
            tickets_df["description"].str.contains(search_term, case=False, na=False)
        ]

    # Filter by selected categories
    if selected_categories:
        tickets_df = tickets_df[tickets_df["Category"].isin(selected_categories)]

    # Filter by change requests if the checkbox is checked
    if change_request_only:
        tickets_df = tickets_df[tickets_df["CR?"]]

    # Add client name column for admins
    if client_code == "admin":
        def get_client_name(cid):
            if not cid or pd.isna(cid):  # Handle None or NaN cases
                return "Unknown"
            try:
                company = freshdesk_api.get_company_by_id(int(cid))
                return company.get("name", "Unknown")
            except (requests.exceptions.HTTPError, ValueError) as e:
                # Handle invalid or non-existent company_id
                st.warning(f"Unable to fetch company name for ID: {cid}. Error: {e}")
                return "Unknown"

        tickets_df["Client name"] = tickets_df["company_id"].apply(get_client_name)

    # Sort by creation date
    tickets_df = tickets_df.sort_values("created_at", ascending=False)

    # Add a column for clickable ticket links
    tickets_df["ticket_url"] = tickets_df["id"].apply(
        lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
    )
    
    # Add human-readable status column
    tickets_df["status_readable"] = tickets_df["status"].map(status_mapping).fillna("Unknown")

    # Filter by selected statuses
    if selected_statuses:
        tickets_df = tickets_df[tickets_df["status_readable"].isin(selected_statuses)]

    # Display table with clickable links
    st.caption(f"Displaying {len(tickets_df)} tickets updated between {start_date} and {end_date}")
    display_columns = ["ticket_url", "subject", "Category", "status_readable", "CR?", "created_at", "updated_at"]
    if client_code == "admin":
        display_columns.insert(2, "Client name")
        
    st.dataframe(
        tickets_df[display_columns],
        column_config={
            "ticket_url": st.column_config.LinkColumn("ID", display_text="tickets/(\\d+)"),
            "subject": st.column_config.TextColumn("Subject"),
            "Category": st.column_config.TextColumn("Category"),
            "status_readable": st.column_config.TextColumn("Status"),
            "CR?": st.column_config.CheckboxColumn("CR?"),
            "created_at": st.column_config.DatetimeColumn("Created", format="ddd DD MMM YYYY, HH:mm z"),
            "updated_at": st.column_config.DatetimeColumn("Updated", format="ddd DD MMM YYYY, HH:mm z"),
        },
        hide_index=True,
        height=1000
    )


@st.cache_data(ttl=3600, show_spinner=False)
def get_tickets_within_date_range(start_date: str, end_date: str):
    # Fetch tickets updated within the date range
    tickets = freshdesk_api.get_tickets(updated_since=start_date)
    return [
        ticket for ticket in tickets
        if start_date <= ticket["updated_at"] <= end_date
    ]