# views/xero.py

import streamlit as st
import pandas as pd
import base64
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from apis.freshdesk import freshdesk_api
from logic import calculate_billable_time
from utils import month_selector

def display_xero_exporter():
    st.info('''
        This tool generates a CSV for importing into Xero. Known limitations:
        * Does not account for rollover hours.
        * Does not include line items for retainer hours.
        
        Please handle these manually for now.
    ''')

    # Month selector using the helper from utils.py
    selected_month = month_selector(label="Choose a month")
    selected_date = datetime.strptime(selected_month, "%B %Y")
    start_date = selected_date.strftime("%Y-%m-%d")
    end_date = (selected_date + relativedelta(months=1) - timedelta(days=1)).strftime("%Y-%m-%d")

    if st.button("Generate CSV for Xero"):
        # Fetch time entries and company details
        time_entries_data = freshdesk_api.get_time_entries(start_date, end_date)
        products = freshdesk_api.get_product_options()
        
        # Prepare detailed tickets
        tickets_details = prepare_tickets_details_from_time_entries(time_entries_data, products)

        # Add invoice numbers and filter relevant data
        for ticket in tickets_details:
            if ticket['company_code']:
                ticket['InvoiceNumber'] = f"S-{ticket['company_code']}{selected_date.strftime('%y%-m')}"
        
        tickets_details_df = pd.DataFrame(tickets_details)
        tickets_details_df = tickets_details_df[tickets_details_df['company_code'] != "—"]
        tickets_details_df = tickets_details_df[tickets_details_df['hourly_rate'].notnull()]
        st.write(tickets_details_df)
        # Map and transform for Xero CSV
        tickets_details_df['Description'] = tickets_details_df.apply(
            lambda row: (
                f"{row['ticket_id']} – {row['title']} [{row['product']}]" +
                (" [Change Request]" if row['change_request'] else "")
            ),
            axis=1
        )
        tickets_details_df = tickets_details_df.rename(columns={
            'company': 'ContactName',
            'company_code': 'ContactCode',
            'hourly_rate': 'UnitAmount',
            'billable_time_this_month': 'Quantity',
            'currency': 'Currency'
        })
        tickets_details_df['InvoiceDate'] = (selected_date + relativedelta(months=1) - timedelta(days=1)).strftime("%Y-%m-%d")
        tickets_details_df['DueDate'] = (selected_date + relativedelta(months=2) - timedelta(days=1)).strftime("%Y-%m-%d")
        # Generate downloadable CSV
        csv = tickets_details_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="upload_me_to_xero_for_a_good_time.csv">Click here to download the CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

    if st.button("Clear caches"):
        st.cache_data.clear()

def prepare_tickets_details_from_time_entries(time_entries, products):
    details = []
    companies = {c['id']: c for c in freshdesk_api.get_companies()}

    for entry in time_entries:
        ticket_id = entry.get('ticket_id')
        if not ticket_id:
            continue

        ticket_data = freshdesk_api.get_ticket_data(ticket_id)
        company_id = ticket_data.get('company_id')
        company = companies.get(company_id, {})

        # Fetch company_code and hourly_rate
        company_code = company.get('custom_fields', {}).get('company_code', "—")
        hourly_rate = company.get('custom_fields', {}).get('contract_hourly_rate') or ticket_data.get('custom_fields', {}).get('contract_hourly_rate')

        product_name = products.get(ticket_data.get('product_id'), "Unknown")
        time_hours = float(entry.get('time_spent_in_seconds', 0)) / 3600.0
        billable_hours = calculate_billable_time(entry, ticket_data, time_hours, products)

        details.append({
            'time_spent_this_month': time_hours,
            'billable_time_this_month': billable_hours,
            'ticket_id': ticket_id,
            'title': ticket_data.get('subject', 'No subject'),
            'company': ticket_data.get('company_name', 'Unknown'),
            'company_code': company_code,
            'hourly_rate': hourly_rate,
            'currency': ticket_data.get('custom_fields', {}).get('currency', 'USD'),
            'product': product_name,
            'change_request': ticket_data.get('custom_fields', {}).get('change_request', False),
        })
    return details