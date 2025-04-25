import streamlit as st
import pandas as pd
from apis.freshdesk import freshdesk_api
from utils import date_range_selector
from logic import status_mapping


def display_ticket_finder(client_code: str, filters_container):
    # Date range selection
    date_range = date_range_selector()
    start_date, end_date = date_range["start_date"], date_range["end_date"]

    with st.spinner("Fetching tickets..."):
        tickets = get_tickets_within_date_range(start_date, end_date)

    if not tickets:
        st.warning("No tickets found in the selected range")
        return

    with st.spinner("Fetching additional details about tickets..."):
        with filters_container:
            st.subheader("Filters")
            if client_code == "admin":
                companies = freshdesk_api.get_companies()
                company_options = {
                    c["name"]: c["custom_fields"].get("company_code") for c in companies
                }
                selected_companies = st.multiselect(
                    "Select clients", list(company_options.keys())
                )
                selected_company_codes = [
                    company_options[comp] for comp in selected_companies
                ]

                # Show all tickets if no specific clients are selected
                if not selected_company_codes:
                    st.caption("No clients selected; showing tickets for all clients")
                    selected_company_codes = None
            else:
                # Non-admin users can only see their company's tickets
                selected_company_codes = [client_code]

            # Filter tickets by selected companies
            if selected_company_codes:
                filtered_tickets = [
                    ticket
                    for ticket in tickets
                    if ticket.get("company_id")
                    and any(
                        freshdesk_api.get_company_by_id(ticket["company_id"])[
                            "custom_fields"
                        ].get("company_code")
                        == code
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
            tickets_df["created_at"] = pd.to_datetime(tickets_df["created_at"]).dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            tickets_df["updated_at"] = pd.to_datetime(tickets_df["updated_at"]).dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            # Add "CR?" column for change requests
            tickets_df["CR?"] = tickets_df["custom_fields"].apply(
                lambda x: x.get("change_request", False)
            )

            # Add custom fields as columns
            tickets_df["Category"] = tickets_df["custom_fields"].apply(
                lambda x: x.get("category", "Unknown")
            )
            
            tickets_df["Ticket Type"] = tickets_df["custom_fields"].apply(
                lambda x: x.get("cf_type", "Unknown")
            )
            
            # Extract estimate from custom fields
            def extract_estimate(custom_fields):
                estimate_value = custom_fields.get("estimate_hrs")
                if estimate_value and isinstance(estimate_value, str) and estimate_value.replace('.', '', 1).isdigit():
                    return float(estimate_value)
                return 0.0
                
            tickets_df["Estimate"] = tickets_df["custom_fields"].apply(extract_estimate)
            
            # Add agent and group information
            def get_agent_name(agent_id):
                if not agent_id:
                    return "Unassigned"
                try:
                    agent = freshdesk_api.get_agent(agent_id)
                    return agent.get("contact", {}).get("name", "Unknown")
                except:
                    return "Unknown"
            
            def get_group_name(group_id):
                if not group_id:
                    return "None"
                try:
                    group = freshdesk_api.get_group(group_id)
                    return group.get("name", "Unknown")
                except:
                    return "Unknown"
            
            tickets_df["Assigned To"] = tickets_df["responder_id"].apply(get_agent_name)
            tickets_df["Group"] = tickets_df["group_id"].apply(get_group_name)

            with filters_container:

                # Add text input filter
                search_term = (
                    st.text_input("Search tickets", "")
                    .strip()
                    .lower()
                )

                # Add "Category" filter
                category_options = (
                    tickets_df["custom_fields"]
                    .apply(lambda x: x.get("category", None))
                    .dropna()
                    .unique()
                    .tolist()
                )
                selected_categories = st.multiselect("Filter by category", category_options)

                # Add status filter
                status_options = tickets_df["status"].unique().tolist()
                status_options_readable = [
                    status_mapping.get(status, status) for status in status_options
                ]
                selected_statuses = st.pills(
                    "Filter by status", status_options_readable, selection_mode="multi"
                )
                
                # Add ticket type filter
                ticket_type_options = sorted(tickets_df["Ticket Type"].unique().tolist())
                selected_ticket_types = st.multiselect("Filter by ticket type", ticket_type_options)
                
                # Add agent filter
                agent_options = sorted(tickets_df["Assigned To"].unique().tolist())
                selected_agents = st.multiselect("Filter by assigned agent", agent_options)
                
                # Add group filter 
                group_options = sorted(tickets_df["Group"].unique().tolist())
                selected_groups = st.multiselect("Filter by group", group_options)
                
                # Add estimate filter
                has_estimate = st.checkbox("Has estimate", value=False)
                
                if has_estimate:
                    min_estimate, max_estimate = st.slider(
                        "Estimate range (hours)",
                        min_value=0.0,
                        max_value=float(tickets_df["Estimate"].max()) if len(tickets_df) > 0 else 40.0,
                        value=(0.1, float(tickets_df["Estimate"].max()) if len(tickets_df) > 0 else 40.0),
                        step=0.5
                    )
                
                change_request_only = st.checkbox("Show change requests only", value=False)

                st.divider()

            # Apply text filter to titles and descriptions
            if search_term:
                tickets_df = tickets_df[
                    tickets_df["subject"].str.contains(search_term, case=False, na=False)
                    | tickets_df["description"].str.contains(
                        search_term, case=False, na=False
                    )
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
                        st.warning(
                            f"Unable to fetch company name for ID: {cid}. Error: {e}"
                        )
                        return "Unknown"

                tickets_df["Client name"] = tickets_df["company_id"].apply(get_client_name)

            # Sort by creation date
            tickets_df = tickets_df.sort_values("created_at", ascending=False)

            # Add a column for clickable ticket links
            tickets_df["ticket_url"] = tickets_df["id"].apply(
                lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
            )

            # Add human-readable status column
            tickets_df["status_readable"] = (
                tickets_df["status"].map(status_mapping).fillna("Unknown")
            )

            # Filter by selected statuses
            if selected_statuses:
                tickets_df = tickets_df[
                    tickets_df["status_readable"].isin(selected_statuses)
                ]
                
            # Filter by selected ticket types
            if selected_ticket_types:
                tickets_df = tickets_df[tickets_df["Ticket Type"].isin(selected_ticket_types)]
                
            # Filter by selected agents
            if selected_agents:
                tickets_df = tickets_df[tickets_df["Assigned To"].isin(selected_agents)]
                
            # Filter by selected groups
            if selected_groups:
                tickets_df = tickets_df[tickets_df["Group"].isin(selected_groups)]
                
            # Filter by estimate
            if has_estimate:
                tickets_df = tickets_df[(tickets_df["Estimate"] >= min_estimate) & 
                                        (tickets_df["Estimate"] <= max_estimate) & 
                                        (tickets_df["Estimate"] > 0)]

        # Display table with clickable links
        st.caption(
            f"Displaying {len(tickets_df)} tickets updated between {start_date} and {end_date}"
        )
        display_columns = [
            "ticket_url",
            "subject",
            "Category",
            "Ticket Type",
            "status_readable",
            "CR?",
            "Estimate",
            "Assigned To",
            "Group",
            "created_at",
            "updated_at",
        ]
        if client_code == "admin":
            display_columns.insert(2, "Client name")

    st.dataframe(
        tickets_df[display_columns],
        column_config={
            "ticket_url": st.column_config.LinkColumn(
                "ID", display_text="tickets/(\\d+)"
            ),
            "subject": st.column_config.TextColumn("Subject"),
            "Category": st.column_config.TextColumn("Category"),
            "Ticket Type": st.column_config.TextColumn("Type"),
            "status_readable": st.column_config.TextColumn("Status"),
            "CR?": st.column_config.CheckboxColumn("CR?"),
            "Estimate": st.column_config.NumberColumn("Estimate (h)", format="%.1f"),
            "Assigned To": st.column_config.TextColumn("Assigned To"),
            "Group": st.column_config.TextColumn("Group"),
            "created_at": st.column_config.DatetimeColumn(
                "Created", format="ddd DD MMM YYYY, HH:mm z"
            ),
            "updated_at": st.column_config.DatetimeColumn(
                "Updated", format="ddd DD MMM YYYY, HH:mm z"
            ),
        },
        hide_index=True,
        height=1000,
    )


@st.cache_data(ttl=3600)
def get_tickets_within_date_range(start_date: str, end_date: str):
    # Fetch tickets updated within the date range
    tickets = freshdesk_api.get_tickets(updated_since=start_date)
    return [
        ticket for ticket in tickets if start_date <= ticket["updated_at"] <= end_date
    ]
