# Support Reports Project Guidelines

## Build & Run Commands
- Install dependencies: `pip install -r requirements.txt`
- Run application: `streamlit run app.py`
- Set up environment: Create `.env` file with required API keys

## Code Style Guidelines
- **Imports**: Standard library first, third-party second, local modules last
- **Naming**: snake_case for functions/variables, CamelCase for classes, ALL_CAPS for constants
- **Formatting**: 4 spaces for indentation
- **Types**: Use type hints for function parameters and return values
- **Error handling**: Use specific exception types in try/except blocks
- **Docstrings**: Include for all functions and classes
- **Streamlit**: Use caching decorators (@st.cache_resource, @st.cache_data) for performance
- **Comments**: Include inline comments for complex logic

## Project Structure
- `/apis`: External API integrations (Freshdesk, Claude, etc.)
- `/views`: Streamlit UI components
- Root: Core application logic and utilities

This is a Streamlit application for managing support reports via the FreshDesk API.