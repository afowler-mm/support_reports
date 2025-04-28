import streamlit as st
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta

def get_fiscal_year(date_obj=None):
    """
    Determine the fiscal year for a given date in the format "YY/YY".
    Fiscal year starts on October 1.
    
    Args:
        date_obj (datetime, optional): The date to check. Defaults to today.
        
    Returns:
        str: Fiscal year in format "YY/YY" (e.g. "23/24")
    """
    if date_obj is None:
        date_obj = datetime.now()
    
    year_short = date_obj.year % 100  # Get last two digits
    
    # If we're in October or later, we're in the next fiscal year
    if date_obj.month >= 10:  # October or later
        return f"{year_short}/{year_short + 1}"
    else:
        return f"{year_short - 1}/{year_short}"

def month_selector(years_back: int = 3, label: str = "Select month") -> str:
    """
    Displays a selectbox with a reverse-chronological list of months going back `years_back` years,
    defaulting to the current calendar month, and returns the selected month as a string.
    
    Args:
        years_back (int): How many years back to include.
        label (str): The label for the selectbox.

    Returns:
        str: The selected month in "Month YYYY" format.
    """
    now = datetime.now()
    options = []
    # Generate a list of months from current going back 'years_back' years
    for i in range(years_back * 12):
        month_date = now - relativedelta(months=i)
        options.append(month_date.strftime("%B %Y"))

    # The first element is the current month by construction
    selected = st.selectbox(label, options, index=0)
    return selected

def date_range_selector():
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=60))
        with col2:
            end_date = st.date_input("End date", value=date.today())
        return {
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d')
        }

def get_support_contract_data(client, company_code, month_date=None):
    """
    Fetch support contract data for a specific client and month from the Google Spreadsheet.
    
    Args:
        client: Google Sheets client
        company_code: The client's company code to look for in the spreadsheet
        month_date: A datetime object representing the month to get data for (defaults to current month)
    
    Returns:
        dict: Support contract data containing:
            - carryover_hours: Hours carried over from previous month
            - inclusive_hours: Hours included in support contract
    """
    if month_date is None:
        month_date = datetime.now()
    
    # Determine the fiscal year for the given month
    fiscal_year = get_fiscal_year(month_date)
    
    # The spreadsheet ID for support contracts
    spreadsheet_id = "1OXy-yuN_Qne2Pc7uc18V2eKXiDkWIEp88y68lHG1FDU"
    
    # Calculate the previous month (for looking up carryover values)
    if month_date.month == 1:  # January
        prev_month_date = datetime(month_date.year - 1, 12, 1)  # December of previous year
    else:
        prev_month_date = datetime(month_date.year, month_date.month - 1, 1)
    
    # Determine the fiscal year for the previous month
    prev_fiscal_year = get_fiscal_year(prev_month_date)
    
    try:
        # Open the spreadsheet 
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # Find the worksheet for the current fiscal year
        worksheet = None
        for ws in spreadsheet.worksheets():
            if ws.title == fiscal_year:
                worksheet = ws
                break
        
        if not worksheet:
            return {"error": f"Could not find worksheet for fiscal year {fiscal_year}"}
        
        # Get all values from the worksheet (handles merged cells better)
        all_values = worksheet.get_all_values()
        
        if not all_values:
            return {"error": "Worksheet is empty"}
        
        # Find the client's row
        client_row = None
        for i, row in enumerate(all_values):
            if i > 2 and row and len(row) > 0 and row[0]:  # Skip header rows
                # Match the client by company code (could be full name or short code)
                if company_code.lower() in row[0].lower():
                    client_row = row
                    break
        
        if not client_row:
            return {"error": f"Client with code {company_code} not found in spreadsheet"}
        
        # Find month columns (check rows 0-4 to be safe)
        month_row = None
        month_row_index = 0
        for i in range(0, 5):  # Check rows 0-4
            if i < len(all_values):
                # Check if this row contains month names
                has_months = False
                for cell in all_values[i]:
                    for month_name in [
                        "January", "February", "March", "April", "May", "June", 
                        "July", "August", "September", "October", "November", "December"
                    ]:
                        if month_name in cell:
                            has_months = True
                            break
                    if has_months:
                        break
                
                if has_months:
                    month_row = all_values[i]
                    month_row_index = i
                    break
        
        if not month_row:
            return {"error": "Could not identify month columns in spreadsheet"}
        
        # Get inclusive hours from the dedicated column (column 2 based on the example)
        inclusive_hours_col_index = 2  # "Monthly inclusive hours" column
        inclusive_hours = 0
        if inclusive_hours_col_index < len(client_row) and client_row[inclusive_hours_col_index]:
            try:
                inclusive_hours_value = client_row[inclusive_hours_col_index].strip()
                if inclusive_hours_value and inclusive_hours_value.replace('.', '', 1).isdigit():
                    inclusive_hours = float(inclusive_hours_value)
            except (ValueError, TypeError):
                pass  # Not a valid number
        
        # For carryover hours, we need the previous month's "Carry over to next month" value
        carryover_hours = 0
        
        # Special case for October: look at previous fiscal year's September
        if month_date.month == 10:  # October
            # We need September from the previous fiscal year's worksheet
            prev_worksheet = None
            for ws in spreadsheet.worksheets():
                if ws.title == prev_fiscal_year:
                    prev_worksheet = ws
                    break
            
            if prev_worksheet:
                # Get September's "Carry over to next month" value from previous fiscal year
                prev_values = prev_worksheet.get_all_values()
                
                # Find the client in the previous worksheet
                prev_client_row = None
                for i, row in enumerate(prev_values):
                    if i > 2 and row and len(row) > 0 and row[0]:
                        if company_code.lower() in row[0].lower():
                            prev_client_row = row
                            break
                
                if prev_client_row:
                    # Find September in the previous fiscal year's worksheet
                    prev_month_row = None
                    for i in range(0, 5):
                        if i < len(prev_values):
                            has_months = False
                            for cell in prev_values[i]:
                                if "September" in cell:
                                    has_months = True
                                    break
                            if has_months:
                                prev_month_row = prev_values[i]
                                break
                    
                    if prev_month_row:
                        # Find September column
                        sept_col_index = None
                        for i, cell in enumerate(prev_month_row):
                            if "September" in cell:
                                sept_col_index = i
                                break
                        
                        if sept_col_index is not None:
                            # Find September's "Carry over to next month" column
                            prev_header_row = prev_values[1] if len(prev_values) > 1 else []
                            sept_carryover_col_index = None
                            
                            for i in range(sept_col_index, min(sept_col_index + 10, len(prev_header_row))):
                                if i < len(prev_header_row) and "carry over to next month" in prev_header_row[i].lower():
                                    sept_carryover_col_index = i
                                    break
                            
                            if sept_carryover_col_index is not None and len(prev_client_row) > sept_carryover_col_index:
                                try:
                                    carryover_value = prev_client_row[sept_carryover_col_index].strip()
                                    if carryover_value and carryover_value.replace('.', '', 1).replace('-', '', 1).isdigit():
                                        carryover_hours = float(carryover_value)
                                except (ValueError, TypeError):
                                    pass  # Not a valid number
            else:
                # If we couldn't find the previous fiscal year worksheet,
                # check for "Carried Over from" column (column 5 based on example)
                carried_over_col_index = 5  # "Carried Over from" column
                if carried_over_col_index < len(client_row) and client_row[carried_over_col_index]:
                    try:
                        carryover_value = client_row[carried_over_col_index].strip()
                        if carryover_value and carryover_value.replace('.', '', 1).replace('-', '', 1).isdigit():
                            carryover_hours = float(carryover_value)
                    except (ValueError, TypeError):
                        pass  # Not a valid number
        else:
            # For other months, find the previous month in the current worksheet
            prev_month_name = prev_month_date.strftime("%B")
            prev_month_col_index = None
            
            for i, cell in enumerate(month_row):
                if prev_month_name in cell:
                    prev_month_col_index = i
                    break
            
            if prev_month_col_index is not None:
                # Get header row - should be row 1 based on the example
                header_row = all_values[1] if len(all_values) > 1 else []
                
                # Find the "Carry over to next month" column for the previous month
                prev_carry_over_col_index = None
                for i in range(prev_month_col_index, min(prev_month_col_index + 10, len(header_row))):
                    if i < len(header_row) and "carry over to next month" in header_row[i].lower():
                        prev_carry_over_col_index = i
                        break
                
                if prev_carry_over_col_index is not None:
                    # Find the cell in the client's row that corresponds to previous month's carryover
                    if len(client_row) > prev_carry_over_col_index and client_row[prev_carry_over_col_index]:
                        try:
                            carryover_value = client_row[prev_carry_over_col_index].strip()
                            if carryover_value and carryover_value.replace('.', '', 1).replace('-', '', 1).isdigit():
                                carryover_hours = float(carryover_value)
                        except (ValueError, TypeError):
                            pass  # Not a valid number
        
        # If we still don't have inclusive hours, try using a field from the company data in Freshdesk
        return {
            "carryover_hours": carryover_hours,
            "inclusive_hours": inclusive_hours,
            "month": month_date.strftime("%B %Y"),
            "client": client_row[0] if client_row else None,
            "prev_month": prev_month_date.strftime("%B %Y")
        }
    
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }