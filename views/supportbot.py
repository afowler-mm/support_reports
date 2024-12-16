import streamlit as st
from apis.claude import ChatBot


def display_supportbot():
    st.info('Support bot is under construction. Please try again later.')
    showmeanyway = st.checkbox('Show me anyway')
    if showmeanyway:
        
        st.write("`beep boop` 🤖")

        # button to clear the chat
        if st.button("Clear chat"):
            del st.session_state.messages
        
        if "messages" not in st.session_state:
            st.session_state.messages = []

        chatbot = ChatBot(st.session_state)

        # Display user and assistant messages
        for message in st.session_state.messages:
            if isinstance(message["content"], str):
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        if user_msg := st.chat_input("Type your message here..."):
            st.chat_message("user").markdown(user_msg)

            with st.chat_message("assistant"):
                with st.spinner("Claude is thinking..."):
                    response_placeholder = st.empty()
                    full_response = chatbot.process_user_input(user_msg)
                    response_placeholder.markdown(full_response)
        
        with st.expander("Debug"):
            st.write(st.session_state.messages)
