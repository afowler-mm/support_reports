import slack_sdk
from datetime import datetime

slack_api_token = st.secrets["slack_api_token"]

client = slack_sdk.WebClient(token=slack_api_token)
support_channels = ["support-general", "support-on-call"]

# find threads containing mention of this ticket number
def find_threads(ticket):
    threads = client.search_messages(query=ticket, sort="timestamp", sort_dir="desc", count=50)["messages"]["matches"]
    # ignore threads not in the support_channels
    threads = [thread for thread in threads if thread["channel"]["name"] in support_channels]

    if len(threads) == 0:
        return "No threads found."

    thread_string = ""
    user_dict = {}  # Initialize a dictionary to store user information
    # make a readable version of all the messages in each thread
    for thread in threads:
        thread_messages = client.conversations_replies(channel=thread["channel"]["id"], ts=thread["ts"])["messages"]
        readable_messages = []
        for message in thread_messages:
            try:
                user_id = message["user"]
                # If user information is not in the dictionary, make an API call
                if user_id not in user_dict:
                    user_info = client.users_info(user=user_id)
                    user_name = user_info["user"]["real_name"]
                    # Store user information in the dictionary
                    user_dict[user_id] = user_name
                else:
                    # Retrieve user information from the dictionary
                    user_name = user_dict[user_id]
            except KeyError:
                # handle missing user information
                user_name = "Unknown User"
            
            # convert timestamp to datetime
            timestamp = datetime.fromtimestamp(float(message["ts"])).strftime('%Y-%m-%d %H:%M:%S')
            
            # format message
            readable_message = f"{user_name} ({timestamp}): {message.get('text', '')}"
            readable_messages.append(readable_message)
        
        thread["messages"] = readable_messages

        thread_string += "\n".join(readable_messages)
        thread_string += "\n\n"  # Add a separator between threads

    return thread_string
