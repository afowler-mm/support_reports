import streamlit as st
import datetime
import pandas as pd

from utils import month_selector
from apis.freshdesk import freshdesk_api


def display_monthly_report(client_code: str):
    st.subheader(f"Monthly report for {client_code}")

    # Allow user to pick a month
    selected_month = month_selector()
    st.write(f"Selected month: {selected_month}")

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

    # Get product options if needed
    product_options = freshdesk_api.get_product_options()

    # Fetch time entries for the given month and company
    time_entries_data = freshdesk_api.get_time_entries(start_date, end_date, company_id)

    if not time_entries_data:
        st.write("No time tracked for this month")
        return

    # Convert time entries to DataFrame
    time_entries_df = pd.DataFrame(time_entries_data)
    # You may need to process this similarly to your old code to get tickets_details
    tickets_details = prepare_tickets_details_from_time_entries(time_entries_data, product_options)

    if not tickets_details:
        st.write("No detailed tickets found.")
        return

    tickets_details_df = pd.DataFrame(tickets_details)

    # Display the time summary
    display_time_summary(tickets_details_df, company_data, start_date)


def prepare_tickets_details_from_time_entries(time_entries_data, product_options):
    """
    Mimic your old logic:
    - For each time entry, fetch ticket info
    - Summarize total and billable time
    - Attach product names, requester info, etc.
    """
    # Placeholder for demonstration. Your real logic might be more complex:
    details = []
    for entry in time_entries_data:
        ticket_id = entry.get('ticket_id')
        ticket_data = freshdesk_api.get_ticket_data(ticket_id)
        requester_name = "Unknown"
        if ticket_data.get('requester_id'):
            requester = freshdesk_api.get_requester(ticket_data['requester_id'])
            requester_name = requester.get('name', 'Unknown')

        product_name = product_options.get(ticket_data.get('product_id'), "Unknown")

        # Convert time spent from seconds to hours
        time_hours = float(entry.get('time_spent_in_seconds',0))/3600.0
        # billable_hours = calculate_billable_time(ticket_data, time_hours)
        billable_hours = ''

        details.append({
            'ticket_id': ticket_id,
            'title': ticket_data.get('subject', 'No subject'),
            'requester_name': requester_name,
            'product_name': product_name,
            'time_spent_this_month': time_hours,
            'billable_time_this_month': billable_hours,
            'billing_status': ticket_data['custom_fields'].get('billing_status', 'Unknown')
        })

    return details

def display_time_summary(tickets_details_df, company_data, start_date):
    year, month, _ = start_date.split("-")

    total_time = f"{tickets_details_df['time_spent_this_month'].sum()} h"
    billable_time = f"{tickets_details_df['billable_time_this_month'].sum()} h"
    carryover_value = 0;
    rollover_time = "{:.1f} h".format(float(carryover_value)) if carryover_value and str(carryover_value).replace(".", "", 1).isdigit() else None

    now = datetime.datetime.now()
    start_date_year, start_date_month = map(int, start_date.split("-")[:2])
    is_current_or_adjacent_month = (now.year == start_date_year and abs(now.month - start_date_month) <= 1)
    currency_symbol = "¢"  # Placeholder

    total_billable_hours = 0 # Placeholder
    overage_rate = company_data['custom_fields'].get('contract_hourly_rate', 0)
    carryover = float(carryover_value) if rollover_time else 0

    estimated_cost = f"{currency_symbol}{max(total_billable_hours - carryover, 0) * overage_rate:,.2f}" if is_current_or_adjacent_month else f"{currency_symbol}0.00"

    time_summary_contents = {
        "Total time tracked": total_time,
        "Of which potentially billable": billable_time,
    }

    inclusive_hours = company_data['custom_fields'].get('inclusive_hours')
    if inclusive_hours and is_current_or_adjacent_month:
        time_summary_contents["Support contract includes"] = f"{inclusive_hours:.0f} h"
    if rollover_time:
        time_summary_contents["Rollover time available"] = rollover_time
    if overage_rate and is_current_or_adjacent_month:
        time_summary_contents["Hourly rate for overages"] = f"{currency_symbol}{overage_rate:,.0f}"
    if is_current_or_adjacent_month:
        time_summary_contents["Estimated cost this month"] = estimated_cost

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
    formatted_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %Y')
    st.markdown(f"#### Made Media support tickets with time tracked during {formatted_date} for {company_data['name']}")
    _display_tickets_table(tickets_details_df)

def _display_tickets_table(tickets_details_df):
    tickets_html = "<table>"
    tickets_html += "<tr><th>Ticket</th><th align='right'>Time tracked this month</th><th align='right'>Potentially billable</th></tr>"
    for _, ticket in tickets_details_df.iterrows():
        tickets_html += "<tr>"
        tickets_html += f"<td><h6 style='padding-bottom:0;margin-bottom:0'><a href='https://mademedia.freshdesk.com/support/tickets/{ticket['ticket_id']}'>{ticket['ticket_id']}</a>: {ticket['title']}</h6><small>Filed by: {ticket['requester_name']}</small></td>"
        tickets_html += f"<td align='right'>{ticket['time_spent_this_month']} hours</td>"
        tickets_html += f"<td align='right'>{ticket['billable_time_this_month']} hours</td>"
        tickets_html += "</tr>"
    tickets_html += "</table>"

    st.markdown(tickets_html, unsafe_allow_html=True)