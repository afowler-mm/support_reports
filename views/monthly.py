import streamlit as st
import datetime
import pandas as pd

from collections import defaultdict

from utils import month_selector, get_support_contract_data
from apis.freshdesk import freshdesk_api
from apis.google import setup_google_sheets
from logic import calculate_billable_time


def display_monthly_report(client_code: str):
    if client_code == "admin":
        st.info("Want to give a client access to this report? Add credentials for them to [this spreadsheet](https://docs.google.com/spreadsheets/d/11RbGbkxKeIqrjweIClMh2a14hwt1-wWP0tKkAI7gvIQ/edit?gid=0#gid=0).")
        companies = freshdesk_api.get_companies()
        company_names = {c['name']: c['custom_fields'].get('company_code') for c in companies}
        selected_company_name = st.selectbox("Select client", list(company_names.keys()))
        client_code = company_names[selected_company_name]
    
    # Allow user to pick a month
    selected_month = month_selector()

    # Convert selected month (e.g. "January 2024") to YYYY-MM-DD date range
    month_datetime = datetime.datetime.strptime(selected_month, "%B %Y")
    start_date = month_datetime.strftime("%Y-%m-01")
    # End date: the end of the selected month
    next_month = month_datetime + datetime.timedelta(days=32)
    end_of_month = datetime.datetime(next_month.year, next_month.month, 1) - datetime.timedelta(days=1)
    end_date = end_of_month.strftime("%Y-%m-%d")

    companies = freshdesk_api.get_companies()
    company_id = None
    for c in companies:
        if c['custom_fields'].get('company_code') == client_code:
            company_id = c['id']
            company_data = c
            break

    if not company_id:
        st.error("Company not found for this client code.")
        return

    # Show progress information while fetching data
    import time
    start_time = time.time()
    
    # Create placeholders for progress reporting
    fetch_status = st.empty()
    fetch_status.info(f"Fetching product options and time entries...")
    
    # Fetch product options
    product_options = freshdesk_api.get_product_options()

    # Fetch time entries for the given month and company
    fetch_status.info(f"Fetching time entries for {selected_month}...")
    time_entries_data = freshdesk_api.get_time_entries(start_date, end_date, company_id)

    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    using_cached_data = elapsed_time < 0.5  # Less than 500ms probably means cached data
    
    # Only show success toast for fresh data
    if not using_cached_data and time_entries_data:
        st.toast(f"✓ Found {len(time_entries_data)} time entries to analyze", icon="✅")
    
    # Clean up status message
    fetch_status.empty()
    
    if not time_entries_data:
        st.write("No time tracked for this month")
        return

    time_entries_df = pd.DataFrame(time_entries_data)
    
    # Process the time entries with progress reporting
    tickets_details = prepare_tickets_details_from_time_entries(time_entries_data, product_options, selected_month)

    if not tickets_details:
        st.write("No detailed tickets found.")
        return

    # Process the tickets_details list to ensure all field values are hashable
    for ticket in tickets_details:
        for field in list(ticket.keys()):
            if isinstance(ticket[field], list):
                ticket[field] = tuple(ticket[field])
                
    # Now create the DataFrame from the sanitized data
    tickets_details_df = pd.DataFrame(tickets_details)

    # Display the time summary
    display_time_summary(tickets_details_df, company_data, start_date)


def prepare_tickets_details_from_time_entries(time_entries_data, product_options, selected_month=None):
    # Track execution time
    import time
    analysis_start_time = time.time()
    
    # Create progress indicators
    progress_status = st.empty()
    progress_bar = st.empty()
    
    # Show initial status
    month_text = f" for {selected_month}" if selected_month else ""
    progress_status.info(f"Analyzing {len(time_entries_data)} time entries{month_text}...")
    progress_bar.progress(0.0)
    
    # Make sure all default values are hashable
    details = defaultdict(lambda: {
        'time_spent_this_month': 0.0,
        'billable_time_this_month': 0.0,
        'total_time_spent': 0.0,
        'total_billable_time': 0.0,
        'ticket_id': None,
        'title': None,
        'requester_name': "Unknown",
        'product_name': "Unknown",
        'billing_status': "Unknown",
        'estimate': 0.0,
        'ticket_type': "Unknown",
        'group_name': "Unknown",
        'agent_name': "Unknown",
        # Make sure change_request is present and hashable
        'change_request': False
    })

    # Process each time entry with progress updates
    for i, entry in enumerate(time_entries_data):
        # Update progress bar
        progress_percent = i / len(time_entries_data)
        progress_bar.progress(progress_percent)
        
        # Update status message periodically
        if i % max(1, len(time_entries_data) // 10) == 0:
            progress_status.empty()  # Clear previous message
            progress_status.info(f"Processing time entries... ({i}/{len(time_entries_data)} - {int(progress_percent*100)}%)")
            
        ticket_id = entry.get('ticket_id')
        if not ticket_id:
            continue

        # Get ticket data
        ticket_data = freshdesk_api.get_ticket_data(ticket_id)
        requester_name = "Unknown"
        if ticket_data.get('requester_id'):
            requester = freshdesk_api.get_requester(ticket_data['requester_id'])
            requester_name = requester.get('name', 'Unknown')
        
        # Get agent and group information
        agent_name = "Unassigned"
        if ticket_data.get('responder_id'):
            agent = freshdesk_api.get_agent(ticket_data['responder_id'])
            agent_name = agent.get('contact', {}).get('name', 'Unknown')
        
        group_name = "None"
        if ticket_data.get('group_id'):
            group = freshdesk_api.get_group(ticket_data['group_id'])
            group_name = group.get('name', 'Unknown')
            
        product_name = product_options.get(ticket_data.get('product_id'), "Unknown")

        # Aggregate time spent
        time_hours = float(entry.get('time_spent_in_seconds', 0)) / 3600.0
        # Pass product_options to calculate_billable_time
        billable_hours = calculate_billable_time(entry, ticket_data, time_hours, product_options)

        # Update the details for the ticket
        ticket_detail = details[ticket_id]
        ticket_detail['time_spent_this_month'] += time_hours
        ticket_detail['billable_time_this_month'] += billable_hours
        ticket_detail['ticket_id'] = ticket_id
        ticket_detail['title'] = ticket_data.get('subject', 'No subject')
        ticket_detail['requester_name'] = requester_name
        ticket_detail['product_name'] = product_name
        
        # Get billing status and ensure it's hashable
        billing_status = ticket_data['custom_fields'].get('billing_status', 'Unknown')
        if isinstance(billing_status, list):
            billing_status = tuple(billing_status)
        ticket_detail['billing_status'] = billing_status
        
        ticket_detail['change_request'] = ticket_data['custom_fields'].get('change_request', False)
        
        # Handle estimate
        estimate_value = ticket_data['custom_fields'].get('estimate_hrs')
        if estimate_value and isinstance(estimate_value, str) and estimate_value.replace('.', '', 1).isdigit():
            # If it's a string representing a number, convert to float
            ticket_detail['estimate'] = float(estimate_value)
        else:
            ticket_detail['estimate'] = 0.0
            
        # Get ticket type and ensure it's hashable
        ticket_type = ticket_data['custom_fields'].get('cf_type', 'Unknown')
        if isinstance(ticket_type, list):
            ticket_type = tuple(ticket_type)
        ticket_detail['ticket_type'] = ticket_type
        
        ticket_detail['group_name'] = group_name
        ticket_detail['agent_name'] = agent_name
        
        # Get the total time spent on this ticket (all time, not just this month)
        try:
            all_time_entries = freshdesk_api.get_time_entries(ticket_id=ticket_id)
            total_time = sum([float(entry.get('time_spent_in_seconds', 0)) / 3600.0 for entry in all_time_entries])
            total_billable = sum([calculate_billable_time(entry, ticket_data, float(entry.get('time_spent_in_seconds', 0)) / 3600.0, product_options) for entry in all_time_entries])
            ticket_detail['total_time_spent'] = total_time
            ticket_detail['total_billable_time'] = total_billable
        except Exception as e:
            # If there's an error fetching total time, just use the current month's time
            st.warning(f"Could not fetch total time for ticket #{ticket_id}: {str(e)}")
            ticket_detail['total_time_spent'] = ticket_detail['time_spent_this_month']
            ticket_detail['total_billable_time'] = ticket_detail['billable_time_this_month']

    # Complete the progress and clean up
    progress_bar.progress(1.0)
    
    # Calculate elapsed time for analysis
    analysis_elapsed_time = time.time() - analysis_start_time
    analysis_using_cached = analysis_elapsed_time < 0.5  # Less than 500ms means cached
    
    # Only show success toast for fresh data
    if not analysis_using_cached:
        ticket_count = len(details.values())
        st.toast(f"✓ Analysis complete - processed {ticket_count} tickets", icon="✅")
    
    # Clear progress indicators
    progress_status.empty()
    progress_bar.empty()
    
    return list(details.values())

def display_time_summary(tickets_details_df, company_data, start_date):
    year, month, _ = start_date.split("-")
    month_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d')

    total_time = tickets_details_df['time_spent_this_month'].sum()
    billable_time = tickets_details_df['billable_time_this_month'].sum()
    
    # Show progress for fetching contract data
    import time
    contract_start_time = time.time()
    contract_status = st.empty()
    contract_status.info("Fetching support contract data...")
    
    # Get carryover and inclusive hours from Google Spreadsheet
    google_client = setup_google_sheets(st.secrets["gcp_service_account"])
    company_code = company_data['custom_fields'].get('company_code')
    
    # Get support contract data from the spreadsheet
    support_data = get_support_contract_data(google_client, company_code, month_datetime)
    
    # Calculate elapsed time
    contract_elapsed_time = time.time() - contract_start_time
    contract_using_cached = contract_elapsed_time < 0.5  # Less than 500ms means cached
    
    # Only show success toast for fresh data
    if not contract_using_cached and 'error' not in support_data:
        st.toast(f"✓ Loaded contract data for {month_datetime.strftime('%B %Y')}", icon="✅")
    
    # Clean up status message
    contract_status.empty()
    
    # Use data from the spreadsheet if available, otherwise fall back to company data
    carryover_value = support_data.get('carryover_hours', 0) if 'error' not in support_data else 0
    inclusive_hours = support_data.get('inclusive_hours') if 'error' not in support_data else company_data['custom_fields'].get('inclusive_hours')
    prev_month = support_data.get('prev_month', '')
    
    # Prepare data source info for later use in the expander
    spreadsheet_id = "1OXy-yuN_Qne2Pc7uc18V2eKXiDkWIEp88y68lHG1FDU"
    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    
    if 'error' not in support_data:
        data_source_info = f"Using support contract data from the [support contract spreadsheet]({spreadsheet_url})."
    else:
        data_source_info = f"Could not get data from the spreadsheet: {support_data.get('error')}. Using fallback data from Freshdesk."
    
    # Format hours with one decimal place
    total_time_formatted = f"{total_time:.1f} h"
    billable_time_formatted = f"{billable_time:.1f} h"
    rollover_time = "{:.1f} h".format(float(carryover_value)) if carryover_value and str(carryover_value).replace(".", "", 1).replace("-", "", 1).isdigit() else "0.0 h"
    carryover = float(carryover_value) if carryover_value else 0

    now = datetime.datetime.now()
    start_date_year, start_date_month = map(int, start_date.split("-")[:2])
    is_current_or_adjacent_month = (now.year == start_date_year and abs(now.month - start_date_month) <= 1)
    
    # make the currency labels friendlier
    currency_map = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "AUD": "A$",
        "CAD": "C$",
        "NZD": "NZ$",
        "JPY": "¥",
    }
    currency_symbol = currency_map.get(company_data['custom_fields'].get('currency'), company_data['custom_fields'].get('currency', ''))

    # Use inclusive hours from either spreadsheet or company data
    if inclusive_hours is None:
        inclusive_hours = company_data['custom_fields'].get('inclusive_hours', 0)
    
    # Calculate billable hours after considering contract and rollover
    inclusive_hours = float(inclusive_hours) if inclusive_hours else 0
    overage_hours = max(0, billable_time - inclusive_hours - carryover)
    overage_rate = company_data['custom_fields'].get('contract_hourly_rate', 0)
    estimated_cost = f"{currency_symbol}{overage_hours * overage_rate:,.2f}" if is_current_or_adjacent_month else f"{currency_symbol}0.00"

    # Generate a clear billing summary
    formatted_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %Y')
    
    st.subheader(f"Support hours usage for {formatted_date}")
    
    # Generate a dictionary for metrics
    time_summary_contents = {
        "Total hours tracked": total_time_formatted,
        "Billable hours": billable_time_formatted,
    }
    
    if is_current_or_adjacent_month:
        time_summary_contents["Rollover hours"] = rollover_time
        time_summary_contents["Billable overage"] = f"{overage_hours:.1f} h"
        time_summary_contents["Estimated cost"] = estimated_cost
    
    columns = st.columns(len(time_summary_contents))
    for col, (k, v) in zip(columns, time_summary_contents.items()):
        col.metric(label=k, value=v)

    if is_current_or_adjacent_month and (inclusive_hours > 0 or carryover > 0) and overage_hours > 0:
        with st.expander("Estimated cost breakdown"):
            st.write(f"{billable_time:.1f} billable hours – {inclusive_hours:.1f} contract hours – {carryover:.1f} rollover hours = **{overage_hours:.1f} billable overage hours**")
            st.write(f"{overage_hours:.1f} hours ×  {currency_symbol}{overage_rate} contract rate/hour = **{currency_symbol}{overage_hours * overage_rate:,.2f} estimated cost**")

    # Warn if any tickets are marked "Invoice"
    # Handle both string "Invoice" and tuple with "Invoice" in it
    invoice_tickets = tickets_details_df[
        tickets_details_df["billing_status"].apply(
            lambda x: x == "Invoice" or 
                      (isinstance(x, tuple) and "Invoice" in x)
        )
    ]
    
    if not invoice_tickets.empty:
        num_invoice_tickets = len(invoice_tickets)
        invoice_ticket_ids = invoice_tickets["ticket_id"].tolist()
        invoice_tickets_str = ", ".join([f"[#{tid}](https://mademedia.freshdesk.com/support/tickets/{tid})" for tid in invoice_ticket_ids])
        total_invoice_time = invoice_tickets["time_spent_this_month"].sum()
        st.warning(
            f"Ticket{'s' if num_invoice_tickets > 1 else ''} {invoice_tickets_str} {'are' if num_invoice_tickets > 1 else 'is'} marked 'Invoice' and {'have' if num_invoice_tickets > 1 else 'has'} {total_invoice_time:.1f} hours tracked this month not included in the above totals."
        )

    # Display ticket table
    st.caption(f"Made Media support tickets with time tracked during {formatted_date} for {company_data['name']}")
    _display_tickets_table(tickets_details_df)

def _display_tickets_table(tickets_details_df):
    tickets_details_df["ticket_url"] = tickets_details_df["ticket_id"].apply(
        lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
    )

    # Make a copy of the data to avoid SettingWithCopyWarning
    display_df = tickets_details_df.copy()
    
    # Convert any tuple values to strings for better display
    for col in ["ticket_type", "billing_status"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: ", ".join(str(i) for i in x) if isinstance(x, tuple) else x
            )

    # Select only the columns we want to display
    display_df = display_df[[
        "ticket_url", 
        "title",
        "time_spent_this_month", 
        "billable_time_this_month",
        "total_time_spent",
        "total_billable_time", 
        "estimate",
        "requester_name",
        "agent_name",
        "group_name",
        "product_name",
        "ticket_type",
        "change_request"
    ]].copy()

    display_df.rename(columns={
        "ticket_url": "Ticket",
        "title": "Title",
        "time_spent_this_month": "Time tracked this month",
        "billable_time_this_month": "Billable time this month",
        "total_time_spent": "Total time tracked",
        "total_billable_time": "Total billable time",
        "estimate": "Estimate (h)",
        "requester_name": "Filed by",
        "agent_name": "Assigned to",
        "group_name": "Group",
        "product_name": "Product",
        "ticket_type": "Type",
        "change_request": "CR?"
    }, inplace=True)

    st.dataframe(
        display_df,
        column_config={
            "Ticket": st.column_config.LinkColumn(
                "ID",
                display_text="tickets/(\\d+)"
            ),
            "Estimate (h)": st.column_config.NumberColumn(
                "Estimate (h)",
                format="%.1f"
            ),
            "Total time tracked": st.column_config.NumberColumn(
                "Total time tracked",
                format="%.1f"
            ),
            "Total billable time": st.column_config.NumberColumn(
                "Total billable time",
                format="%.1f"
            ),
        },
        hide_index=True,
    )
