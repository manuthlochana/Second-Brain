import os
from typing import TypedDict, Literal
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from tavily import TavilyClient
import database
import processor
import json

# Load environment variables
load_dotenv()

# Initialize LLM
def get_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found")
    return ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0, google_api_key=api_key)

# Define State
class AgentState(TypedDict):
    user_input: str
    intent: Literal["INSERT", "QUERY", "RESEARCH"]
    memory_context: str
    web_context: str
    final_answer: str

# --- Nodes ---

def listener_agent(state: AgentState):
    """Classifies user intent."""
    print("👂 Listener Agent: Analyzing intent...")
    llm = get_llm()
    
    template = """
    You are the consciousness of a Second Brain.
    Classify the user's input into one of these intents:
    1. INSERT: The user is sharing a fact, memory, or idea to save. (e.g., "I like apples", "Steve Jobs founded Apple")
    2. QUERY: The user is asking a question about stored memories. (e.g., "What do I like?", "Who founded Apple?")
    3. RESEARCH: The user is asking for new information from the web. (e.g., "What is the latest iPhone price?", "Who won the 2024 election?")
    
    Input: {input}
    
    Return ONLY one word: INSERT, QUERY, or RESEARCH.
    """
    prompt = PromptTemplate(template=template, input_variables=["input"])
    chain = prompt | llm
    response = chain.invoke({"input": state["user_input"]})
    intent = response.content.strip().upper()
    
    # Fallback for safety
    if intent not in ["INSERT", "QUERY", "RESEARCH"]:
        intent = "QUERY"
        
    print(f"👂 Intent detected: {intent}")
    return {"intent": intent}

def researcher_agent(state: AgentState):
    """Fetches information from the web using Tavily."""
    print("🕵️ Researcher Agent: Searching the web...")
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return {"web_context": "Error: TAVILY_API_KEY not found."}
        
    try:
        tavily = TavilyClient(api_key=tavily_key)
        response = tavily.search(query=state["user_input"], search_depth="basic")
        context = "\n".join([r["content"] for r in response["results"]])
        return {"web_context": context}
    except Exception as e:
        print(f"❌ Research failed: {e}")
        return {"web_context": "Could not fetch web results."}

def memory_agent(state: AgentState):
    """Searches the vector database for context."""
    print("🧠 Memory Agent: Recalling memories...")
    context = database.search_memory(state["user_input"])
    return {"memory_context": context}

def inserter_agent(state: AgentState):
    """Extracts entities and saves to Graph and Vector DB."""
    print("✍️ Inserter Agent: Saving memory...")
    text = state["user_input"]
    
    # 1. Extract Entities (Graph)
    graph_data = processor.analyze_text(text)
    database.save_to_graph(graph_data)
    
    # 2. Save Vector
    database.save_to_vector(text)
    
    return {"final_answer": f"Saved to memory! Extracted {len(graph_data.get('nodes', []))} entities."}

def advisor_agent(state: AgentState):
    """Synthesizes an answer from Memory or Web context."""
    print("🎓 Advisor Agent: Synthesizing answer...")
    llm = get_llm()
    
    context = state.get("memory_context") or state.get("web_context") or "No context available."
    
    template = """
    You are a wise Second Brain Advisor.
    Answer the user's question based on the provided context.
    
    Context:
    {context}
    
    User Question: {input}
    
    Answer concisely and helpfully.
    """
    prompt = PromptTemplate(template=template, input_variables=["context", "input"])
    chain = prompt | llm
    response = chain.invoke({"context": context, "input": state["user_input"]})
    
    return {"final_answer": response.content}

# --- Graph Construction ---

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("listener", listener_agent)
workflow.add_node("researcher", researcher_agent)
workflow.add_node("memory", memory_agent)
workflow.add_node("inserter", inserter_agent)
workflow.add_node("advisor", advisor_agent)

# Set Entry Point
workflow.set_entry_point("listener")

# Conditional Edges
def route_intent(state: AgentState):
    intent = state["intent"]
    if intent == "INSERT":
        return "inserter"
    elif intent == "RESEARCH":
        return "researcher"
    else:
        return "memory"

workflow.add_conditional_edges(
    "listener",
    route_intent,
    {
        "inserter": "inserter",
        "researcher": "researcher",
        "memory": "memory"
    }
)

# Edges to Advisor or End
workflow.add_edge("researcher", "advisor")
workflow.add_edge("memory", "advisor")
workflow.add_edge("advisor", END)
workflow.add_edge("inserter", END)

# Compile
brain_app = workflow.compile()

def process_thought(user_input: str):
    """Main entry point for the API."""
    initial_state = {
        "user_input": user_input,
        "intent": "QUERY", # Default
        "memory_context": "",
        "web_context": "",
        "final_answer": ""
    }
    
    result = brain_app.invoke(initial_state)
    return result
