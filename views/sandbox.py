import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from apis.google import setup_google_sheets
from utils import get_fiscal_year, get_support_contract_data

def display_sandbox_view(client_code: str):
    """Sandbox view for exploring Google Spreadsheet data."""
    
    st.title("Support Contract Spreadsheet Explorer")
    
    # Only allow admin access to this view
    if client_code != "admin":
        st.error("This view is only available to admin users.")
        return
        
    # Load the Google Sheets client using credentials from Streamlit secrets
    google_client = setup_google_sheets(st.secrets["gcp_service_account"])
    
    # The spreadsheet ID from the URL
    spreadsheet_id = "1OXy-yuN_Qne2Pc7uc18V2eKXiDkWIEp88y68lHG1FDU"
    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    
    try:
        # Open the spreadsheet by ID
        spreadsheet = google_client.open_by_key(spreadsheet_id)
        
        # Get current fiscal year
        current_fiscal_year = get_fiscal_year()
        
        # Find the worksheet for the current fiscal year
        worksheet = None
        for ws in spreadsheet.worksheets():
            if ws.title == current_fiscal_year:
                worksheet = ws
                break
        
        if not worksheet:
            st.error(f"Could not find worksheet for fiscal year {current_fiscal_year}.")
            return
        
        # Display information about the selected worksheet
        st.info(f"Using data from the '{current_fiscal_year}' tab of the [support contract spreadsheet]({spreadsheet_url}).")
        
        # Get all values from the worksheet (handles merged cells better)
        all_values = worksheet.get_all_values()
        
        if not all_values:
            st.warning("Worksheet is empty.")
            return
        
        # Display the raw data structure to help debug
        with st.expander("Show raw worksheet data"):
            st.write("First 10 rows of raw data:")
            for i, row in enumerate(all_values[:10]):
                st.write(f"Row {i}: {row}")
        
        # Find client names (typically in first column)
        # Skip header rows (assume they're in the first few rows)
        client_rows = []
        start_row = 0
        
        # Find where client data starts (looking for non-empty first cells after header rows)
        for i, row in enumerate(all_values):
            if i > 2 and row and row[0] and row[0].strip():  # Skip first few rows and find first non-empty cell
                if not row[0].startswith(('Client', 'Month', 'Date', 'Total', 'Average')):  # Skip header/summary rows
                    client_rows.append((i, row))
                    if start_row == 0:
                        start_row = i
        
        # Display client names found
        st.subheader("Clients Found in Spreadsheet")
        if client_rows:
            clients_df = pd.DataFrame([row[1][0] for row in client_rows], columns=["Client name"])
            st.dataframe(clients_df)
            
            # Try to extract month headers (assuming they're in row 2 or 3)
            month_row = []
            for i in range(1, 4):  # Check rows 1-3
                if i < len(all_values) and any("October" in str(cell) or "November" in str(cell) for cell in all_values[i]):
                    month_row = all_values[i]
                    break
            
            # Display month headers if found
            if month_row:
                st.subheader("Months in Spreadsheet")
                months = [cell for cell in month_row if cell.strip()]
                st.write(", ".join(months))
                
                # Create a structured DataFrame for better visualization
                # Find where month columns start (usually after client name column)
                data_dict = {}
                for i, (row_idx, row_data) in enumerate(client_rows):
                    client_name = row_data[0]
                    values = row_data[1:len(months)+1]  # Get values that align with months
                    data_dict[client_name] = values
                
                # Convert to DataFrame
                if data_dict:
                    df = pd.DataFrame.from_dict(data_dict, orient='index', columns=months)
                    
                    # Clean the data (replace empty strings with NaN)
                    df = df.replace('', np.nan)
                    
                    st.subheader("Client Data by Month")
                    st.dataframe(df)
                
            # Look for column headers describing what the values represent
            column_headers_row = None
            for i in range(1, 6):  # Check first few rows
                if i < len(all_values) and any("Billable" in str(cell) or "Hours" in str(cell) for cell in all_values[i]):
                    column_headers_row = all_values[i]
                    break
            
            if column_headers_row:
                st.subheader("Column Headers")
                headers = [h for h in column_headers_row if h.strip()]
                for h in headers:
                    st.write(f"- {h}")
                    
            # Analyze data structure
            st.subheader("Data Structure Analysis")
            st.write("""
            This spreadsheet appears to have:
            1. Client names in the first column
            2. Monthly data across columns
            3. Possibly merged cells for headers
            """)
            
            # Test the support contract data function
            st.subheader("Test Support Contract Data Function")
            
            # List client codes for testing (update with clients from your spreadsheet)
            client_codes = [
                "MTC", "NYT", "SFM", "TBC", "SVA", "ASH", "IMM", "LAP", "RAH", "ROH", "STC"
            ]
            selected_client = st.selectbox("Select client code to test", client_codes)
            
            if selected_client:
                st.write(f"Testing with client code: {selected_client}")
                
                # Allow selecting a test month 
                test_months = ["January", "February", "March", "April", "May", "June", 
                              "July", "August", "September", "October", "November", "December"]
                current_month_index = datetime.now().month - 1
                selected_month_name = st.selectbox("Select month to test", test_months, index=current_month_index)
                
                # Create a date object for the selected month
                current_year = datetime.now().year
                test_date = datetime(current_year, test_months.index(selected_month_name) + 1, 1)
                
                # Test the function
                contract_data = get_support_contract_data(google_client, selected_client, test_date)
                
                if "error" in contract_data:
                    st.error(f"Error: {contract_data.get('error')}")
                    if "traceback" in contract_data:
                        with st.expander("Show error details"):
                            st.code(contract_data.get("traceback"))
                    
                    # Add debugging information
                    with st.expander("Debugging Information"):
                        # Find the spreadsheet data for the selected client
                        all_values = worksheet.get_all_values()
                        client_row = None
                        for i, row in enumerate(all_values):
                            if i > 2 and row and len(row) > 0 and row[0]:
                                if selected_client.lower() in row[0].lower():
                                    client_row = row
                                    st.write(f"Found client in row {i}: {row[0]}")
                                    st.write(f"Client row data: {row}")
                                    break
                        
                        # Show month headers
                        if len(all_values) > 0:
                            st.write("Month row data:")
                            for i in range(0, 3):
                                if i < len(all_values):
                                    st.write(f"Row {i}: {all_values[i]}")
                        
                        # Show header row with column names
                        if len(all_values) > 1:
                            st.write("Header row with column names:")
                            st.write(f"Row 1: {all_values[1]}")
                            
                        # Look for "Carry over" columns
                        st.write("Looking for 'Carry over' columns:")
                        for i in range(1, 3):
                            if i < len(all_values):
                                carry_cols = [(j, cell) for j, cell in enumerate(all_values[i]) 
                                              if "carry" in cell.lower() and "over" in cell.lower()]
                                if carry_cols:
                                    st.write(f"Found in row {i}: {carry_cols}")
                                    
                        # Look for month columns
                        st.write(f"Looking for month '{selected_month_name}' columns:")
                        for i in range(0, 3):
                            if i < len(all_values):
                                month_cols = [(j, cell) for j, cell in enumerate(all_values[i]) 
                                              if selected_month_name in cell]
                                if month_cols:
                                    st.write(f"Found in row {i}: {month_cols}")
                else:
                    st.success("Successfully retrieved support contract data")
                    st.write(f"Client: {contract_data.get('client')}")
                    st.write(f"Month: {contract_data.get('month')}")
                    st.write(f"Carryover hours: {contract_data.get('carryover_hours')}")
                    st.write(f"Inclusive hours: {contract_data.get('inclusive_hours')}")
                    
                    # Show the details that helped us find the data
                    with st.expander("How we found this data"):
                        st.write("""
                        1. Used the client code to find the client's row in the spreadsheet
                        2. Found the month column based on the month name
                        3. Located carryover hours by finding the "Carry over to next month" column for that month
                        4. Got inclusive hours from the "Monthly inclusive hours" column (column 2)
                        """)
                        # Show fiscal year information
                        fiscal_year = get_fiscal_year(test_date)
                        st.write(f"Fiscal year for {selected_month_name}: {fiscal_year}")
        else:
            st.warning("No client data found in the spreadsheet.")
    
    except Exception as e:
        st.error(f"Error accessing the spreadsheet: {str(e)}")
        st.write("Detailed error information to help debugging:")
        import traceback
        st.code(traceback.format_exc())