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
    st.warning('Recently updated. Use with caution and let Andrew SF know if something needs adjusting.')
    
    st.info('''
        This tool generates a CSV for importing into Xero. Features:
        * Groups all time entries by ticket, showing one line per ticket
        * Automatically includes contract information as a descriptive line item
        * Adds a negative quantity line item for rollover hours (credit)
        * Shows both applied rollover hours and total available rollover hours
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

        # Add invoice numbers
        for ticket in tickets_details:
            if ticket['company_code']:
                ticket['InvoiceNumber'] = f"S-{ticket['company_code']}{selected_date.strftime('%y%-m')}"

        # Create the initial DataFrame for tickets
        tickets_details_df = pd.DataFrame(tickets_details)
        tickets_details_df = tickets_details_df[tickets_details_df['company_code'] != "—"]
        tickets_details_df = tickets_details_df[tickets_details_df['hourly_rate'].notnull()]
        
        # Group by company to create additional line items for each company
        company_groups = tickets_details_df.groupby(['company', 'company_code', 'InvoiceNumber', 'hourly_rate', 'currency'])
        
        # Create a list to store all rows including the new line items
        all_rows = []
        
        # Process each company group
        for (company, company_code, invoice_number, hourly_rate, currency), group in company_groups:
            # Add all original ticket rows to our list
            all_rows.extend(group.to_dict('records'))
            
            # Get total billable hours for this company
            total_billable_hours = group['billable_time_this_month'].sum()
            
            # Get contract data from the first row (should be the same for all rows in this company)
            first_row = group.iloc[0]
            carryover_hours = first_row.get('carryover_hours', 0)
            inclusive_hours = first_row.get('inclusive_hours', 0)
            
            # Only add extra line items if we have contract or carryover hours
            if carryover_hours > 0 or inclusive_hours > 0:
                # Create contract details line item
                contract_line = {
                    'company': company,
                    'company_code': company_code,
                    'InvoiceNumber': invoice_number,
                    'hourly_rate': hourly_rate,
                    'currency': currency,
                    'billable_time_this_month': 0,  # No quantity for this informational line
                    'ticket_id': "",  # No ticket associated
                    'title': "Support contract details",
                    'product': "Support",
                    'change_request': False,
                    'Description': f"Support contract: {inclusive_hours} hours included monthly"
                }
                all_rows.append(contract_line)
                
                # If we have carryover hours, add a line item with negative quantity
                if carryover_hours > 0:
                    # Only apply carryover up to the billable amount
                    applied_carryover = min(carryover_hours, total_billable_hours)
                    if applied_carryover > 0:
                        carryover_line = {
                            'company': company,
                            'company_code': company_code,
                            'InvoiceNumber': invoice_number,
                            'hourly_rate': hourly_rate,
                            'currency': currency,
                            'billable_time_this_month': -applied_carryover,  # Negative quantity for credit
                            'ticket_id': "",  # No ticket associated
                            'title': "Rollover credit",
                            'product': "Support",
                            'change_request': False,
                            'Description': f"Credit for {applied_carryover:.1f} rollover hours (total available: {carryover_hours:.1f}h)"
                        }
                        all_rows.append(carryover_line)
        
        # Create new DataFrame with all rows
        tickets_details_df = pd.DataFrame(all_rows)

        # Map and transform for Xero CSV
        tickets_details_df['Description'] = tickets_details_df.apply(
            lambda row: (
                # For ticket rows, show ticket ID and details
                (f"{row['ticket_id']} – {row['title']} [{row['product']}]" + 
                 (" [Change Request]" if row['change_request'] else "")) 
                if row['ticket_id'] else 
                # For non-ticket rows (contract info and rollover), use the description directly
                row.get('Description', '')
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
    # Create a dictionary to aggregate time entries by ticket
    ticket_aggregates = {}
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

        # Create a key for the ticket
        ticket_key = str(ticket_id)
        
        # If we haven't seen this ticket before, create a new entry
        if ticket_key not in ticket_aggregates:
            ticket_aggregates[ticket_key] = {
                'time_spent_this_month': 0,
                'billable_time_this_month': 0,
                'ticket_id': ticket_id,
                'title': ticket_data.get('subject', 'No subject'),
                'company': ticket_data.get('company_name', 'Unknown'),
                'company_code': company_code,
                'hourly_rate': hourly_rate,
                'currency': currency,
                'product': product_name,
                'change_request': ticket_data.get('custom_fields', {}).get('change_request', False),
                # Add contract data if available
                'carryover_hours': contract_data_cache.get(company_code, {}).get('carryover_hours', 0) 
                    if company_code != "—" and "error" not in contract_data_cache.get(company_code, {}) else 0,
                'inclusive_hours': contract_data_cache.get(company_code, {}).get('inclusive_hours') 
                    if company_code != "—" and "error" not in contract_data_cache.get(company_code, {}) 
                    else company.get('custom_fields', {}).get('inclusive_hours')
            }
        
        # Add the hours to the ticket's total
        ticket_aggregates[ticket_key]['time_spent_this_month'] += time_hours
        ticket_aggregates[ticket_key]['billable_time_this_month'] += billable_hours
    
    # Convert the aggregated dictionary to a list
    details = list(ticket_aggregates.values())
    
    # Display a note about spreadsheet data source if we're in admin mode
    if st.session_state.client_code == "admin" and contract_data_cache:
        success_count = sum(1 for data in contract_data_cache.values() if "error" not in data)
        if success_count > 0:
            spreadsheet_id = "1OXy-yuN_Qne2Pc7uc18V2eKXiDkWIEp88y68lHG1FDU"
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            st.info(f"Got support contract data from the [spreadsheet]({spreadsheet_url}) for {success_count} companies.")
        
    return details