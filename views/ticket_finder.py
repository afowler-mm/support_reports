import streamlit as st
import pandas as pd
import requests
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
        # Add a progress bar to show processing status
        progress_bar = st.progress(0.0)
        
        try:
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

            # Pre-fetch company data for efficiency and error handling
            company_data = {}
            if selected_company_codes:
                # Get unique company IDs from tickets
                company_ids = {ticket.get("company_id") for ticket in tickets if ticket.get("company_id")}
                
                # Pre-fetch company data for all companies
                progress_bar.progress(0.1)  # Update progress
                total_companies = len(company_ids)
                for i, company_id in enumerate(company_ids):
                    # Update progress every few companies
                    if i % max(1, total_companies // 10) == 0:
                        progress_bar.progress(0.1 + (i / total_companies) * 0.3)
                    try:
                        company = freshdesk_api.get_company_by_id(company_id)
                        company_code = company.get("custom_fields", {}).get("company_code")
                        if company_code:
                            company_data[company_id] = company_code
                    except Exception as e:
                        st.error(f"Error fetching company data for ID {company_id}: {str(e)}")
                        # Continue with other companies
                
                # Filter tickets with pre-fetched company data
                filtered_tickets = [
                    ticket
                    for ticket in tickets
                    if ticket.get("company_id") and
                    company_data.get(ticket.get("company_id")) in selected_company_codes
                ]
            else:
                filtered_tickets = tickets

            if not filtered_tickets:
                st.write("No tickets found for the selected clients.")
                return

            # Convert to DataFrame for display
            tickets_df = pd.DataFrame(filtered_tickets)
            # Handle potential None values before converting dates
            tickets_df["created_at"] = tickets_df["created_at"].fillna(pd.Timestamp.now())
            tickets_df["updated_at"] = tickets_df["updated_at"].fillna(pd.Timestamp.now())
            
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
            
            # Pre-fetch agent and group information for efficiency
            # 1. Get unique agent IDs
            agent_ids = set(tickets_df["responder_id"].dropna().unique())
            agent_names = {}
            
            # Update progress
            progress_bar.progress(0.4)
            
            # Pre-fetch all agent data
            total_agents = len(agent_ids)
            for i, agent_id in enumerate(agent_ids):
                # Update progress periodically
                if i % max(1, total_agents // 10) == 0:
                    progress_bar.progress(0.4 + (i / total_agents) * 0.2)
                
                if not agent_id:
                    continue
                try:
                    agent = freshdesk_api.get_agent(int(agent_id))
                    agent_names[agent_id] = agent.get("contact", {}).get("name", "Unknown")
                except Exception as e:
                    st.warning(f"Error fetching agent data for ID {agent_id}: {str(e)}")
                    agent_names[agent_id] = "Unknown"
            
            # 2. Get unique group IDs
            group_ids = set(tickets_df["group_id"].dropna().unique())
            group_names = {}
            
            # Update progress
            progress_bar.progress(0.6)
            
            # Pre-fetch all group data
            total_groups = len(group_ids)
            for i, group_id in enumerate(group_ids):
                # Update progress periodically
                if i % max(1, total_groups // 5) == 0:
                    progress_bar.progress(0.6 + (i / total_groups) * 0.2)
                
                if not group_id:
                    continue
                try:
                    group = freshdesk_api.get_group(int(group_id))
                    group_names[group_id] = group.get("name", "Unknown")
                except Exception as e:
                    st.warning(f"Error fetching group data for ID {group_id}: {str(e)}")
                    group_names[group_id] = "Unknown"
                    
            # Update progress
            progress_bar.progress(0.8)
            
            # Use the pre-fetched data for assignments
            def get_agent_name(agent_id):
                if not agent_id or pd.isna(agent_id):
                    return "Unassigned"
                return agent_names.get(agent_id, "Unknown")
            
            def get_group_name(group_id):
                if not group_id or pd.isna(group_id):
                    return "None"
                return group_names.get(group_id, "Unknown")
            
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
                # Extract categories and handle None values
                tickets_df["Category"] = tickets_df["Category"].fillna("Unknown")
                category_options = sorted(tickets_df["Category"].unique().tolist())
                selected_categories = st.multiselect("Filter by category", category_options)

                # Add status filter
                tickets_df["status"] = tickets_df["status"].fillna(0)  # Use 0 for numeric status fields that are None
                status_options = tickets_df["status"].unique().tolist()
                status_options_readable = [
                    status_mapping.get(status, str(status)) for status in status_options
                ]
                selected_statuses = st.pills(
                    "Filter by status", status_options_readable, selection_mode="multi"
                )
                
                # Add ticket type filter
                # Fill None values with "Unknown" to avoid sorting errors
                tickets_df["Ticket Type"] = tickets_df["Ticket Type"].fillna("Unknown")
                ticket_type_options = sorted(tickets_df["Ticket Type"].unique().tolist())
                selected_ticket_types = st.multiselect("Filter by ticket type", ticket_type_options)
                
                # Add agent filter
                tickets_df["Assigned To"] = tickets_df["Assigned To"].fillna("Unassigned")
                agent_options = sorted(tickets_df["Assigned To"].unique().tolist())
                selected_agents = st.multiselect("Filter by assigned agent", agent_options)
                
                # Add group filter
                tickets_df["Group"] = tickets_df["Group"].fillna("None") 
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

            # Make sure subject and description fields have no None values for text search
            tickets_df["subject"] = tickets_df["subject"].fillna("")
            tickets_df["description"] = tickets_df["description"].fillna("")
            
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
                # Pre-fetch all company names at once
                company_ids = set()
                for cid in tickets_df["company_id"].dropna().unique():
                    try:
                        company_ids.add(int(cid))
                    except (ValueError, TypeError):
                        # Skip invalid IDs
                        pass
                
                # Create a mapping of company_id to name
                company_names = {}
                progress_bar.progress(0.8)  # Update progress
                total_cids = len(company_ids)
                for i, cid in enumerate(company_ids):
                    # Update progress periodically
                    if i % max(1, total_cids // 10) == 0:
                        progress_bar.progress(0.8 + (i / total_cids) * 0.1)
                    try:
                        company = freshdesk_api.get_company_by_id(cid)
                        company_names[cid] = company.get("name", "Unknown")
                    except Exception as e:
                        st.warning(f"Unable to fetch company name for ID: {cid}. Error: {e}")
                        company_names[cid] = "Unknown"
                
                # Final progress update
                progress_bar.progress(0.9)

                # Apply the mapping to add the client name column
                def get_client_name(cid):
                    if not cid or pd.isna(cid):  # Handle None or NaN cases
                        return "Unknown"
                    try:
                        return company_names.get(int(cid), "Unknown")
                    except (ValueError, TypeError):
                        return "Unknown"
                        
                tickets_df["Client name"] = tickets_df["company_id"].apply(get_client_name)

            # Sort by creation date
            tickets_df = tickets_df.sort_values("created_at", ascending=False)

            # Add a column for clickable ticket links
            tickets_df["ticket_url"] = tickets_df["id"].apply(
                lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
            )

            # Add human-readable status column
            # First make sure status column has no None values
            tickets_df["status"] = tickets_df["status"].fillna(0)
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

            # Update progress to 100% when done
            progress_bar.progress(1.0)
            
            # Display the dataframe
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
        except Exception as e:
            st.error(f"Error processing ticket data: {str(e)}")
            # Show stack trace in expanded section for admin users
            if client_code == "admin":
                with st.expander("Error details"):
                    st.exception(e)


@st.cache_data(ttl=3600)
def get_tickets_within_date_range(start_date: str, end_date: str):
    try:
        # Fetch tickets updated within the date range
        tickets = freshdesk_api.get_tickets(updated_since=start_date)
        return [
            ticket for ticket in tickets if start_date <= ticket["updated_at"] <= end_date
        ]
    except Exception as e:
        st.error(f"Error fetching tickets: {str(e)}")
        return []
