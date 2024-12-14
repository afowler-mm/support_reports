import requests
import datetime
import streamlit as st
from typing import List, Dict, Optional
from urllib.parse import quote

BASE_URL = st.secrets["base_url"]
API_KEY = st.secrets["api_key"]

class FreshdeskAPI:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def _get(self, url: str) -> requests.Response:
        """Base GET request with authentication."""
        response = requests.get(url, auth=(self.api_key, 'X'))
        response.raise_for_status()
        return response

    def _get_paginated(self, url: str):
        """Handle pagination to yield all results."""
        while url:
            resp = self._get(url)
            data = resp.json()
            yield data
            link_header = resp.headers.get('link')
            if link_header and 'rel="next"' in link_header:
                # Extract next URL from link header
                # link header format: <https://..>; rel="next"
                next_url_part = link_header.split(';')[0].strip('<>')
                url = next_url_part
            else:
                url = None

    @st.cache_resource(ttl=3600)
    def get_companies(_self) -> List[Dict]:
        url = f"{_self.base_url}/companies"
        results = []
        for page_data in _self._get_paginated(url):
            results.extend(page_data)
        return results

    @st.cache_resource(ttl=3600)
    def get_company_by_id(_self, company_id: int) -> Optional[Dict]:
        url = f"{_self.base_url}/companies/{company_id}"
        resp = _self._get(url)
        return resp.json()

    def get_companies_options(self) -> Dict[str, int]:
        companies_data = self.get_companies()
        return {c['name']: c['id'] for c in companies_data}

    @st.cache_resource(ttl=3600)
    def get_products(_self) -> List[Dict]:
        url = f"{_self.base_url}/products"
        results = []
        for page_data in _self._get_paginated(url):
            results.extend(page_data)
        return results

    def get_product_options(self) -> Dict[int, str]:
        products = self.get_products()
        return {p['id']: p['name'] for p in products}

    @st.cache_resource(ttl=3600)
    def get_time_entries(_self, start_date: str, end_date: str, company_id: Optional[int]=None) -> List[Dict]:
        # start_date and end_date are expected as YYYY-MM-DD strings
        url = f"{_self.base_url}/time_entries?executed_before={end_date}&executed_after={start_date}"
        if company_id is not None:
            url += f"&company_id={company_id}"

        results = []
        for page_data in _self._get_paginated(url):
            results.extend(page_data)
        return results

    @st.cache_resource(ttl=3600)
    def get_tickets(_self, updated_since: Optional[str]=None, per_page=100, order_by='updated_at', order_type='desc', include='stats,requester,description') -> List[Dict]:
        """Get tickets updated since a certain date."""
        if updated_since is None:
            # Default: last 90 days
            date = datetime.datetime.now() - datetime.timedelta(days=90)
            date_utc = date.astimezone(datetime.timezone.utc)
            updated_since = date_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        url = f"{_self.base_url}/tickets/?per_page={per_page}&order_by={order_by}&order_type={order_type}&include={include}&updated_since={updated_since}"

        results = []
        for page_data in _self._get_paginated(url):
            results.extend(page_data)
        return results

    @st.cache_resource(ttl=3600)
    def get_ticket_data(_self, ticket_id: int) -> Dict:
        url = f"{_self.base_url}/tickets/{ticket_id}"
        resp = _self._get(url)
        return resp.json()

    @st.cache_resource(ttl=3600*24*7)
    def get_agent(_self, agent_id: int) -> Dict:
        url = f"{_self.base_url}/agents/{agent_id}"
        resp = _self._get(url)
        return resp.json()

    @st.cache_resource(ttl=3600*24*7)
    def get_group(_self, group_id: int) -> Dict:
        url = f"{_self.base_url}/groups/{group_id}"
        resp = _self._get(url)
        return resp.json()

    @st.cache_resource(ttl=3600*24*7)
    def get_requester(_self, requester_id: int) -> Dict:
        url = f"{_self.base_url}/contacts/{requester_id}"
        resp = _self._get(url)
        return resp.json()

# Create a global instance if desired
freshdesk_api = FreshdeskAPI(BASE_URL, API_KEY)