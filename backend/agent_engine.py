import os
import json
import logging
from datetime import datetime, timedelta
from typing import TypedDict, Literal, Dict, Any, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, END
from sqlalchemy import select, and_

import database
import processor
import memory_manager
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Setup logging
logger = logging.getLogger("CEO_BRAIN.agent_engine")

# --- Helpers ---

def get_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found")
    return ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0, google_api_key=api_key)

@contextmanager
def get_db_session():
    """Yields a DB session."""
    db_gen = database.get_db()
    db = next(db_gen)
    try:
        yield db
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
        except Exception:
            pass

# --- Agent State ---

class AgentState(TypedDict):
    # Core Inputs
    user_input: str
    user_id: str # UUID of the active user profile
    
    # Context
    user_profile: Dict[str, Any] # Loaded profile data
    memory_context: str # Retrieved vector memories
    web_context: str # Web search results
    
    # Reasoning
    intent: str
    processed_data: Dict[str, Any] # From Semantic Router
    plan: List[str] # For multi-step reasoning
    critique: str # From Critical Friend logic
    
    # Output
    final_answer: str

# --- Nodes ---

def profile_loader(state: AgentState):
    """Loads user profile and bio-memory."""
    logger.debug("Profile Loader: Fetching user persona...")
    
    with get_db_session() as session:
        # Singleton pattern for now: Get first profile or create default
        result = session.execute(select(database.UserProfile).limit(1))
        profile = result.scalar_one_or_none()
        
        if not profile:
            logger.info("Creating new profile for 'Manuth'")
            profile = database.UserProfile(
                name="Manuth",
                bio_memory={"routines": [], "preferences": {}, "tone": "Professional"},
                stats={"loyalty_score": 50, "interaction_count": 0}
            )
            session.add(profile)
            session.commit()
            session.refresh(profile)
            
        # Update interaction stats logic could go here or in Reflector
        
        user_data = {
            "id": str(profile.id),
            "name": profile.name,
            "bio_memory": profile.bio_memory,
            "stats": profile.stats
        }
        
    return {"user_profile": user_data, "user_id": str(profile.id)}

def semantic_router(state: AgentState):
    """Uses the existing Semantic Router to classify intent."""
    logger.debug("Semantic Router: Analyzing input...")
    p = processor.InputProcessor()
    result = p.process(state["user_input"])
    logger.info(f"Intent detected: {result.get('intent', 'UNKNOWN')}")
    return {"intent": result.get("intent", "UNKNOWN"), "processed_data": result}

def memory_retriever(state: AgentState):
    """Fetches relevant memories + Proactive Task Check."""
    logger.debug("Memory Retriever: Gathering context...")
    
    user_input = state["user_input"]
    user_profile = state["user_profile"]
    
    context_parts = []
    
    with get_db_session() as session:
        # 1. Deep Memory Retrieval
        # Use the highly specialized Memory Manager
        retrieved_memories = memory_manager.memory_manager.retrieve_context(user_input, state["user_id"])
        if retrieved_memories:
            context_parts.append(retrieved_memories)
            
        # 2. Proactive Task Check (Urgent tasks)
        # Check tasks due in the next 24 hours
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        
        # We need a proper query for due_date range
        # Assuming due_date is offset-aware or we manage naive correctly. 
        # database.py uses DateTime(timezone=True)
        
        urgent_tasks = session.execute(
            select(database.Task).where(
                and_(
                    database.Task.status != 'DONE',
                    database.Task.due_date <= tomorrow
                )
            ).order_by(database.Task.due_date)
        ).scalars().all()
        
        if urgent_tasks:
            task_list = [f"- {t.title} (Due: {t.due_date})" for t in urgent_tasks]
            context_parts.append("\n⚠️ Urgent Tasks:\n" + "\n".join(task_list))
            
    full_context = "\n\n".join(context_parts)
    return {"memory_context": full_context}

def reasoning_core(state: AgentState):
    """
    The 'Critical Friend'. Analyzes logic, safety, and coherence.
    Decides if the user's request is logical based on context.
    """
    logger.debug("Reasoning Core: Validating logic...")
    
    llm = get_llm()
    profile = state["user_profile"]
    context = state["memory_context"]
    input_text = state["user_input"]
    intent = state["intent"]
    
    # If trivial intent, skip heavy reasoning
    if intent in ["SEARCH_MEMORY", "UNKNOWN"]:
         return {"critique": "None"}

    template = """
    You are the 'Reasoning Core' of an advanced AI Assistant for {user_name}.
    Your Loyalty Score is {loyalty}.
    
    TASK: Analyze the User Request against the Context and Profile.
    
    User Profile: {bio_memory}
    Context/Memories: {context}
    User Request: {input}
    
    CHECKLIST:
    1. Is this request physically/financially possible given the context? (e.g., spending $5k with $2k balance).
    2. Is it safe and logical?
    3. Is it consistent with the user's long-term goals?
    
    OUTPUT:
    If Valid: Return "VALID".
    If Invalid/Illogical: Return a polite but firm counter-argument (The "Critical Friend" mode). Start with "CRITIQUE:".
    """
    
    prompt = PromptTemplate(template=template, input_variables=["user_name", "loyalty", "bio_memory", "context", "input"])
    
    chain = prompt | llm
    response = chain.invoke({
        "user_name": profile["name"], 
        "loyalty": profile["stats"].get("loyalty_score"),
        "bio_memory": json.dumps(profile["bio_memory"]),
        "context": context,
        "input": input_text
    })
    
    full_resp = response.content.strip()
    if full_resp.startswith("CRITIQUE:"):
        logger.warning(f"Critique generated: {full_resp[:100]}")
        return {"critique": full_resp}
    else:
        logger.debug("Logic verified")
        return {"critique": "None"}

def planner_node(state: AgentState):
    """
    Generates a plan if the request is complex or if a critique exists.
    """
    if state["critique"] != "None":
        # If there's a critique, the plan is to explain the critique and suggest alternatives.
        return {"plan": ["Explain critique", "Suggest alternative"], "final_answer": state["critique"]}

    # For now, simple pass-through unless it's a CREATE_TASK which we might plan out
    # If the user says "Plan a date", the Semantic Router might tag it as CREATE_TASK or UNKNOWN
    # We can detect complexity here.
    
    return {"plan": [], "final_answer": ""}

def executor_node(state: AgentState):
    """Executes the action (DB insert, Search, etc.)"""
    # If we have a critique, we skip execution of the original intent usually,
    # or effectively the execution is returning the critique.
    if state["critique"] != "None":
        return {} # Pass to reflector/end
        
    intent = state["intent"]
    processed = state["processed_data"]
    
    logger.info(f"Executor: Running {intent}...")
    
    # Reusing brain.py logic style but implemented cleanly here
    with get_db_session() as session:
        service = database.DatabaseService(session)
        
        if intent == "STORE_NOTE":
            service.add_note(state["user_input"], [e['name'] for e in processed.get("entities", [])])
            return {"final_answer": "Note saved successfully."}
            
        elif intent == "CREATE_TASK":
            # Just create the task
            # TODO: Extract date from processed_data dates_times
            date_str = processed.get("dates_times", [None])[0]
            due_date = None
            # Basic parsing placeholders - in prod use dateparser
            if date_str:
                # Naive attempt or leave None
                pass
                
            task = database.Task(
                title=state["user_input"],
                status="PENDING",
                due_date=due_date,
                priority=processed.get("priority", 1)
            )
            session.add(task)
            session.commit()
            return {"final_answer": f"Task '{state['user_input']}' created."}

        # SEARCH_MEMORY handled by context + advisor equivalent
    
    return {} # Fallback

def response_generator(state: AgentState):
    """Generates the final natural language response."""
    # If we already have a final answer (from Critique or Executor), usage it.
    if state.get("final_answer"):
        return {} 
        
    logger.debug("Response Generator: Synthesizing...")
    llm = get_llm()
    
    import persona_config
    from datetime import datetime
    
    # Fetch recent reflections (mock/db)
    reflections = "No major reflections yet."
    if profile.get("bio_memory", {}).get("reflections"):
        reflections = str(profile["bio_memory"]["reflections"][-3:])

    formatted_prompt = persona_config.JARVIS_SYSTEM_PROMPT.format(
        user_name=profile["name"],
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        reflections=reflections,
        loyalty_score=profile["stats"].get("loyalty_score", 50)
    )

    template = formatted_prompt + """
    
    Context/Memories: {context}
    User Request: {input}
    
    Draft a concise, professional response.
    """
    prompt = PromptTemplate(template=template, input_variables=["context", "input"])
    chain = prompt | llm
    res = chain.invoke({
        "context": state["memory_context"],
        "input": state["user_input"]
    })
    
    return {"final_answer": res.content}

def reflector_node(state: AgentState):
    """
    Post-interaction reflection.
    Updates User Profile (Bio-Memory) and Loyalty Score.
    """
    logger.debug("Reflector: Updating Persona...")
    
    with get_db_session() as session:
        # Load profile object
        profile = session.execute(select(database.UserProfile).where(database.UserProfile.id == state["user_id"])).scalar_one()
        
        # 1. Update Loyalty/Stats
        stats = dict(profile.stats)
        stats["interaction_count"] = stats.get("interaction_count", 0) + 1
        # Simple Logic: Interaction increases loyalty slightly
        stats["loyalty_score"] = min(100, stats.get("loyalty_score", 50) + 0.1)
        profile.stats = stats
        
        # 2. Extract Bio-Memory Update (LLM)
        # We check if we learned anything new about the user
        llm = get_llm()
        template = """
        Analyze this interaction for new facts about the user '{user_name}'.
        Interaction: {input}
        Response: {response}
        Current Bio: {bio}
        
        Return a JSON object with keys "new_routines" (list), "new_preferences" (dict), "life_events" (list).
        If nothing new, return empty lists/dicts.
        """
        # (Skipping full implementation for brevity, assuming simple update)
        
        session.commit()
        
    return {}

# --- Graph ---

workflow = StateGraph(AgentState)

workflow.add_node("profile_loader", profile_loader)
workflow.add_node("semantic_router", semantic_router)
workflow.add_node("memory_retriever", memory_retriever)
workflow.add_node("reasoning_core", reasoning_core)
workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)
workflow.add_node("response_generator", response_generator)
workflow.add_node("reflector", reflector_node)

workflow.set_entry_point("profile_loader")

workflow.add_edge("profile_loader", "semantic_router")
workflow.add_edge("semantic_router", "memory_retriever")
workflow.add_edge("memory_retriever", "reasoning_core")
workflow.add_edge("reasoning_core", "planner") # Planner checks critique
workflow.add_edge("planner", "executor")
workflow.add_edge("executor", "response_generator")
workflow.add_edge("response_generator", "reflector")
workflow.add_edge("reflector", END)

agent_app = workflow.compile()

def run_agent(user_input: str):
    logger.info(f"Agent Engine Started: '{user_input[:50]}...'")
    initial_state = {
        "user_input": user_input,
        "user_id": "",
        "user_profile": {},
        "memory_context": "",
        "web_context": "",
        "intent": "",
        "processed_data": {},
        "plan": [],
        "critique": "None",
        "final_answer": ""
    }
    
    
    result = agent_app.invoke(initial_state)
    return result["final_answer"]

async def astream_agent(user_input: str):
    """
    Async Generator for Streaming Responses.
    Yields:
    - "THINKING: <status>"
    - "TOKEN: <text>"
    """
    logger.info(f"Streaming Agent Started: '{user_input[:50]}...'")
    
    # Run the "Thinking" phases (Pre-computation)
    # We can use the graph, but we want to intercept the FINAL node.
    # Current LangGraph setup calculates final_answer in "response_generator"
    
    # 1. State Setup
    initial_state = {
        "user_input": user_input,
        "user_id": "",
        "user_profile": {},
        "memory_context": "",
        "intent": "",
        "processed_data": {},
        "plan": [],
        "critique": "None",
        "final_answer": ""
    }
    
    # 2. Run Intermediary Steps (Thinking)
    # We invoke the graph but we modify "response_generator" to NOT call invoke() 
    # but return the prompt inputs.
    # HOWEVER, modifying the compiled graph on the fly is hard.
    # ALTERNATIVE: We use the existing graph to get the state *before* generation?
    # Or simpler: We just run the graph to completion (since it's fast usually except LLM) 
    # BUT we want to stream the LLM part.
    
    # Let's manually run the nodes for the "Thinking" phase to get the PROMPT CONTEXT.
    # This duplicates logic slightly but ensures streaming works perfectly without refactoring the whole graph to async.
    
    yield "THINKING: Identifying Intent..."
    p_res = profile_loader(initial_state) 
    initial_state.update(p_res)
    
    s_res = semantic_router(initial_state)
    initial_state.update(s_res)
    
    yield f"THINKING: Accessing Memory... ({s_res['intent']})"
    m_res = memory_retriever(initial_state) # This uses DB, might block slightly
    initial_state.update(m_res)
    
    r_res = reasoning_core(initial_state)
    initial_state.update(r_res)
    
    pl_res = planner_node(initial_state)
    initial_state.update(pl_res)
    
    e_res = executor_node(initial_state)
    initial_state.update(e_res)
    
    # 3. Stream Generation
    # If executor provided a final answer (e.g. note stored), yield it directly.
    if initial_state.get("final_answer"):
        yield f"TOKEN: {initial_state['final_answer']}"
        return

    yield "THINKING: Synthesizing Response..."
    
    # Prepare Prompt (Same logic as response_generator)
    llm = get_llm()
    import persona_config
    from datetime import datetime
    
    # Profile might be inside user_profile dict now
    prof = initial_state["user_profile"] # dict
    
    # Safe access to stats
    loyalty = 50
    if "stats" in prof:
        loyalty = prof["stats"].get("loyalty_score", 50)
        
    formatted_prompt = persona_config.JARVIS_SYSTEM_PROMPT.format(
        user_name=prof.get("name", "User"),
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        reflections=" streaming mode ...", 
        loyalty_score=loyalty
    )
    
    template = formatted_prompt + """
    
    Context/Memories: {context}
    User Request: {input}
    
    Draft a concise, professional response.
    """
    prompt = PromptTemplate(template=template, input_variables=["context", "input"])
    
    chain = prompt | llm
    
    # Stream the tokens
    async for chunk in chain.astream({
        "context": initial_state["memory_context"],
        "input": initial_state["user_input"]
    }):
        if chunk.content:
            yield f"TOKEN: {chunk.content}"

