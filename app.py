import streamlit as st
import asyncio
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import processor
import database
import visualizer
from streamlit_agraph import agraph

# 1. Wide Layout (Must be first Streamlit command)
st.set_page_config(layout="wide", page_title="Second Brain AI")

# Fix for "RuntimeError: There is no current event loop in thread"
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Load environment variables
load_dotenv()

# Check for Google API Key
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    st.error("❌ `GOOGLE_API_KEY` not found. Please add it to your `.env` file.")
    st.stop()

# Initialize the Gemini model
try:
    llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key)
except Exception as e:
    st.error(f"Failed to initialize Gemini: {e}")
    st.stop()

# Custom CSS for Chat Styling
st.markdown("""
<style>
    /* User Message Style */
    .user-message {
        background-color: #2b313e;
        color: #ffffff;
        padding: 10px 15px;
        border-radius: 15px 15px 0 15px;
        text-align: right;
        float: right;
        max-width: 80%;
        margin-bottom: 10px;
        display: inline-block;
        clear: both;
    }
    
    /* Container fix to allow floating */
    [data-testid="stChatMessageContent"] {
        display: block;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

st.title("Second Brain AI 🧠")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# 2. Create Columns
col_chat, col_graph = st.columns([1, 2])

# --- LEFT COLUMN (Chat) ---
with col_chat:
    st.subheader("💬 Chat")
    
    # Mode Selection
    mode = st.radio("Mode", ["Query", "Insert"], horizontal=True, index=0)
    
    # Display Chat History
    # Using a container for scrollable chat history
    chat_container = st.container(height=600)
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.markdown(f'<div class="user-message">{message["content"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(message["content"])

    # Chat Input
    if prompt := st.chat_input("Type here..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Display user message immediately
        with chat_container:
            with st.chat_message("user"):
                st.markdown(f'<div class="user-message">{prompt}</div>', unsafe_allow_html=True)

        # Handle Logic based on Mode
        if mode == "Query":
            with chat_container:
                with st.chat_message("assistant"):
                    try:
                        with st.spinner("Searching memory..."):
                            context = database.search_memory(prompt)
                        
                        if context:
                            rag_prompt = f"Context from memory:\n{context}\n\nUser Question: {prompt}\n\nAnswer the question using the context provided."
                        else:
                            rag_prompt = prompt
                        
                        response = llm.invoke(rag_prompt)
                        st.markdown(response.content)
                        st.session_state.messages.append({"role": "assistant", "content": response.content})
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

        elif mode == "Insert":
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("Saving to Brain..."):
                        try:
                            result = processor.analyze_text(prompt)
                            database.save_to_graph(result)
                            database.save_to_vector(prompt)
                            
                            num_entities = len(result.get("nodes", []))
                            success_msg = f"Saved! Extracted {num_entities} entities."
                            st.markdown(success_msg)
                            with st.expander("Debug Data"):
                                st.json(result)
                            st.session_state.messages.append({"role": "assistant", "content": success_msg})
                        except Exception as e:
                            st.error(f"Error: {e}")

# --- RIGHT COLUMN (Graph) ---
with col_graph:
    st.subheader("🧠 Knowledge Graph")
    search_query = st.text_input("🔍 Search Memory...", key="search_bar")
    
    with st.spinner("Loading Graph..."):
        nodes, edges, config = visualizer.get_graph_data()
        
    if nodes:
        agraph(nodes=nodes, edges=edges, config=config)
    else:
        st.info("Graph is empty. Switch to 'Insert' mode to add data!")
