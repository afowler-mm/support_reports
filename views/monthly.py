import streamlit as st
import datetime
import pandas as pd

from collections import defaultdict

from utils import month_selector
from apis.freshdesk import freshdesk_api
from logic import calculate_billable_time


def display_monthly_report(client_code: str):

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

    product_options = freshdesk_api.get_product_options()

    # Fetch time entries for the given month and company
    time_entries_data = freshdesk_api.get_time_entries(start_date, end_date, company_id)

    if not time_entries_data:
        st.write("No time tracked for this month")
        return

    time_entries_df = pd.DataFrame(time_entries_data)
    product_options = freshdesk_api.get_product_options()
    tickets_details = prepare_tickets_details_from_time_entries(time_entries_data, product_options)

    if not tickets_details:
        st.write("No detailed tickets found.")
        return

    tickets_details_df = pd.DataFrame(tickets_details)

    # Display the time summary
    display_time_summary(tickets_details_df, company_data, start_date)


def prepare_tickets_details_from_time_entries(time_entries_data, product_options):
    details = defaultdict(lambda: {
        'time_spent_this_month': 0.0,
        'billable_time_this_month': 0.0,
        'ticket_id': None,
        'title': None,
        'requester_name': "Unknown",
        'product_name': "Unknown",
        'billing_status': "Unknown"
    })

    for entry in time_entries_data:
        ticket_id = entry.get('ticket_id')
        if not ticket_id:
            continue

        # Get ticket data
        ticket_data = freshdesk_api.get_ticket_data(ticket_id)
        requester_name = "Unknown"
        if ticket_data.get('requester_id'):
            requester = freshdesk_api.get_requester(ticket_data['requester_id'])
            requester_name = requester.get('name', 'Unknown')
        
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
        ticket_detail['billing_status'] = ticket_data['custom_fields'].get('billing_status', 'Unknown')
        ticket_detail['change_request'] = ticket_data['custom_fields'].get('change_request', False)

    return list(details.values())

def display_time_summary(tickets_details_df, company_data, start_date):
    year, month, _ = start_date.split("-")

    total_time = f"{tickets_details_df['time_spent_this_month'].sum():.1f} h"
    billable_time = f"{tickets_details_df['billable_time_this_month'].sum():.1f} h"
    carryover_value = 0;
    rollover_time = "{:.1f} h".format(float(carryover_value)) if carryover_value and str(carryover_value).replace(".", "", 1).isdigit() else None

    now = datetime.datetime.now()
    start_date_year, start_date_month = map(int, start_date.split("-")[:2])
    is_current_or_adjacent_month = (now.year == start_date_year and abs(now.month - start_date_month) <= 1)
    
    currency_map = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "AUD": "A$",
        "CAD": "C$",
    }
    currency_symbol = currency_map.get(company_data['custom_fields'].get('currency'), "$")

    total_billable_hours = tickets_details_df['billable_time_this_month'].sum()
    overage_rate = company_data['custom_fields'].get('contract_hourly_rate', 0)
    carryover = float(carryover_value) if rollover_time else 0
    inclusive_hours = company_data['custom_fields'].get('inclusive_hours')

    estimated_cost = f"{currency_symbol}{max(total_billable_hours - carryover - inclusive_hours, 0) * overage_rate:,.2f}" if is_current_or_adjacent_month else f"{currency_symbol}0.00"

    time_summary_contents = {
        "Total time tracked": total_time,
        "Of which potentially billable": billable_time,
    }

    
    if inclusive_hours and is_current_or_adjacent_month:
        time_summary_contents["Support contract includes"] = f"{inclusive_hours:.0f} h"
    if rollover_time:
        time_summary_contents["Rollover time available"] = rollover_time
    if overage_rate and is_current_or_adjacent_month:
        time_summary_contents["Hourly rate for overages"] = f"{currency_symbol}{overage_rate:,.0f}"
    if is_current_or_adjacent_month:
        time_summary_contents["Estimated cost this month"] = estimated_cost

    formatted_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %Y')
    

    columns = st.columns(len(time_summary_contents))
    for col, (k, v) in zip(columns, time_summary_contents.items()):
        col.metric(label=k, value=v)

    # Warn if any tickets are marked "Invoice"
    invoice_tickets = tickets_details_df[tickets_details_df["billing_status"] == "Invoice"]
    if not invoice_tickets.empty:
        num_invoice_tickets = len(invoice_tickets)
        invoice_ticket_ids = invoice_tickets["ticket_id"].tolist()
        invoice_tickets_str = ", ".join([f"[#{tid}](https://mademedia.freshdesk.com/support/tickets/{tid})" for tid in invoice_ticket_ids])
        total_invoice_time = invoice_tickets["time_spent_this_month"].sum()
        st.warning(
            f"Ticket{'s' if num_invoice_tickets > 1 else ''} {invoice_tickets_str} {'are' if num_invoice_tickets > 1 else 'is'} marked 'Invoice' and have {total_invoice_time:.1f} hours tracked this month not included in the above totals."
        )

    # Display ticket table
    st.caption(f"Made Media support tickets with time tracked during {formatted_date} for {company_data['name']}")
    _display_tickets_table(tickets_details_df)

def _display_tickets_table(tickets_details_df):
    tickets_details_df["ticket_url"] = tickets_details_df["ticket_id"].apply(
        lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
    )

    display_df = tickets_details_df[[
        "ticket_url", 
        "title",
        "time_spent_this_month", 
        "billable_time_this_month", 
        "requester_name",
        "product_name",
        "change_request"
    ]].copy()

    display_df.rename(columns={
        "ticket_url": "Ticket",
        "title": "Title",
        "time_spent_this_month": "Time tracked",
        "billable_time_this_month": "Billable time",
        "requester_name": "Filed by",
        "product_name": "Product",
        "change_request": "CR?"
    }, inplace=True)

    st.dataframe(
        display_df,
        column_config={
            "Ticket": st.column_config.LinkColumn(
                "ID",
                display_text="tickets/(\\d+)"
            ),
        },
        hide_index=True,
    )
