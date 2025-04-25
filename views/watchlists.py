import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from apis.freshdesk import freshdesk_api
from logic import status_mapping

def display_watchlists(client_code: str, filters_container=None):
    """Display watchlists for admin users."""
    # Verify user is admin
    if client_code != "admin":
        st.warning("You must be an admin to view watchlists.")
        return
        
    # Initialize common filters
    # Use the provided filters_container if available, else create a new one in main content
    filter_container = filters_container if filters_container else st.container()
    
    with filter_container:
        st.header("Filters")
        st.caption("Apply these filters to both watchlists")
        
        # Fetch groups using a safer approach
        groups = []
        try:
            # Get groups from the tickets instead of assuming IDs
            # This ensures we only show groups that actually have tickets
            companies = freshdesk_api.get_companies()
            sample_tickets = freshdesk_api.get_tickets()[:100]  # Limit to 100 recent tickets
            
            group_ids = set()
            for ticket in sample_tickets:
                if ticket.get('group_id'):
                    group_ids.add(ticket.get('group_id'))
            
            for group_id in group_ids:
                try:
                    group = freshdesk_api.get_group(group_id)
                    if group and 'name' in group:
                        groups.append(group['name'])
                except:
                    # Skip if this group can't be fetched
                    pass
        except Exception as e:
            st.warning(f"Could not fetch groups: {str(e)}")
            
        # Fetch all products for filtering
        products = []
        try:
            product_options = freshdesk_api.get_product_options()
            products = list(product_options.values())
        except Exception as e:
            st.warning(f"Could not fetch products: {str(e)}")
            
        # Fetch categories for filtering (from custom_fields)
        categories = []
        try:
            # Get categories from sample tickets' custom fields
            sample_tickets = freshdesk_api.get_tickets()[:100]  # Limit to 100 recent tickets
            for ticket in sample_tickets:
                if ticket.get('custom_fields') and ticket['custom_fields'].get('category'):
                    category = ticket['custom_fields'].get('category')
                    if category and category not in categories:
                        categories.append(category)
        except Exception as e:
            st.warning(f"Could not fetch categories: {str(e)}")
            
        # Create multiselect filters
        selected_groups = st.multiselect("Filter by group", ["All Groups"] + sorted(groups))
        selected_products = st.multiselect("Filter by product", ["All Products"] + sorted(products))
        selected_categories = st.multiselect("Filter by category", ["All Categories"] + sorted(categories))
        
        # Convert "All X" selection to None for easier filtering
        # Convert lists to tuples to make them hashable for caching
        filter_groups = None if "All Groups" in selected_groups else tuple(selected_groups)
        filter_products = None if "All Products" in selected_products else tuple(selected_products)
        filter_categories = None if "All Categories" in selected_categories else tuple(selected_categories)

    # Create tabs for different watchlists
    tabs = st.tabs(["Tickets over estimate", "Aging unresolved tickets"])

    # Tab 1: Tickets Over Estimate
    with tabs[0]:
        display_tickets_over_estimate(client_code, filter_groups, filter_products, filter_categories)

    # Tab 2: Aging Unresolved Tickets
    with tabs[1]:
        display_aging_unresolved_tickets(client_code, filter_groups, filter_products, filter_categories)

def display_tickets_over_estimate(client_code: str, filter_groups=None, filter_products=None, filter_categories=None):
    """Display tickets where time spent exceeds estimate."""
    st.subheader("Tickets over estimate")
    
    # Show active filters if any
    if filter_groups or filter_products or filter_categories:
        filters_text = []
        if filter_groups:
            filters_text.append(f"Groups: {', '.join(filter_groups)}")
        if filter_products:
            filters_text.append(f"Products: {', '.join(filter_products)}")
        if filter_categories:
            filters_text.append(f"Categories: {', '.join(filter_categories)}")
        st.caption(f"Active filters: {' | '.join(filters_text)}")

    # Date selector for filtering
    col1, col2 = st.columns(2)
    with col1:
        today = datetime.datetime.now().date()
        default_lookback = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        lookback_date = st.date_input(
            "Show tickets updated since", 
            value=datetime.datetime.strptime(default_lookback, "%Y-%m-%d").date(),
            max_value=today
        )
    
    # Company selector for admins
    with col2:
        if client_code == "admin":
            companies = freshdesk_api.get_companies()
            company_options = {
                c["name"]: c["id"] for c in companies
            }
            company_options["All Companies"] = None
            selected_company = st.selectbox(
                "Select company", 
                options=["All Companies"] + list(company_options.keys()),
                key="over_estimate_company_select"
            )
            company_id = company_options[selected_company]
        else:
            # For non-admin users, get their company ID
            companies = freshdesk_api.get_companies()
            company_id = None
            for c in companies:
                if c['custom_fields'].get('company_code') == client_code:
                    company_id = c['id']
                    break

    # Show progress information while fetching data
    import time
    start_time = time.time()
    
    # Create placeholders for progress reporting
    fetch_status = st.empty()
    fetch_status.info(f"Fetching tickets updated since {lookback_date}...")
    
    # Get tickets updated since specified date
    updated_since = lookback_date.strftime("%Y-%m-%d")
    tickets = freshdesk_api.get_tickets(updated_since=updated_since)
    
    # Filter by company if needed
    if company_id:
        tickets = [t for t in tickets if t.get('company_id') == company_id]
    
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    using_cached_data = elapsed_time < 0.5  # Less than 500ms probably means cached data
    
    # Only show success toast for fresh data
    if not using_cached_data:
        st.toast(f"Found {len(tickets)} tickets to analyze", icon="✅")
    
    # Clean up status message
    fetch_status.empty()
    
    if not tickets:
        st.info("No tickets found within the selected parameters.")
        return
    
    # Calculate time spent for each ticket
    over_estimate_tickets = []
    
    # Create progress indicators for ticket analysis
    progress_status = st.empty()
    progress_bar = st.empty()
    
    # Start time for this operation
    analysis_start_time = time.time()
    
    # Show initial status
    progress_status.info(f"Analyzing {len(tickets)} tickets for time entries...")
    
    # Process each ticket with progress updates
    for i, ticket in enumerate(tickets):
        # Update progress
        progress_percent = i / len(tickets)
        progress_bar.progress(progress_percent)
        
        # Update status periodically
        if i % max(1, len(tickets) // 10) == 0:
            progress_status.info(f"Analyzing tickets... ({i}/{len(tickets)} - {int(progress_percent*100)}%)")
        ticket_id = ticket['id']
        
        # Extract estimate from custom fields
        estimate_value = ticket['custom_fields'].get('estimate_hrs')
        if estimate_value and isinstance(estimate_value, str) and estimate_value.replace('.', '', 1).isdigit():
            estimate = float(estimate_value)
        else:
            estimate = 0.0
        
        # Skip tickets with no estimate
        if estimate <= 0:
            continue
        
        # Get all time entries for this ticket
        try:
            time_entries = freshdesk_api.get_time_entries(ticket_id=ticket_id)
            total_time = sum([float(entry.get('time_spent_in_seconds', 0)) / 3600.0 for entry in time_entries])
        except Exception as e:
            # Skip this ticket if we can't get time entries
            continue
        
        # Check if time exceeds estimate
        if total_time > estimate:
            # Get additional ticket details
            company_name = "Unknown"
            if ticket.get('company_id'):
                company = freshdesk_api.get_company_by_id(ticket['company_id'])
                company_name = company.get('name', 'Unknown')
                
            # Get agent information
            agent_name = "Unassigned"
            if ticket.get('responder_id'):
                agent = freshdesk_api.get_agent(ticket['responder_id'])
                agent_name = agent.get('contact', {}).get('name', 'Unknown')
                
            # Get group information
            group_name = "None"
            if ticket.get('group_id'):
                group = freshdesk_api.get_group(ticket['group_id'])
                group_name = group.get('name', 'Unknown')
                
            # Get product information
            product_name = "Unknown"
            if ticket.get('product_id'):
                product_options = freshdesk_api.get_product_options()
                product_name = product_options.get(ticket.get('product_id'), "Unknown")
                
            # Get category information
            category = "Unknown"
            if ticket.get('custom_fields') and ticket['custom_fields'].get('category'):
                category = ticket['custom_fields'].get('category')
                
            over_estimate_tickets.append({
                'id': ticket_id,
                'subject': ticket.get('subject', 'No subject'),
                'status': status_mapping.get(ticket.get('status'), ticket.get('status')),
                'company': company_name,
                'assigned_to': agent_name,
                'group': group_name,
                'product_name': product_name,
                'category': category,
                'estimate': estimate,
                'total_time': total_time,
                'over_by': total_time - estimate,
                'over_by_percent': ((total_time - estimate) / estimate) * 100 if estimate > 0 else 0,
                'created_at': ticket.get('created_at'),
                'updated_at': ticket.get('updated_at')
            })
    
    # Complete the progress and clean up
    progress_bar.progress(1.0)
    
    # Calculate elapsed time for analysis
    analysis_elapsed_time = time.time() - analysis_start_time
    analysis_using_cached = analysis_elapsed_time < 0.5  # Less than 500ms means cached
    
    # Only show success toast for fresh data
    if not analysis_using_cached:
        st.toast(f"Analyzed {len(tickets)} tickets for time entries", icon="✅")
    
    # Clear progress indicators
    progress_status.empty()
    progress_bar.empty()
    
    if not over_estimate_tickets:
        st.info("No tickets over estimate found.")
        return
        
    # Convert to DataFrame and sort
    df = pd.DataFrame(over_estimate_tickets)
    df = df.sort_values('over_by_percent', ascending=False)
    
    # Add URL column for clickable links
    df['ticket_url'] = df['id'].apply(
        lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
    )
    
    # Format dates
    df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
    df['updated_at'] = pd.to_datetime(df['updated_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # Apply sidebar filters if provided
    filtered_df = df.copy()
    if filter_groups:
        # Convert tuple back to list for isin
        filtered_df = filtered_df[filtered_df['group'].isin(list(filter_groups))]
    if filter_products:
        # Convert tuple back to list for isin
        filtered_df = filtered_df[filtered_df['product_name'].isin(list(filter_products))]
    if filter_categories:
        # Convert tuple back to list for isin
        filtered_df = filtered_df[filtered_df['category'].isin(list(filter_categories))]
    
    # Show filter results
    total_count = len(df)
    filtered_count = len(filtered_df)
    
    if filtered_count < total_count:
        st.caption(f"Found {filtered_count} of {total_count} tickets over estimate (after filtering)")
    else:
        st.caption(f"Found {total_count} tickets over estimate")
    
    st.dataframe(
        filtered_df[['ticket_url', 'over_by_percent', 'subject', 'company', 'status', 'category', 'assigned_to', 'group', 
            'product_name', 'estimate', 'total_time', 'over_by', 'updated_at']],
        column_config={
            'ticket_url': st.column_config.LinkColumn("ID", display_text="tickets/(\d+)"),
            'over_by_percent': st.column_config.ProgressColumn("Over by (%)", format="%.1f%%", min_value=0, max_value=100),
            'subject': "Subject",
            'company': "Company",
            'status': "Status",
            'category': "Category",
            'assigned_to': "Assigned to",
            'group': "Group",
            'product_name': "Product",
            'estimate': st.column_config.NumberColumn("Estimate (h)", format="%.1f"),
            'total_time': st.column_config.NumberColumn("Total time (h)", format="%.1f"),
            'over_by': st.column_config.NumberColumn("Over by (h)", format="%.1f"),
            'updated_at': st.column_config.DatetimeColumn("Last updated", format="ddd DD MMM YYYY, HH:mm z")
        },
        hide_index=True,
        height=600
    )

def display_aging_unresolved_tickets(client_code: str, filter_groups=None, filter_products=None, filter_categories=None):
    """Display unresolved tickets that have been open for a long time."""
    st.subheader("Aging unresolved tickets")
    
    # Show active filters if any
    if filter_groups or filter_products or filter_categories:
        filters_text = []
        if filter_groups:
            filters_text.append(f"Groups: {', '.join(filter_groups)}")
        if filter_products:
            filters_text.append(f"Products: {', '.join(filter_products)}")
        if filter_categories:
            filters_text.append(f"Categories: {', '.join(filter_categories)}")
        st.caption(f"Active filters: {' | '.join(filters_text)}")
    
    # Get aging threshold in days
    days_threshold = st.slider("Days since last update", 7, 90, 30)
    
    cutoff_date = (datetime.datetime.now() - timedelta(days=days_threshold)).strftime("%Y-%m-%d")
    
    # Company selector for admins
    if client_code == "admin":
        companies = freshdesk_api.get_companies()
        company_options = {
            c["name"]: c["id"] for c in companies
        }
        company_options["All Companies"] = None
        selected_company = st.selectbox(
            "Select company", 
            options=["All Companies"] + list(company_options.keys()),
            key="aging_tickets_company_select"
        )
        company_id = company_options[selected_company]
    else:
        # For non-admin users, get their company ID
        companies = freshdesk_api.get_companies()
        company_id = None
        for c in companies:
            if c['custom_fields'].get('company_code') == client_code:
                company_id = c['id']
                break
    
    # Show progress information while fetching data
    import time
    start_time = time.time()
    
    # Create placeholders for progress reporting
    fetch_status = st.empty()
    fetch_status.info(f"Fetching all tickets...")
    
    # Get all tickets
    tickets = freshdesk_api.get_tickets()
    
    # Filter by company if needed
    if company_id:
        tickets = [t for t in tickets if t.get('company_id') == company_id]
    
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    using_cached_data = elapsed_time < 0.5  # Less than 500ms probably means cached data
    
    # Only show success toast for fresh data
    if not using_cached_data:
        st.toast(f"Found {len(tickets)} tickets to analyze", icon="✅")
    
    # Clean up status message
    fetch_status.empty()
    
    # Create progress indicators for ticket analysis
    progress_status = st.empty()
    progress_bar = st.empty()
    
    # Start time for analysis
    analysis_start_time = time.time()
    
    # Show initial status
    progress_status.info(f"Analyzing {len(tickets)} tickets for aging issues...")
    progress_bar.progress(0.0)
    
    # Filter out resolved/closed/deferred and waiting on customer tickets
    EXCLUDED_STATUSES = [3, 4, 5, 6, 12]  # Resolved, Closed, Deferred, Waiting on Customer, Deferred
    aging_tickets = []
    
    # Process each ticket with progress updates
    for i, ticket in enumerate(tickets):
        # Update progress
        progress_percent = i / len(tickets)
        progress_bar.progress(progress_percent)
        
        # Update status periodically
        if i % max(1, len(tickets) // 10) == 0:
            progress_status.info(f"Analyzing tickets... ({i}/{len(tickets)} - {int(progress_percent*100)}%)")
            
        # Skip if ticket has a status we want to exclude
        if ticket.get('status') in EXCLUDED_STATUSES:
            continue
            
        # Skip if updated recently
        updated_at = ticket.get('updated_at', '')
        if updated_at > cutoff_date:
            continue
            
        # Get company name
        company_name = "Unknown"
        if ticket.get('company_id'):
            company = freshdesk_api.get_company_by_id(ticket['company_id'])
            company_name = company.get('name', 'Unknown')
            
        # Get agent information
        agent_name = "Unassigned"
        if ticket.get('responder_id'):
            agent = freshdesk_api.get_agent(ticket['responder_id'])
            agent_name = agent.get('contact', {}).get('name', 'Unknown')
            
        # Get group information
        group_name = "None"
        if ticket.get('group_id'):
            group = freshdesk_api.get_group(ticket['group_id'])
            group_name = group.get('name', 'Unknown')
            
        # Get ticket type
        ticket_type = ticket['custom_fields'].get('cf_type', 'Unknown')
        
        # Get product information
        product_name = "Unknown"
        if ticket.get('product_id'):
            product_options = freshdesk_api.get_product_options()
            product_name = product_options.get(ticket.get('product_id'), "Unknown")
            
        # Get category information
        category = "Unknown"
        if ticket.get('custom_fields') and ticket['custom_fields'].get('category'):
            category = ticket['custom_fields'].get('category')
            
        # Calculate days since last update
        updated_date = datetime.datetime.strptime(updated_at.split('T')[0], '%Y-%m-%d').date()
        days_since_update = (datetime.datetime.now().date() - updated_date).days
            
        aging_tickets.append({
            'id': ticket.get('id'),
            'subject': ticket.get('subject', 'No subject'),
            'status': status_mapping.get(ticket.get('status'), ticket.get('status')),
            'company': company_name,
            'assigned_to': agent_name,
            'group': group_name,
            'product_name': product_name,
            'category': category,
            'ticket_type': ticket_type,
            'days_since_update': days_since_update,
            'created_at': ticket.get('created_at'),
            'updated_at': updated_at
        })
    
    # Complete the progress and clean up
    progress_bar.progress(1.0)
    
    # Calculate elapsed time for analysis
    analysis_elapsed_time = time.time() - analysis_start_time
    analysis_using_cached = analysis_elapsed_time < 0.5  # Less than 500ms means cached
    
    # Only show success toast for fresh data
    if not analysis_using_cached:
        st.toast(f"Analyzed {len(tickets)} tickets for aging issues", icon="✅")
    
    # Clear progress indicators
    progress_status.empty()
    progress_bar.empty()
    
    if not aging_tickets:
        st.info(f"No unresolved tickets found that haven't been updated in the last {days_threshold} days.")
        return
        
    # Convert to DataFrame and sort by days_since_update
    df = pd.DataFrame(aging_tickets)
    df = df.sort_values('days_since_update', ascending=False)
    
    # Add URL column for clickable links
    df['ticket_url'] = df['id'].apply(
        lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
    )
    
    # Format dates
    df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
    df['updated_at'] = pd.to_datetime(df['updated_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # Apply sidebar filters if provided
    filtered_df = df.copy()
    if filter_groups:
        # Convert tuple back to list for isin
        filtered_df = filtered_df[filtered_df['group'].isin(list(filter_groups))]
    if filter_products:
        # Convert tuple back to list for isin
        filtered_df = filtered_df[filtered_df['product_name'].isin(list(filter_products))]
    if filter_categories:
        # Convert tuple back to list for isin
        filtered_df = filtered_df[filtered_df['category'].isin(list(filter_categories))]
    
    # Show filter results
    total_count = len(df)
    filtered_count = len(filtered_df)
    
    # Create status note explaining excluded statuses
    excluded_status_names = [status_mapping.get(status, str(status)) for status in EXCLUDED_STATUSES]
    excluded_status_note = f"(excludes {', '.join(excluded_status_names)} tickets)"
    
    if filtered_count < total_count:
        st.caption(f"Found {filtered_count} of {total_count} aging tickets that haven't been updated in {days_threshold} days {excluded_status_note} (after filtering)")
    else:
        st.caption(f"Found {total_count} aging tickets that haven't been updated in {days_threshold} days {excluded_status_note}")
    
    st.dataframe(
        filtered_df[['ticket_url', 'days_since_update', 'subject', 'company', 'status', 'category', 'assigned_to', 'group', 
            'product_name', 'ticket_type', 'updated_at']],
        column_config={
            'ticket_url': st.column_config.LinkColumn("ID", display_text="tickets/(\d+)"),
            'subject': "Subject",
            'company': "Company",
            'status': "Status",
            'category': "Category",
            'assigned_to': "Assigned to",
            'group': "Group",
            'product_name': "Product",
            'ticket_type': "Type",
            'days_since_update': st.column_config.ProgressColumn("Days since update", format="%d", min_value=0, max_value=days_threshold * 2),
            'updated_at': st.column_config.DatetimeColumn("Last updated", format="ddd DD MMM YYYY, HH:mm z")
        },
        hide_index=True,
        height=600
    )