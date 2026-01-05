import os
from typing import TypedDict, Literal, Dict, Any, List
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from tavily import TavilyClient
import database
import processor 
import json
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Initialize LLM
def get_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found")
    return ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0, google_api_key=api_key)

# Helper for Database Service
@contextmanager
def get_db_service():
    """Yields a DatabaseService instance with a managed session."""
    db_gen = database.get_db()
    db = next(db_gen)
    try:
        service = database.DatabaseService(db)
        yield service
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
        except Exception:
            pass

# Define State
class AgentState(TypedDict):
    user_input: str
    intent: Literal["STORE_NOTE", "CREATE_TASK", "SEARCH_MEMORY", "GET_CREDENTIALS", "UNKNOWN", "INSERT", "QUERY", "RESEARCH"] # Added legacy for compatibility checks
    processed_data: Dict[str, Any] # Holds the structured output from InputProcessor
    memory_context: str
    web_context: str
    final_answer: str

# --- Nodes ---

def listener_agent(state: AgentState):
    """
    Uses the Semantic Router (InputProcessor) to classify intent and extract data.
    This replaces the simple LLM classification.
    """
    print("👂 Listener Agent: Semantic Routing...")
    
    input_processor = processor.InputProcessor()
    processed_result = input_processor.process(state["user_input"])
    
    intent = processed_result.get("intent", "UNKNOWN")
    print(f"   Intent: {intent}")
    print(f"   Reasoning: {processed_result.get('reasoning')}")
    
    # Map Processor Intents to Graph Routes if needed, or update routes
    # Current Graph Routes: inserter, researcher, memory
    # Mapping:
    # STORE_NOTE -> inserter
    # CREATE_TASK -> inserter (handled there)
    # SEARCH_MEMORY -> memory
    # GET_CREDENTIALS -> memory (or specific credential handler)
    # UNKNOWN -> advisor (to ask clarification)
    
    return {
        "intent": intent, 
        "processed_data": processed_result
    }

def researcher_agent(state: AgentState):
    """Fetches information from the web using Tavily with Context-Awareness."""
    print("🕵️ Researcher Agent: Searching the web...")
    
    # 1. Recall Context
    memory_context = ""
    with get_db_service() as db_service:
        results = db_service.hybrid_search(state["user_input"], k=3)
        memory_context = "\n".join([f"- {note.content}" for note in results])
    
    # 2. Refine Query (Simpler extraction from processed data if available, otherwise LLM)
    processed_data = state.get("processed_data", {})
    keywords = processed_data.get("keywords_for_mindmap", [])
    
    refined_query = state["user_input"]
    if keywords:
        refined_query = f"{state['user_input']} {' '.join(keywords)}"

    # 3. Search
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return {"web_context": "Error: TAVILY_API_KEY not found."}
        
    try:
        tavily = TavilyClient(api_key=tavily_key)
        # using the raw input or refined query
        response = tavily.search(query=refined_query, search_depth="basic")
        web_results = "\n".join([f"- {r['content']}" for r in response["results"]])
        full_context = f"Web Results for '{refined_query}':\n{web_results}"
        return {"web_context": full_context}
    except Exception as e:
        print(f"❌ Research failed: {e}")
        return {"web_context": "Could not fetch web results."}

def memory_agent(state: AgentState):
    """Searches the vector database for context."""
    print("🧠 Memory Agent: Recalling memories...")
    
    # We can use extracted entities to boost search
    processed_data = state.get("processed_data", {})
    entities = [e['name'] for e in processed_data.get("entities", [])]
    query = state["user_input"]
    
    context = ""
    with get_db_service() as db_service:
        # Hybrid search handles vector + keyword (we could optimize to filter by entities if implemented)
        results = db_service.hybrid_search(query, k=5)
        context = "\n\n".join([f"Memory: {note.content}" for note in results])
        
    return {"memory_context": context}

def inserter_agent(state: AgentState):
    """
    Handles STORE_NOTE and CREATE_TASK.
    Uses the data already extracted by the Semantic Router.
    """
    print("✍️ Inserter Agent: processing...")
    
    processed_data = state.get("processed_data", {})
    intent = state.get("intent")
    user_input = state["user_input"]
    
    with get_db_service() as db_service:
        # 1. Extract Data
        entity_objs = processed_data.get("entities", [])
        entity_names = [e['name'] for e in entity_objs]
        
        # 2. Save Note
        # We save the note with the vector embedding
        new_note = db_service.add_note(content=user_input, entity_names=entity_names)
        
        # 3. Handle Task Creation
        if intent == "CREATE_TASK":
            # Basic task creation logic (could be expanded)
            session = db_service.db
            new_task = database.Task(
                title=user_input,
                note_id=new_note.id,
                status="PENDING",
                priority=processed_data.get("priority", 1)
            )
            session.add(new_task)
            session.commit()
            print("   ✅ Task created.")

        # 4. Mindmap / Keyword Linking
        # Link entities to each other based on co-occurrence in this thought
        session = db_service.db
        if len(entity_names) > 1:
            # Fully connected graph for co-occurring entities
            # Get IDs
            entities = session.query(database.Entity).filter(database.Entity.name.in_(entity_names)).all()
            ids = [e.id for e in entities]
            
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    # Check if exists (simplified, usually need extraction of specific relation)
                    # For co-occurrence, we can use "RELATED_TO"
                    rel = database.Relationship(
                        source_id=ids[i], 
                        target_id=ids[j], 
                        relation_type="RELATED_TO",
                        strength=0.5
                    )
                    session.add(rel)
            session.commit()

    action_msg = "Saved note." if intent == "STORE_NOTE" else "Created task and saved note."
    return {"final_answer": f"{action_msg} Extracted {len(entity_names)} entities."}

def advisor_agent(state: AgentState):
    """Synthesizes an answer or asks for clarification."""
    print("🎓 Advisor Agent: Synthesizing answer...")
    
    intent = state.get("intent")
    processed_data = state.get("processed_data", {})
    
    # Handle UNKNOWN explicitly
    if intent == "UNKNOWN":
        clarification = processed_data.get("response_if_unknown", "I'm not sure how to handle that. Could you clarify?")
        return {"final_answer": clarification}

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
    
    # Map processor intents to nodes
    if intent in ["STORE_NOTE", "CREATE_TASK"]:
        return "inserter"
    # For research, we might need a specific trigger. 
    # Current Processor doesn't explicit output RESEARCH intent in the prompt list 
    # (The user prompt requested: STORE_NOTE, CREATE_TASK, SEARCH_MEMORY, GET_CREDENTIALS, UNKNOWN)
    # However, "SEARCH_MEMORY" covers query.
    # If we want web search, we might need logic inside memory agent to fallback, 
    # or add RESEARCH to processor.
    # For now, let's assume SEARCH_MEMORY goes to memory.
    elif intent in ["SEARCH_MEMORY", "GET_CREDENTIALS"]:
        return "memory"
    elif intent == "UNKNOWN":
        return "advisor"
    else:
        return "advisor"

workflow.add_conditional_edges(
    "listener",
    route_intent,
    {
        "inserter": "inserter",
        "memory": "memory",
        "advisor": "advisor" # UNKNOWN goes straight to advisor for clarification
        # Researcher is currently disconnected unless we add logic to route there.
        # We can route from memory -> advisor, and advisor could decide to tool call, 
        # or we update processor to detect "RESEARCH".
        # Given the requirements, I'll stick to the requested intents. 
    }
)

# Edges
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
        "intent": "UNKNOWN", 
        "processed_data": {},
        "memory_context": "",
        "web_context": "",
        "final_answer": ""
    }
    
    result = brain_app.invoke(initial_state)
    return result
