import gspread
from google.oauth2.service_account import Credentials

def setup_google_sheets(secrets):
    """Setup Google Sheets API client."""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    creds = Credentials.from_service_account_info(secrets, scopes=scopes)
    return gspread.authorize(creds)

def fetch_auth_data(client, sheet_id, sheet_name):
    """Fetch authentication data from Google Sheets."""
    sheet = client.open_by_key(sheet_id).worksheet(sheet_name)
    data = sheet.get_all_records()
    return data