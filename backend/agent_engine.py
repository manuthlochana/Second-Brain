import os
import json
import logging
from datetime import datetime, timedelta
from typing import TypedDict, Literal, Dict, Any, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from sqlalchemy import select, and_

import database
import processor
import memory_manager
import persona_config
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
    return ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0.7, google_api_key=api_key)

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

def get_user_profile(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Loads user profile from database."""
    with get_db_session() as session:
        result = session.execute(select(database.UserProfile).limit(1))
        profile = result.scalar_one_or_none()
        
        if not profile:
            logger.info("Creating new profile for 'Manuth'")
            profile = database.UserProfile(
                name="Manuth",
                bio_memory={"routines": [], "preferences": {}, "tone": "Casual"},
                stats={"loyalty_score": 50, "interaction_count": 0}
            )
            session.add(profile)
            session.commit()
            session.refresh(profile)
        
        return {
            "id": str(profile.id),
            "name": profile.name,
            "bio_memory": profile.bio_memory,
            "stats": profile.stats
        }

def update_interaction_stats(user_id: str):
    """Updates user interaction statistics."""
    with get_db_session() as session:
        profile = session.execute(
            select(database.UserProfile).where(database.UserProfile.id == user_id)
        ).scalar_one_or_none()
        
        if profile:
            stats = dict(profile.stats)
            stats["interaction_count"] = stats.get("interaction_count", 0) + 1
            stats["last_interaction"] = datetime.now().isoformat()
            stats["loyalty_score"] = min(100, stats.get("loyalty_score", 50) + 0.2)
            profile.stats = stats
            session.commit()

# --- Tavily Search Integration ---

def search_external(query: str) -> str:
    """Performs external web search using Tavily API."""
    try:
        from tavily import TavilyClient
        
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            logger.warning("TAVILY_API_KEY not found, skipping external search")
            return "External search unavailable (API key missing)"
        
        client = TavilyClient(api_key=api_key)
        results = client.search(query, max_results=3)
        
        # Format results
        formatted = []
        for idx, result in enumerate(results.get('results', []), 1):
            formatted.append(
                f"{idx}. **{result.get('title', 'No title')}**\n"
                f"   {result.get('content', 'No content')}\n"
                f"   Source: {result.get('url', 'No URL')}"
            )
        
        return "\n\n".join(formatted) if formatted else "No results found"
        
    except ImportError:
        logger.error("tavily-python not installed. Install via: pip install tavily-python")
        return "External search unavailable (library not installed)"
    except Exception as e:
        logger.error(f"External search failed: {e}")
        return f"External search failed: {str(e)}"

# --- Intent Handlers ---

def handle_reflex(processed_data: Dict[str, Any]) -> str:
    """
    FAST PATH: Instant social responses.
    No database lookup, no heavy processing.
    """
    logger.info("⚡ REFLEX mode: Instant response")
    
    instant_reply = processed_data.get('instant_reply')
    if instant_reply:
        return instant_reply
    
    # Fallback canned responses
    return "Got it! 👍"

def handle_memory_write(user_input: str, processed_data: Dict[str, Any], user_id: str) -> str:
    """
    MEMORY WRITE: Extract facts and save to Pinecone + Supabase.
    Returns confirmation message with specific details.
    """
    logger.info("💾 MEMORY_WRITE mode: Storing facts")
    
    extracted_facts = processed_data.get('extracted_facts', [])
    
    if not extracted_facts:
        # Fallback: store the raw input
        try:
            result = memory_manager.memory_manager.save_memory(
                text=user_input,
                user_id=user_id,
                entities=[]
            )
            return "Noted! I've saved that."
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            return f"I tried to save that but ran into an issue: {str(e)}"
    
    # Store each fact using memory_manager (Pinecone + Supabase)
    stored_facts = []
    try:
        for fact in extracted_facts:
            full_fact = fact.get('full_fact', user_input)
            subject = fact.get('subject', '')
            
            # Extract entities
            entities = [subject] if subject else []
            
            # Save to both Pinecone and Supabase
            result = memory_manager.memory_manager.save_memory(
                text=full_fact,
                user_id=user_id,
                entities=entities
            )
            
            stored_facts.append(full_fact)
            logger.debug(f"Saved: {result}")
        
        # Generate smart confirmation
        if len(stored_facts) == 1:
            fact = stored_facts[0]
            return f"Noted, I'll remember: {fact}"
        else:
            facts_list = "\n- ".join(stored_facts)
            return f"Got it! I've saved {len(stored_facts)} things:\n- {facts_list}"
            
    except Exception as e:
        logger.error(f"Failed to save memories: {e}")
        return f"I tried to save that but ran into an issue: {str(e)}"

def handle_memory_read(user_input: str, processed_data: Dict[str, Any], user_id: str) -> str:
    """
    MEMORY READ: Search Pinecone and generate contextual response.
    This is where the AI proves it's NOT a dumb chatbot.
    """
    logger.info("🔍 MEMORY_READ mode: Recalling context")
    
    search_query = processed_data.get('search_query', user_input)
    
    # Retrieve context from Pinecone
    user_profile = get_user_profile(user_id)
    memory_context = memory_manager.memory_manager.search_memory(search_query, user_id)
    
    if not memory_context or memory_context.strip() == "":
        # Check if we have ANY memories
        try:
            from vector_store import get_vector_store
            vs = get_vector_store()
            stats = vs.get_stats()
            total_vectors = stats.get('total_vectors', 0)
            
            if total_vectors == 0:
                return "I don't have any memories stored yet. Share something with me first!"
            else:
                return f"Hmm, I searched my memory but couldn't find anything about '{search_query}'. Can you give me more context?"
        except Exception as e:
            logger.error(f"Failed to check vector stats: {e}")
            return "I tried to search my memory but ran into an issue. Can you try rephrasing your question?"
    
    # Inject context into LLM prompt
    llm = get_llm()
    
    enhanced_prompt = persona_config.JARVIS_SYSTEM_PROMPT.format(
        user_name=user_profile["name"],
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        reflections="Context from memory",
        loyalty_score=user_profile["stats"].get("loyalty_score", 50)
    )
    
    template = enhanced_prompt + """

**CRITICAL CONTEXT FROM MY MEMORY:**
{context}

**User Question:** {question}

Rules:
- Use the context above to answer
- Reference specific details from memory naturally
- If the context doesn't contain the answer, say so honestly
- Be conversational and empathetic
- NEVER ignore the provided context
"""
    
    prompt = PromptTemplate(template=template, input_variables=["context", "question"])
    chain = prompt | llm
    
    response = chain.invoke({
        "context": memory_context,
        "question": user_input
    })
    
    return response.content

def handle_external(user_input: str, processed_data: Dict[str, Any]) -> str:
    """
    EXTERNAL: Web search for general knowledge.
    Uses Tavily to search and LLM to synthesize.
    """
    logger.info("🌐 EXTERNAL mode: Web search")
    
    external_query = processed_data.get('external_query', user_input)
    
    # Perform search
    search_results = search_external(external_query)
    
    if "unavailable" in search_results.lower() or "failed" in search_results.lower():
        return f"I tried to search for that but ran into issues: {search_results}"
    
    # Synthesize with LLM
    llm = get_llm()
    
    template = """
You are a helpful AI assistant answering a general knowledge question.

**User Question:** {question}

**Search Results:**
{search_results}

Synthesize the search results into a clear, concise answer. Cite sources when relevant.
If the results don't answer the question, say so honestly.
"""
    
    prompt = PromptTemplate(template=template, input_variables=["question", "search_results"])
    chain = prompt | llm
    
    response = chain.invoke({
        "question": user_input,
        "search_results": search_results
    })
    
    return response.content

# --- Main Entry Point ---

def run_agent(user_input: str, user_id: Optional[str] = None) -> str:
    """
    Main agent execution with human-like intent recognition.
    
    Flow:
    1. Classify intent (REFLEX / MEMORY_WRITE / MEMORY_READ / EXTERNAL)
    2. Route to appropriate handler
    3. Update user stats
    4. Return response
    """
    logger.info(f"🚀 Agent Started: '{user_input[:50]}...'")
    
    # Get or create user profile
    if not user_id:
        profile = get_user_profile()
        user_id = profile["id"]
    
    try:
        # STEP 1: Classify Intent
        p = processor.InputProcessor()
        processed_data = p.process(user_input)
        
        intent = processed_data.get('intent', 'MEMORY_READ')
        logger.info(f"   Intent: {intent} (confidence: {processed_data.get('confidence', 0.0)})")
        
        # STEP 2: Route to Handler
        if intent == "REFLEX":
            response = handle_reflex(processed_data)
            
        elif intent == "MEMORY_WRITE":
            response = handle_memory_write(user_input, processed_data, user_id)
            
        elif intent == "MEMORY_READ":
            response = handle_memory_read(user_input, processed_data, user_id)
            
        elif intent == "EXTERNAL":
            response = handle_external(user_input, processed_data)
            
        else:
            # Fallback
            logger.warning(f"Unknown intent: {intent}, defaulting to MEMORY_READ")
            response = handle_memory_read(user_input, processed_data, user_id)
        
        # STEP 3: Update Stats
        update_interaction_stats(user_id)
        
        logger.info(f"✅ Response generated successfully")
        return response
        
    except Exception as e:
        logger.error(f"❌ Agent Error: {e}", exc_info=True)
        return f"Sorry, I encountered an error: {str(e)}"

# --- Async Streaming Support ---

async def astream_agent(user_input: str, user_id: Optional[str] = None):
    """
    Async Generator for Streaming Responses.
    Yields:
    - "THINKING: <status>"
    - "TOKEN: <text>"
    """
    logger.info(f"📡 Streaming Agent Started: '{user_input[:50]}...'")
    
    # Get user profile
    if not user_id:
        profile = get_user_profile()
        user_id = profile["id"]
    else:
        profile = get_user_profile(user_id)
    
    try:
        # STEP 1: Classify Intent
        yield "THINKING: Classifying intent..."
        p = processor.InputProcessor()
        processed_data = p.process(user_input)
        intent = processed_data.get('intent', 'MEMORY_READ')
        
        yield f"THINKING: Mode - {intent}"
        
        # STEP 2: Handle based on intent
        if intent == "REFLEX":
            # Instant - no streaming needed
            response = handle_reflex(processed_data)
            yield f"TOKEN: {response}"
            return
            
        elif intent == "MEMORY_WRITE":
            # Store facts - no streaming needed
            response = handle_memory_write(user_input, processed_data, user_id)
            yield f"TOKEN: {response}"
            return
            
        elif intent == "EXTERNAL":
            yield "THINKING: Searching the web..."
            response = handle_external(user_input, processed_data)
            # Stream the response token by token
            for token in response.split():
                yield f"TOKEN: {token} "
            return
            
        elif intent == "MEMORY_READ":
            yield "THINKING: Searching my memory..."
            
            search_query = processed_data.get('search_query', user_input)
            memory_context = memory_manager.memory_manager.retrieve_context(search_query, user_id)
            
            if not memory_context or memory_context.strip() == "":
                yield "TOKEN: I don't have any relevant memories about that."
                return
            
            yield "THINKING: Synthesizing response..."
            
            # Stream LLM response
            llm = get_llm()
            enhanced_prompt = persona_config.JARVIS_SYSTEM_PROMPT.format(
                user_name=profile["name"],
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                reflections="Context from memory",
                loyalty_score=profile["stats"].get("loyalty_score", 50)
            )
            
            template = enhanced_prompt + """

**CRITICAL CONTEXT FROM MY MEMORY:**
{context}

**User Question:** {question}

Use the context to answer naturally and empathetically.
"""
            
            prompt = PromptTemplate(template=template, input_variables=["context", "question"])
            chain = prompt | llm
            
            async for chunk in chain.astream({"context": memory_context, "question": user_input}):
                if chunk.content:
                    yield f"TOKEN: {chunk.content}"
        
        # Update stats
        update_interaction_stats(user_id)
        
    except Exception as e:
        logger.error(f"❌ Streaming Error: {e}", exc_info=True)
        yield f"TOKEN: Error: {str(e)}"

if __name__ == "__main__":
    # Quick test
    print("\n" + "="*80)
    print("AGENT ENGINE TEST")
    print("="*80 + "\n")
    
    test_cases = [
        "Hi there!",
        "I bought Sony WH-CH520 headphones",
        "What headphones do I have?",
        "Who is the president?",
    ]
    
    for test_input in test_cases:
        print(f"\n💬 User: {test_input}")
        print(f"🤖 Jarvis: {run_agent(test_input)}")
        print("-" * 80)
