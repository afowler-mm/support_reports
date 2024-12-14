import streamlit as st
import pandas as pd
import base64
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from apis.freshdesk import freshdesk_api
from logic import calculate_billable_time
from utils import month_selector

def display_xero_exporter(client_code):
    st.warning('Not recently tested. Use with caution and let Andrew SF know if something needs changing.')
    
    st.info('''
        This tool generates a CSV for importing into Xero. Known limitations:
        * Does not account for rollover hours.
        * Does not include line items for retainer hours.
        
        Please handle these manually for now.
    ''')

    # Use the month_selector from utils.py
    selected_month = month_selector()
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

        # Add extra Xero columns
        for col in [
            'EmailAddress', 'POAddressLine1', 'POAddressLine2', 'POAddressLine3',
            'POAddressLine4', 'POCity', 'PORegion', 'POPostalCode', 'POCountry',
            'Total', 'InventoryItemCode', 'Discount', 'AccountCode', 'TaxType',
            'TaxAmount', 'TrackingName1', 'TrackingOption1', 'TrackingName2',
            'TrackingOption2'
        ]:
            tickets_details_df[col] = None
        
        tickets_details_df['AccountCode'] = '4010'
        tickets_details_df['TaxType'] = 'Tax Exempt (0%)'
        
        tickets_details_df = tickets_details_df.sort_values(by=['InvoiceNumber', 'Description'])

        # Reorder columns to match Xero's expected format
        columns_for_xero = [
            'ContactName', 'EmailAddress', 'POAddressLine1', 'POAddressLine2',
            'POAddressLine3', 'POAddressLine4', 'POCity', 'PORegion', 'POPostalCode',
            'POCountry', 'InvoiceNumber', 'InvoiceDate', 'DueDate', 'Total',
            'InventoryItemCode', 'Description', 'Quantity', 'UnitAmount', 'Discount',
            'AccountCode', 'TaxType', 'TaxAmount', 'TrackingName1', 'TrackingOption1',
            'TrackingName2', 'TrackingOption2', 'Currency'
        ]
        tickets_details_df = tickets_details_df[columns_for_xero]

        # Generate downloadable CSV
        csv = tickets_details_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="upload_me_to_xero.csv">Click here to download the CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

        # Display a preview of the data
        with st.expander("Preview the CSV Data"):
            st.write(tickets_details_df)

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

        # Fetch company_code, hourly_rate, and currency
        company_code = company.get('custom_fields', {}).get('company_code', "—")
        hourly_rate = company.get('custom_fields', {}).get('contract_hourly_rate') or ticket_data.get('custom_fields', {}).get('contract_hourly_rate')
        currency = company.get('custom_fields', {}).get('currency', 'USD')  # Fetch the currency here

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
            'currency': currency,  # Include the correct currency
            'product': product_name,
            'change_request': ticket_data.get('custom_fields', {}).get('change_request', False),
        })
    return details