import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta

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

# Example usage within a Streamlit app:
if __name__ == "__main__":
    chosen_month = month_selector()
    st.write(f"You selected: {chosen_month}")