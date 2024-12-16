import streamlit as st
from anthropic import Anthropic

class ChatBot:
    def __init__(self, session_state):
        # Get the API key from Streamlit secrets
        api_key = st.secrets["anthropic_api_token"]
        if not api_key:
            raise ValueError("Missing API key in Streamlit secrets!")
        self.anthropic = Anthropic(api_key=api_key)
        self.session_state = session_state

    def generate_message(self, messages, max_tokens):
        try:
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                messages=messages,
            )
            return response
        except Exception as e:
            return {"error": str(e)}

    def process_user_input(self, user_input):
        messages = self.session_state.messages
        messages.append({"role": "user", "content": user_input})
        
        # Generate the response
        response = self.generate_message(messages, 100)

        # Debug: print the response structure
        print(response)

        # Handle potential errors in the response
        if "error" in response:
            assistant_message = f"Error: {response['error']}"
        else:
            # Extract the assistant's message from the content attribute
            assistant_message = response.content[0].text  # Access content as an attribute
        
        # Add the assistant's response to the session state messages
        messages.append({"role": "assistant", "content": assistant_message})
        return assistant_message