# xero.py

import pandas as pd
import streamlit as st
import base64
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from api import get_companies_options, get_companies_data, get_time_entries_data, get_tickets_data
from utils import prepare_tickets_details_from_time_entries, get_product_options, get_products_data


def display_month_selector():
    now = datetime.now()
    months = [(now - relativedelta(months=i)).strftime("%B %Y") for i in range(5)]
    selected_month = st.selectbox("Choose a month", months)
    selected_date = datetime.strptime(selected_month, "%B %Y")
    formatted_selected_date = selected_date.strftime("%Y-%m")
    return selected_month

def display_territory_selector():
    territories = ['Made Media Inc.', 'Made Media Ltd.']
    selected_territory = st.multiselect("Filter by territory", territories, default=territories)
    return selected_territory
    

def display_xero_exporter():
    st.info('''
            This can generate a CSV file that you can import into Xero. Known issues: 
            * The system does not yet know about rollover hours
            * The system does not yet add a line item for the hours included in the monthly retainer
            
            For the moment, please deal with these things manually.
            ''')
    
    selected_month = display_month_selector()
    selected_territory = display_territory_selector()

    # Define start and end dates for the selected month
    selected_date = datetime.strptime(selected_month, "%B %Y")
    start_date = selected_date.strftime("%Y-%m-%d")  # Start of the month
    end_date = (selected_date + relativedelta(months=1) - timedelta(days=1)).strftime("%Y-%m-%d")  # End of the month

    if st.button("Generate CSV for Xero"):
        time_entries_data = get_time_entries_data(start_date, end_date)

        products_data = get_products_data()
        product_options = get_product_options(products_data)

        tickets_details = prepare_tickets_details_from_time_entries(time_entries_data, product_options)

        for ticket_detail in tickets_details:
            if ticket_detail['company_code']:
                ticket_detail['InvoiceNumber'] = "S-" + ticket_detail['company_code'] + selected_date.strftime("%y%-m")

        tickets_details_df = pd.DataFrame(tickets_details)

        # remove tickets where company code is "—"
        tickets_details_df = tickets_details_df[tickets_details_df['company_code'] != "—"]

        # remove tickets where hourly_rate is null
        tickets_details_df = tickets_details_df[tickets_details_df['hourly_rate'].notnull()]

        # filter by territory
        tickets_details_df = tickets_details_df[tickets_details_df['territory'].isin(selected_territory)]

        # prepare data for Xero
        data_for_xero = tickets_details_df[[
            'ticket_id',
            'company',
            'company_code',
            'currency',
            'hourly_rate',
            'InvoiceNumber',
            'title',
            'change_request',
            'product',
            'billable_time_this_month'
        ]]
        data_for_xero['ticket_id'] = data_for_xero['ticket_id'].astype(str)
        data_for_xero['Description'] = data_for_xero['ticket_id'] + ' – ' + data_for_xero['title']
        data_for_xero['Description'] = data_for_xero['Description'] + ' [' + data_for_xero['product'] + ']'

        def add_tags(row):
            if row['change_request']:
                return row['Description'] + ' [Change Request]'
            else:
                return row['Description']
        
        data_for_xero['Description'] = data_for_xero.apply(add_tags, axis=1)

        #rename columns
        data_for_xero = data_for_xero.rename(columns={
            'company': 'ContactName',
            'company_code': 'ContactCode',
            'hourly_rate': 'UnitAmount',
            'billable_time_this_month': 'Quantity',
            'currency': 'Currency'
        })
        # invoice is dated this month...
        data_for_xero['InvoiceDate'] = (selected_date + relativedelta(months=1) - timedelta(days=1)).strftime("%Y-%m-%d")
        # ...and due next month
        data_for_xero['DueDate'] = (selected_date + relativedelta(months=2) - timedelta(days=1)).strftime("%Y-%m-%d")
        data_for_xero = data_for_xero.sort_values(by=['InvoiceNumber', 'ticket_id'])
        data_for_xero = data_for_xero.drop(columns=['ticket_id', 'title', 'change_request', 'product'])
        # reindex
        data_for_xero = data_for_xero.reset_index(drop=True)
        
        # add an expander
        with st.expander("Peek at what's in the CSV"):
            st.write("Here's a preview of the data that will be exported to Xero:")
            st.write(data_for_xero)

        # prep for CSV
        data_for_xero.insert(2, 'EmailAddress', None)
        data_for_xero.insert(3, 'POAddressLine1', None)
        data_for_xero.insert(3, 'POAddressLine2', None)
        data_for_xero.insert(3, 'POAddressLine3', None)
        data_for_xero.insert(3, 'POAddressLine4', None)
        data_for_xero.insert(3, 'POCity', None)
        data_for_xero.insert(3, 'PORegion', None)
        data_for_xero.insert(3, 'POPostalCode', None)
        data_for_xero.insert(3, 'POCountry', None)
        data_for_xero.insert(3, 'Total', None)
        data_for_xero.insert(3, 'InventoryItemCode', None)
        data_for_xero.insert(3, 'Discount', None)
        data_for_xero.insert(3, 'AccountCode', '4010')
        data_for_xero.insert(3, 'TaxType', 'Tax Exempt (0%)')
        data_for_xero.insert(3, 'TaxAmount', None)
        data_for_xero.insert(3, 'TrackingName1', None)
        data_for_xero.insert(3, 'TrackingOption1', None)
        data_for_xero.insert(3, 'TrackingName2', None)
        data_for_xero.insert(3, 'TrackingOption2', None)
        columns_for_xero = ['ContactName', 'EmailAddress', 'POAddressLine1', 'POAddressLine2', 'POAddressLine3', 'POAddressLine4', 'POCity', 'PORegion', 'POPostalCode', 'POCountry', 'InvoiceNumber', 'InvoiceDate', 'DueDate', 'Total', 'InventoryItemCode', 'Description', 'Quantity', 'UnitAmount', 'Discount', 'AccountCode', 'TaxType', 'TaxAmount', 'TrackingName1', 'TrackingOption1', 'TrackingName2', 'TrackingOption2', 'Currency']
        data_for_xero = data_for_xero[columns_for_xero]

        # Generate CSV
        csv = data_for_xero.to_csv(index=False)

        # Create a download link
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="upload_me_to_xero_for_a_good_time.csv">Your CSV is ready! Click here to download it.</a>'
        st.markdown(href, unsafe_allow_html=True)

        # companies_data = get_companies_data()
        # companies_data_df = pd.DataFrame(companies_data)
        # st.write(companies_data_df)
    
    if st.button("Clear caches"):
        st.cache_data.clear()

