import pandas as pd
import streamlit as st
import datetime
import streamlit_authenticator as stauth


from config import base_url, status_mapping
from api import get_ticket_data, get_tickets_data, get_agent_data, get_requester_data, get_group_data, get_paginated, get_products_data, get_product_options, get_companies_data, get_companies_options, get_time_entries_data
from utils import date_range_selector, get_currency_symbol, setup_google_sheets, open_google_sheet, get_client_data, get_contract_renews_date, display_columns, get_product_options, prepare_tickets_details, prepare_tickets_details_from_time_entries, calculate_billable_time
from xero import display_xero_exporter

api_key = st.secrets["api_key"]

def display_client_selector(companies_options, client_code=None):
    col1, col2 = st.columns(2)
    with col1:
        if client_code is not None and client_code != "Made":
            selected_client = client_code
            st.markdown(f"<small>Client</small>\n\n {selected_client}", unsafe_allow_html=True)
        else:
            selected_client = st.selectbox('Client', companies_options)
        selected_value = companies_options.get(selected_client)
    with col2:
        start_date, end_date = date_range_selector('Month', datetime.datetime.now(
        ) - datetime.timedelta(days=1095), datetime.datetime.now())
    return selected_client, selected_value, start_date, end_date


def display_company_summary(company_data, start_date):
    company_name = company_data['name']
    company_cfs = company_data['custom_fields']

    client_code = company_cfs['company_code']
    global client_info
    client_info = get_client_data(worksheet, client_code)

    contract_renews = client_info.get('contract_renews')

    try:
        if contract_renews is not None:
            client_renewal_date = datetime.datetime.strptime(
                contract_renews, "%B %Y")
            client_renewal_date_formatted = client_renewal_date.strftime("%B %Y")
        else:
            client_renewal_date_formatted = None
    except:
        client_renewal_date_formatted = None

    company_data_to_display = {
        'Client Code': company_cfs['company_code'],
        'Support Contract': f"{company_cfs['support_contract']}, paid annually" if company_cfs['paid_annually'] else company_cfs['support_contract'],
        # 'Contract Renewal Date': client_renewal_date_formatted,
        'Included Hours Per Month': company_cfs['inclusive_hours'],
        'Overage Rate': f"{company_cfs['currency']} {company_cfs['contract_hourly_rate']}/hour"
    }

    with st.expander("Company details for debugging"):
        col1, col2 = st.columns(2)
        with col1:
            f"##### Data from [FreshDesk](https://mademedia.freshdesk.com/a/companies/{selected_value}):"
            st.write(company_data_to_display)

        with col2:
            "##### Data from [Google Sheets](https://docs.google.com/spreadsheets/d/1Mv-7n-1ST9eFB3_q_rHQPt8NfcnsuqNYEM8ei5PXbgw/edit#gid=0):"
            st.write(client_info)


def display_time_summary(tickets_details_df, company_data, start_date):
    year, month, _ = start_date.split("-")
    key = f"{year}_{month}_carryover"
    carryover_value = client_info.get(key)

    total_time = f"{tickets_details_df['time_spent_this_month'].sum():.1f} h"
    billable_time = f"{tickets_details_df['billable_time_this_month'].sum():.1f} h"

    rollover_time = "{:.1f} h".format(float(carryover_value)) if carryover_value is not None and str(
        carryover_value).replace(".", "", 1).isdigit() else None
    net_time = "{:.1f} h".format(tickets_details_df['billable_time_this_month'].sum(
    ) - (float(carryover_value) if carryover_value is not None and str(carryover_value).replace('.', '', 1).isdigit() else 0)) if carryover_value is not None else None

    now = datetime.datetime.now()
    start_date_year, start_date_month = map(int, start_date.split("-")[:2])
    is_current_or_adjacent_month = (
        now.year == start_date_year and abs(now.month - start_date_month) <= 1)
    currency_symbol = get_currency_symbol(
        company_data['custom_fields']['currency'])
    total_billable_hours = tickets_details_df['billable_time_this_month'].sum(
    ) - float(company_data['custom_fields'].get('inclusive_hours') or 0)

    estimated_cost = f"{currency_symbol}{max(total_billable_hours - (float(carryover_value) if carryover_value is not None and str(carryover_value).replace('.', '', 1).isdigit() else 0), 0) * (company_data['custom_fields']['contract_hourly_rate']) if is_current_or_adjacent_month and company_data['custom_fields']['contract_hourly_rate'] is not None else 0.00:,.2f}"

    inclusive_hours = company_data['custom_fields'].get('inclusive_hours')

    time_summary_contents = {
        "Total time tracked": total_time,
        "Of which potentially billable": billable_time,
    }
    
    if inclusive_hours is not None and is_current_or_adjacent_month:
        time_summary_contents["Support contract includes"] = "{:.0f} h".format(inclusive_hours)

    if rollover_time is not None:
        time_summary_contents["Rollover time available"] = rollover_time

    if company_data['custom_fields']['contract_hourly_rate'] is not None and is_current_or_adjacent_month:
        time_summary_contents["Hourly rate for overages"] = f"{currency_symbol}{company_data['custom_fields']['contract_hourly_rate']:,.0f}"

    if is_current_or_adjacent_month and company_data['custom_fields']['contract_hourly_rate'] is not None:
        time_summary_contents["Estimated cost this month"] = estimated_cost

    # time_summary_table = "<table>"
    # for each in time_summary_contents:
    #     time_summary_table += f"<tr><td>{each}</td><td align='right'>{time_summary_contents[each]}</td></tr>"
    # time_summary_table += "</table><br>"
    # st.markdown(time_summary_table, unsafe_allow_html=True)

    display_columns(time_summary_contents)

    # warn if any tickets with time tracked are marked "Invoice"
    if not tickets_details_df[tickets_details_df["billing_status"] == "Invoice"].empty:
        invoice_tickets = tickets_details_df[tickets_details_df["billing_status"] == "Invoice"]
        num_invoice_tickets = len(invoice_tickets)
        invoice_ticket_ids = invoice_tickets["ticket_id"].tolist()
        invoice_tickets_str = ", ".join(
            [f"[#{ticket_id}](https://mademedia.freshdesk.com/support/tickets/{ticket_id})" for ticket_id in invoice_ticket_ids])

        total_invoice_time = invoice_tickets["time_spent_this_month"].sum()
        total_invoice_time_str = "{:.1f}".format(total_invoice_time)
        st.warning(f"Ticket{'s' if num_invoice_tickets > 1 else ''} {invoice_tickets_str} {'are' if num_invoice_tickets > 1 else 'is'} marked with billing status ‘Invoice’ and {'have a total of' if num_invoice_tickets > 1 else 'has'} {total_invoice_time_str} hours tracked this month. This time is not included in the above total of billable hours.")


def display_monthly_dashboard(client_code=None):
    client = setup_google_sheets()
    sheet = open_google_sheet(client, st.secrets["private_gsheets_url"])
    global worksheet
    worksheet = sheet.get_worksheet(0)

    companies_data = get_companies_data()
    companies_options = get_companies_options(companies_data)
    products_data = get_products_data()
    product_options = get_product_options(products_data)

    global selected_value
    selected_client, selected_value, start_date, end_date = display_client_selector(
        companies_options, client_code)
    selected_company = next(
        (company for company in companies_data if company["id"] == selected_value), None)
    time_entries_df = pd.DataFrame()
    time_entries_data = []
    company_data = []

    if selected_company is not None:
        company_data = {key: selected_company[key]
                        for key in selected_company.keys()}
        display_company_summary(company_data, start_date)

        time_entries_data = get_time_entries_data(
            start_date, end_date, selected_value)
        time_entries_df = pd.DataFrame(time_entries_data)
    else:
        print("No company found with the selected value.")

    if not time_entries_df.empty:
        time_entries_df = time_entries_df.astype({
            'id': 'str',
            'agent_id': 'str',
            'ticket_id': 'str',
            'company_id': 'str',
            'time_spent_in_seconds': 'str'
        })

        progress_text = "Getting time entries for this month…"
        progress_bar = st.progress(0, text=progress_text)
        tickets_details = prepare_tickets_details_from_time_entries(time_entries_data, product_options, progress=progress_bar, progress_text=progress_text)
        progress_bar.progress(1.0, text="Your ticket details are ready!").empty()

        tickets_details_df = pd.DataFrame(tickets_details)

        if not tickets_details_df.empty:

            display_time_summary(tickets_details_df, company_data, start_date)

            formatted_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %Y')
            st.markdown(f"#### Made Media support tickets with time tracked during {formatted_date} for {company_data['name']}")

            tickets_html = f"<table>"
            tickets_html += f"<tr><th>Ticket</th><th align='right'>Time tracked this month</th><th align='right'>Potentially billable time this month</th></tr>"
            for ticket in tickets_details:
                tickets_html += f"<tr>"
                tickets_html += f"<td><h6 style='padding-bottom:0;margin-bottom:0'><a href='https://mademedia.freshdesk.com/support/tickets/{ticket['ticket_id']}'>{ticket['ticket_id']}</a>: {ticket['title']}</h6><small>Filed by: {ticket['requester_name']}</small></td>"
                tickets_html += f"<td align='right'>{ticket['time_spent_this_month']:.1f} hours</td>"
                tickets_html += f"<td align='right'>{ticket['billable_time_this_month']:.1f} hours</td>"
                tickets_html += f"</tr>"
            tickets_html += f"</table>"
            # tickets_details_df
            st.markdown(tickets_html, unsafe_allow_html=True)

        else:
            st.write("Uh-oh, I couldn't find any tickets that match the time entries tracked this month. This probably means something is wrong with me 🤖")

    else:
        st.write("No time tracked for this month")


def display_ticket_search(client_code=None):
    tickets_data = get_tickets_data()
    tickets_details = prepare_tickets_details(tickets_data, client_code)
    tickets_details_df = pd.DataFrame(tickets_details)
    st.info("This view is a work in progress. It currently displays tickets that have been updated in the last 90 days.")
    st.dataframe(
        tickets_details_df,
        column_config = {
            "Ticket ID": st.column_config.NumberColumn(
                "Ticket ID",
                format="%d"
            ),
            "Created": st.column_config.DatetimeColumn(
                "Created",
                format="DD MMM YY HH:mm"
            ),
            "Updated": st.column_config.DatetimeColumn(
                "Updated",
                format="DD MMM YY HH:mm"
            ),
        },
        hide_index=True
)


def main():
    st.set_page_config(layout="wide", page_icon=":bar_chart:")

    import yaml
    from yaml.loader import SafeLoader
    with open("auth.yaml") as f:
        auth = yaml.load(f, Loader=SafeLoader)
        authenticator = stauth.Authenticate(
            auth['credentials'],
            auth['cookie']['name'],
            auth['cookie']['key'],
            auth['cookie']['expiry_days'],
            auth['preauthorized']
        )

    with open('auth.yaml', 'r') as f:
        auth_data = yaml.safe_load(f)
        username = st.session_state.get('username', None)
        name, authentication_status, username = authenticator.login('Login', 'main')
        if username:
            user = auth_data['credentials']['usernames'][username]
            client_code = user['client_code']

    if st.session_state.get("authentication_status", False):
        if client_code == "admin":
            tab1, tab2, tab3 = st.tabs(["Tickets by tracked time", "Tickets by status", "Export for Xero"])
            with tab1:
                display_monthly_dashboard(name)
            with tab3:
                display_xero_exporter()
            with tab2:
                display_ticket_search(client_code)
            
        else:
            tab1, tab2 = st.tabs(["Tickets by tracked time", "Tickets by status"])
            with tab1:
                display_monthly_dashboard(name)
            with tab2:
                display_ticket_search(client_code)
        st.write('---')
        f"You’re logged in as {name} ({username})"
        authenticator.logout('Logout', 'main')

    elif st.session_state.get("authentication_status", False) == False:
        st.error('Username/password is incorrect')
    elif st.session_state.get("authentication_status", None) == None:
        st.warning('Please enter your username and password').empty()
    else:
        st.error("I don't know who you are 🤷‍♂️")

if __name__ == "__main__":
    main()
