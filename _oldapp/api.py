# api.py
"""This file handles all the interaction with the FreshDesk API."""

import streamlit as st
import requests
from config import base_url
import urllib.parse
import datetime

api_key = st.secrets["api_key"]


@st.cache_resource(ttl=60*60, show_spinner=False)
def get_ticket_data(ticket_id):
    ticket_url = f'{base_url}/tickets/{ticket_id}'
    ticket_data, _ = get_data_from_api(ticket_url, api_key)
    return ticket_data


@st.cache_resource(ttl=60*60, show_spinner=False)
def get_tickets_data(updated_since=None, per_page=100, order_by='updated_at', order_type='desc', include='stats,requester,description'):
    if updated_since is None:
        # Get tickets from the last 90 days
        date = datetime.datetime.now() - datetime.timedelta(days=90)
        date = date.replace(year=date.year, month=1, day=1, hour=16, minute=20)
        date_utc = date.astimezone(datetime.timezone.utc)
        updated_since = date_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    tickets_url = f'{base_url}/tickets/?per_page={per_page}&order_by={order_by}&order_type={order_type}&include={include}&updated_since={updated_since}'
    tickets_data = []
    for page_data in get_paginated(tickets_url, api_key):
        tickets_data.extend(page_data)
    return tickets_data



@st.cache_resource(ttl=60*60, show_spinner=False)
def search_tickets(query):
    """
    More information: https://developers.freshdesk.com/api/#filter_tickets
    """
    encoded_query = urllib.parse.quote(query) 
    search_url = f'{base_url}/search/tickets?query="{encoded_query}"'
    tickets_data = []
    for page_data in get_paginated(search_url, api_key):
        tickets_data.extend(page_data)
    return tickets_data


@st.cache_resource(ttl=60*60*24*7, show_spinner=False)
def get_agent_data(agent_id):
    agent_url = f'{base_url}/agents/{agent_id}'
    agent_data, _ = get_data_from_api(agent_url, api_key)
    return agent_data


@st.cache_resource(ttl=60*60*24*7, show_spinner=False)
def get_group_data(group_id):
    group_url = f'{base_url}/groups/{group_id}'
    group_data, _ = get_data_from_api(group_url, api_key)
    return group_data


@st.cache_resource(ttl=60*60*24*7, show_spinner=False)
def get_products_data():
    products_url = f'{base_url}/products'
    products_data = [page_data for sublist in get_paginated(
        products_url, api_key) for page_data in sublist]
    return products_data


def get_product_options(products_data):
    product_options = {product['id']: product['name']
                       for product in products_data}
    return product_options


@st.cache_resource(ttl=60*60*24*7, show_spinner=False)
def get_requester_data(requester_id):
    requester_url = f'{base_url}/contacts/{requester_id}'
    requester_data, _ = get_data_from_api(requester_url, api_key)
    return requester_data


def get_data_from_api(url, api_key):
    response = requests.get(url, auth=(api_key, 'X'))
    if response.ok:
        data = response.json()
        link_header = response.headers.get('link')
        return data, link_header
    else:
        return None, None


def get_paginated(url, api_key):
    data, link_header = get_data_from_api(url, api_key)
    if data is not None:
        yield data
        if link_header:
            next_url = link_header.split(';')[0].strip('<').strip('>')
            yield from get_paginated(next_url, api_key)


@st.cache_resource(ttl=60*60*24*7, show_spinner=False)
def get_companies_data():
    companies_url = f'{base_url}/companies'
    companies_data = []
    for page_data in get_paginated(companies_url, api_key):
        companies_data.extend(page_data)
    return companies_data


def get_companies_options(companies_data):
    companies_options = {}
    for company_data in companies_data:
        companies_options[company_data['name']] = company_data['id']
    return companies_options


@st.cache_resource(ttl=60*60*24*7, show_spinner=False)
def get_time_entries_data(start_date, end_date, selected_value=None):
    time_entries_url = f'{base_url}/time_entries?executed_before={end_date}&executed_after={start_date}'
    if selected_value is not None:
        time_entries_url += f'&company_id={selected_value}'
    time_entries_data = [page_data for sublist in get_paginated(
        time_entries_url, api_key) for page_data in sublist]
    return time_entries_data
