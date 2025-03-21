import streamlit as st
import pandas as pd
import base64
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from apis.freshdesk import freshdesk_api
from apis.google import setup_google_sheets
from logic import calculate_billable_time
from utils import month_selector, get_support_contract_data

def display_xero_exporter(client_code):
    st.warning('Not recently tested. Use with caution and let Andrew SF know if something needs changing.')
    
    st.info('''
        This tool generates a CSV for importing into Xero. Known limitations:
        * Does not account for rollover hours.
        * Does not include line items for retainer hours.
        
        Please handle these manually for now.
    ''')

    selected_month = month_selector(label="Select a month")
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
                
                # If we have contract data, add a line in the description
                if 'carryover_hours' in ticket and ticket['carryover_hours'] > 0 or 'inclusive_hours' in ticket and ticket['inclusive_hours']:
                    carry_note = ""
                    if ticket['carryover_hours'] > 0:
                        carry_note += f"{ticket['carryover_hours']} hours carried over. "
                    if ticket['inclusive_hours']:
                        carry_note += f"{ticket['inclusive_hours']} hours included in contract."
                    if carry_note:
                        # We'll add this note later when building the description
                        ticket['contract_note'] = carry_note

        tickets_details_df = pd.DataFrame(tickets_details)
        tickets_details_df = tickets_details_df[tickets_details_df['company_code'] != "—"]
        tickets_details_df = tickets_details_df[tickets_details_df['hourly_rate'].notnull()]

        # Map and transform for Xero CSV
        tickets_details_df['Description'] = tickets_details_df.apply(
            lambda row: (
                f"{row['ticket_id']} – {row['title']} [{row['product']}]" +
                (" [Change Request]" if row['change_request'] else "") +
                (f"\nNote: {row['contract_note']}" if 'contract_note' in row else "")
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
    
    # Setup Google Sheets client
    google_client = setup_google_sheets(st.secrets["gcp_service_account"])

    # Create a dict to store contract data by company code to avoid multiple lookups
    contract_data_cache = {}

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

        # Get support contract data from spreadsheet
        if company_code not in contract_data_cache and company_code != "—":
            # Use the first day of the month from the time entry for contract data lookup
            time_spent_at = entry.get('executed_at')
            if time_spent_at:
                # Parse the date from the time entry
                try:
                    date_obj = datetime.strptime(time_spent_at.split('T')[0], '%Y-%m-%d')
                    # Get first day of the month
                    first_day = datetime(date_obj.year, date_obj.month, 1)
                    contract_data_cache[company_code] = get_support_contract_data(google_client, company_code, first_day)
                except Exception:
                    contract_data_cache[company_code] = {"error": "Failed to parse date"}
            else:
                # Use current month if no date in time entry
                contract_data_cache[company_code] = get_support_contract_data(google_client, company_code)

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
            # Add contract data if available
            'carryover_hours': contract_data_cache.get(company_code, {}).get('carryover_hours', 0) 
                if company_code != "—" and "error" not in contract_data_cache.get(company_code, {}) else 0,
            'inclusive_hours': contract_data_cache.get(company_code, {}).get('inclusive_hours') 
                if company_code != "—" and "error" not in contract_data_cache.get(company_code, {}) 
                else company.get('custom_fields', {}).get('inclusive_hours')
        })
    
    # Display a note about spreadsheet data source if we're in admin mode
    if st.session_state.client_code == "admin" and contract_data_cache:
        success_count = sum(1 for data in contract_data_cache.values() if "error" not in data)
        if success_count > 0:
            spreadsheet_id = "1OXy-yuN_Qne2Pc7uc18V2eKXiDkWIEp88y68lHG1FDU"
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            st.info(f"Got support contract data from the [spreadsheet]({spreadsheet_url}) for {success_count} companies.")
        
    return details