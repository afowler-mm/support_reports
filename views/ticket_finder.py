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

    # Create an empty placeholder for ticket fetching status
    fetch_status = st.empty()
    
    # Track start time to identify cached vs fresh data
    import time
    start_time = time.time()
    
    with st.spinner(f"Fetching tickets updated since {start_date}..."):
        # Show a progress message
        fetch_status.info(f"Loading tickets from {start_date} to {end_date}...")
        # Get tickets with caching
        tickets = get_tickets_within_date_range(start_date, end_date)
        
        # Calculate how long it took - if it's quick, it was cached
        elapsed_time = time.time() - start_time
        using_cached_data = elapsed_time < 0.5  # Less than 500ms probably means cached data
        
        if not tickets:
            st.warning("No tickets found in the selected range")
            # Clean up the status message
            fetch_status.empty()
            return
            
        # Only show success toast if it took some time (fresh data)
        if not using_cached_data:
            st.toast(f"Found {len(tickets)} tickets in the selected date range", icon="✅")
        
        # Always clean up the status
        fetch_status.empty()

    # Store the initial ticket count before filtering
    initial_ticket_count = len(tickets)
    
    with st.spinner("Fetching additional details about tickets..."):
        # Create an empty placeholder for the progress bar
        progress_bar = st.empty()
        progress_bar.progress(0.0)
        
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
                
                # Track start time to identify cached vs fresh data
                company_start_time = time.time()
                
                # Create individual empty placeholders for company progress
                company_status = st.empty()
                company_status.info(f"Fetching data for {len(company_ids)} companies...")
                company_progress = st.empty()
                company_progress.progress(0.0)
                
                total_companies = len(company_ids)
                for i, company_id in enumerate(company_ids):
                    # Update progress every company
                    progress_percent = i / total_companies
                    company_progress.progress(progress_percent)
                    
                    # Update the main progress bar less frequently
                    if i % max(1, total_companies // 10) == 0:
                        main_progress = 0.1 + (i / total_companies) * 0.3
                        progress_bar.progress(main_progress)
                        # Update status message with percentage
                        company_status.empty()  # Clear previous message
                        company_status.info(f"Fetching company data... ({i}/{total_companies} - {int(progress_percent*100)}%)")
                    try:
                        company = freshdesk_api.get_company_by_id(company_id)
                        company_code = company.get("custom_fields", {}).get("company_code")
                        if company_code:
                            company_data[company_id] = company_code
                    except Exception as e:
                        st.error(f"Error fetching company data for ID {company_id}: {str(e)}")
                        # Continue with other companies
                
                # Update the company progress to completion
                company_progress.progress(1.0)
                
                # Calculate elapsed time
                company_elapsed_time = time.time() - company_start_time
                company_using_cached = company_elapsed_time < 0.5  # Less than 500ms means cached
                
                # Only show success toast for fresh data (not cached)
                if not company_using_cached:
                    st.toast(f"Completed fetching company data for {total_companies} companies", icon="✅")
                
                # Clean up the progress elements
                company_status.empty()
                company_progress.empty()
                
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
            
            # Convert any list values to tuples to make them hashable
            tickets_df["Category"] = tickets_df["Category"].apply(
                lambda x: tuple(x) if isinstance(x, list) else x
            )
            
            tickets_df["Ticket Type"] = tickets_df["custom_fields"].apply(
                lambda x: x.get("cf_type", "Unknown")
            )
            
            # Convert any list values to tuples to make them hashable
            tickets_df["Ticket Type"] = tickets_df["Ticket Type"].apply(
                lambda x: tuple(x) if isinstance(x, list) else x
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
            
            # Track start time for agent data fetching
            agent_start_time = time.time()
            
            # Create individual empty placeholders for agent progress
            agent_status = st.empty()
            agent_status.info(f"Fetching data for {len(agent_ids)} agents...")
            agent_progress = st.empty()
            agent_progress.progress(0.0)
            
            # Pre-fetch all agent data
            total_agents = len(agent_ids)
            for i, agent_id in enumerate(agent_ids):
                # Update agent progress for every agent
                progress_percent = i / total_agents
                agent_progress.progress(progress_percent)
                
                # Update main progress bar less frequently
                if i % max(1, total_agents // 10) == 0:
                    main_progress = 0.4 + (i / total_agents) * 0.2
                    progress_bar.progress(main_progress)
                    # Update status message
                    agent_status.empty()  # Clear previous message
                    agent_status.info(f"Fetching agent data... ({i}/{total_agents} - {int(progress_percent*100)}%)")
                
                if not agent_id:
                    continue
                try:
                    agent = freshdesk_api.get_agent(int(agent_id))
                    agent_names[agent_id] = agent.get("contact", {}).get("name", "Unknown")
                except Exception as e:
                    st.warning(f"Error fetching agent data for ID {agent_id}: {str(e)}")
                    agent_names[agent_id] = "Unknown"
            
            # Update agent progress to completion and clean up
            agent_progress.progress(1.0)
            
            # Calculate elapsed time
            agent_elapsed_time = time.time() - agent_start_time
            agent_using_cached = agent_elapsed_time < 0.5  # Less than 500ms means cached
            
            # Only show success toast for fresh data (not cached)
            if not agent_using_cached:
                st.toast(f"Completed fetching agent data for {total_agents} agents", icon="✅")
            
            # Clear the progress elements
            agent_status.empty()
            agent_progress.empty()
            
            # 2. Get unique group IDs
            group_ids = set(tickets_df["group_id"].dropna().unique())
            group_names = {}
            
            # Update progress
            progress_bar.progress(0.6)
            
            # Track start time for group data fetching
            group_start_time = time.time()
            
            # Create individual empty placeholders for group progress
            group_status = st.empty()
            group_status.info(f"Fetching data for {len(group_ids)} groups...")
            group_progress = st.empty()
            group_progress.progress(0.0)
            
            # Pre-fetch all group data
            total_groups = len(group_ids)
            for i, group_id in enumerate(group_ids):
                # Update group progress for every group
                progress_percent = i / total_groups
                group_progress.progress(progress_percent)
                
                # Update main progress bar less frequently
                if i % max(1, total_groups // 5) == 0:
                    main_progress = 0.6 + (i / total_groups) * 0.2
                    progress_bar.progress(main_progress)
                    # Update status message
                    group_status.empty()  # Clear previous message
                    group_status.info(f"Fetching group data... ({i}/{total_groups} - {int(progress_percent*100)}%)")
                
                if not group_id:
                    continue
                try:
                    group = freshdesk_api.get_group(int(group_id))
                    group_names[group_id] = group.get("name", "Unknown")
                except Exception as e:
                    st.warning(f"Error fetching group data for ID {group_id}: {str(e)}")
                    group_names[group_id] = "Unknown"
                    
            # Update group progress to completion and clean up
            group_progress.progress(1.0)
            
            # Calculate elapsed time
            group_elapsed_time = time.time() - group_start_time
            group_using_cached = group_elapsed_time < 0.5  # Less than 500ms means cached
            
            # Only show success toast for fresh data (not cached)
            if not group_using_cached:
                st.toast(f"Completed fetching group data for {total_groups} groups", icon="✅")
            
            # Clear the progress elements
            group_status.empty()
            group_progress.empty()
                    
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
                
                # Safely get category options, converting tuples back to strings if needed
                category_options = []
                for cat in tickets_df["Category"].unique():
                    if isinstance(cat, tuple):
                        # Join tuple elements with comma if it's a tuple
                        category_options.append(", ".join(str(x) for x in cat))
                    else:
                        category_options.append(cat)
                
                category_options = sorted(category_options)
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
                
                # Safely get ticket type options, converting tuples back to strings if needed
                ticket_type_options = []
                for tt in tickets_df["Ticket Type"].unique():
                    if isinstance(tt, tuple):
                        # Join tuple elements with comma if it's a tuple
                        ticket_type_options.append(", ".join(str(x) for x in tt))
                    else:
                        ticket_type_options.append(tt)
                        
                ticket_type_options = sorted(ticket_type_options)
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
            
            # Create a cacheable function for text search
            @st.cache_data(ttl=3600)
            def filter_by_text_and_categories(df, search, categories, cr_only):
                """Cache-friendly function for text search and category filtering"""
                filtered_df = df.copy()
                
                # Apply text filter
                if search:
                    filtered_df = filtered_df[
                        filtered_df["subject"].str.contains(search, case=False, na=False)
                        | filtered_df["description"].str.contains(
                            search, case=False, na=False
                        )
                    ]
                
                # Apply category filter
                if categories:
                    # Convert to tuple/list to ensure hashability
                    if not isinstance(categories, (list, tuple)):
                        cat_list = [categories]
                    else:
                        cat_list = list(categories)
                    
                    # Handle case when categories are tuples in DataFrame but strings in filter
                    matched_rows = filtered_df["Category"].apply(
                        lambda x: (isinstance(x, tuple) and ", ".join(str(i) for i in x) in cat_list) or
                               (not isinstance(x, tuple) and x in cat_list)
                    )
                    filtered_df = filtered_df[matched_rows]
                
                # Apply CR filter
                if cr_only:
                    filtered_df = filtered_df[filtered_df["CR?"]]
                    
                return filtered_df
                
            # Apply text and category filters
            if search_term or selected_categories or change_request_only:
                # Track search time
                search_start_time = time.time()
                
                # Create empty elements for text search progress
                text_status = st.empty()
                text_status.info("Searching ticket content...")
                
                # Store ticket count before search filtering
                pre_search_count = len(tickets_df)
                
                # Run the search
                tickets_df = filter_by_text_and_categories(
                    tickets_df, 
                    search_term, 
                    selected_categories, 
                    change_request_only
                )
                
                # Calculate elapsed time
                search_elapsed_time = time.time() - search_start_time
                search_using_cached = search_elapsed_time < 0.5  # Less than 500ms means cached
                
                # Only show success toast for non-cached operations
                if not search_using_cached:
                    # Show filtered vs total in the toast
                    search_result_count = len(tickets_df)
                    if search_result_count < pre_search_count:
                        st.toast(f"Search complete - found {search_result_count} of {pre_search_count} matches", icon="✅")
                    else:
                        st.toast(f"Search complete - found {search_result_count} matches", icon="✅")
                    
                # Always clean up immediately
                text_status.empty()

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
                
                # Track start time for company name fetching
                company_name_start_time = time.time()
                
                # Create individual empty placeholders for company name progress
                company_name_status = st.empty()
                company_name_status.info(f"Fetching names for {len(company_ids)} companies...")
                company_name_progress = st.empty()
                company_name_progress.progress(0.0)
                
                # Create a mapping of company_id to name
                company_names = {}
                progress_bar.progress(0.8)  # Update progress
                total_cids = len(company_ids)
                for i, cid in enumerate(company_ids):
                    # Update company name progress for every company
                    progress_percent = i / total_cids
                    company_name_progress.progress(progress_percent)
                    
                    # Update main progress periodically
                    if i % max(1, total_cids // 10) == 0:
                        main_progress = 0.8 + (i / total_cids) * 0.1
                        progress_bar.progress(main_progress)
                        # Update status message
                        company_name_status.empty()  # Clear previous message
                        company_name_status.info(f"Fetching company names... ({i}/{total_cids} - {int(progress_percent*100)}%)")
                    try:
                        company = freshdesk_api.get_company_by_id(cid)
                        company_names[cid] = company.get("name", "Unknown")
                    except Exception as e:
                        st.warning(f"Unable to fetch company name for ID: {cid}. Error: {e}")
                        company_names[cid] = "Unknown"
                
                # Update progress to completion and clean up
                company_name_progress.progress(1.0)
                
                # Calculate elapsed time
                company_name_elapsed_time = time.time() - company_name_start_time
                company_name_using_cached = company_name_elapsed_time < 0.5  # Less than 500ms means cached
                
                # Only show success toast for fresh data (not cached)
                if not company_name_using_cached:
                    st.toast(f"Completed fetching company names for {total_cids} companies", icon="✅")
                
                # Clear the progress elements
                company_name_status.empty()
                company_name_progress.empty()
                
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
            
            # Store the count of tickets before applying filters (but after company filtering)
            # This gives us a more accurate baseline for filter comparisons
            base_ticket_count = len(tickets_df)
            
            # Cache the complete dataframe before filtering
            # This improves performance when changing filters
            @st.cache_data(ttl=3600)
            def get_filtered_tickets(df, statuses, types, agents, groups, estimate_range=None, has_est=False):
                """Cache-friendly function to filter tickets based on criteria"""
                filtered_df = df.copy()
                
                # Apply filters - ensure all input lists are hashable (tuples)
                if statuses:
                    # Convert to list to ensure hashability
                    status_list = list(statuses) if isinstance(statuses, (list, tuple)) else [statuses]
                    filtered_df = filtered_df[filtered_df["status_readable"].isin(status_list)]
                    
                if types:
                    # Convert to list to ensure hashability
                    types_list = list(types) if isinstance(types, (list, tuple)) else [types]
                    
                    # Handle case when types are tuples in DataFrame but strings in filter
                    matched_rows = filtered_df["Ticket Type"].apply(
                        lambda x: any(
                            (isinstance(x, tuple) and ", ".join(str(i) for i in x) in types_list) or
                            (not isinstance(x, tuple) and x in types_list)
                        )
                    )
                    filtered_df = filtered_df[matched_rows]
                    
                if agents:
                    # Convert to list to ensure hashability
                    agents_list = list(agents) if isinstance(agents, (list, tuple)) else [agents]
                    filtered_df = filtered_df[filtered_df["Assigned To"].isin(agents_list)]
                    
                if groups:
                    # Convert to list to ensure hashability
                    groups_list = list(groups) if isinstance(groups, (list, tuple)) else [groups]
                    filtered_df = filtered_df[filtered_df["Group"].isin(groups_list)]
                    
                if has_est and estimate_range:
                    min_est, max_est = estimate_range
                    filtered_df = filtered_df[(filtered_df["Estimate"] >= min_est) & 
                                            (filtered_df["Estimate"] <= max_est) & 
                                            (filtered_df["Estimate"] > 0)]
                
                return filtered_df
            
            # Get estimate range for filter
            estimate_range = None
            if has_estimate:
                estimate_range = (min_estimate, max_estimate)
            
            # Apply filters with cached function to improve performance
            # Track filter time
            filter_start_time = time.time()
            
            filter_status = st.empty()
            filter_status.info("Applying filters...")
            
            # Store ticket count before filtering
            pre_filter_count = len(tickets_df)
            
            # Apply filters
            tickets_df = get_filtered_tickets(
                tickets_df, 
                selected_statuses, 
                selected_ticket_types, 
                selected_agents, 
                selected_groups,
                estimate_range,
                has_estimate
            )
            
            # Calculate elapsed time
            filter_elapsed_time = time.time() - filter_start_time
            filter_using_cached = filter_elapsed_time < 0.5  # Less than 500ms means cached
            
            # Only show success toast for non-cached operations
            if not filter_using_cached:
                # Show filtered vs total in the toast
                filter_result_count = len(tickets_df)
                if filter_result_count < pre_filter_count:
                    st.toast(f"Filters applied - displaying {filter_result_count} of {pre_filter_count} tickets", icon="✅")
                else:
                    st.toast(f"Filters applied - displaying {filter_result_count} tickets", icon="✅")
                
            # Always clean up immediately
            filter_status.empty()

            # Check if any filters are applied
            current_ticket_count = len(tickets_df)
            filters_applied = (
                search_term or 
                selected_categories or 
                change_request_only or
                selected_statuses or
                selected_ticket_types or
                selected_agents or
                selected_groups or
                has_estimate
            )
            
            # Display table with clickable links, showing filter information if relevant
            if filters_applied and current_ticket_count < base_ticket_count:
                # Show both filtered count and total count when filters reduce the number of tickets shown
                st.caption(
                    f"Displaying {current_ticket_count} of {base_ticket_count} tickets updated between {start_date} and {end_date} (filters applied)"
                )
            else:
                st.caption(
                    f"Displaying {current_ticket_count} tickets updated between {start_date} and {end_date}"
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
            
            # Check if any of our data operations were non-cached
            overall_using_cached = (
                using_cached_data and 
                (not selected_company_codes or company_using_cached) and
                (len(agent_ids) == 0 or agent_using_cached) and 
                (len(group_ids) == 0 or group_using_cached) and
                (client_code != "admin" or company_name_using_cached)
            )
            
            # Only show final success toast if we did actual work
            if not overall_using_cached:
                st.toast("✨ All data loaded successfully!", icon="🚀")
            
            # Remove the progress bar
            progress_bar.empty()
            
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
        # The API already filters by updated_since, so we only need to filter by end_date locally
        tickets = freshdesk_api.get_tickets(updated_since=start_date)
        
        # Make sure we're not storing any mutable objects like lists in fields that will be cached
        # Filter tickets without modifying the originals - creates immutable records
        filtered_tickets = []
        for ticket in tickets:
            if start_date <= ticket["updated_at"] <= end_date:
                # Deep copy the ticket to prevent shared references to mutable objects
                filtered_tickets.append(ticket.copy())
                
                # If the ticket has custom fields with lists, convert them to tuples
                for field in filtered_tickets[-1].get('custom_fields', {}).keys():
                    value = filtered_tickets[-1]['custom_fields'].get(field)
                    if isinstance(value, list):
                        filtered_tickets[-1]['custom_fields'][field] = tuple(value)
                
        return filtered_tickets
    except Exception as e:
        # Return empty list on error - we'll handle the error display outside the cached function
        return []
