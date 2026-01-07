import os
import json
from typing import List, Optional, Literal, Dict
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# --- Pydantic Models ---

class ExtractedFact(BaseModel):
    """Structured fact extracted from user input."""
    subject: str = Field(description="Who/What the fact is about (e.g., 'I', 'My girlfriend', 'Sony headphones')")
    predicate: str = Field(description="The relationship/action (e.g., 'bought', 'is angry', 'likes')")
    object: str = Field(description="The target/description (e.g., 'Sony WH-CH520', 'at me', 'black coffee')")
    full_fact: str = Field(description="Complete fact in natural language")

class ProcessedInput(BaseModel):
    """AI-friendly structured output from the semantic router."""
    intent: Literal["REFLEX", "MEMORY_WRITE", "MEMORY_READ", "EXTERNAL"] = Field(
        description="The classification of the user's intent."
    )
    
    # For REFLEX
    instant_reply: Optional[str] = Field(
        description="Instant canned response for REFLEX intents (greetings, thanks, etc.)",
        default=None
    )
    
    # For MEMORY_WRITE
    extracted_facts: List[ExtractedFact] = Field(
        description="List of facts extracted from the input (for MEMORY_WRITE)",
        default_factory=list
    )
    
    # For MEMORY_READ
    search_query: Optional[str] = Field(
        description="Semantic search query to find relevant memories (for MEMORY_READ)",
        default=None
    )
    
    # For EXTERNAL
    external_query: Optional[str] = Field(
        description="Query for external web search (for EXTERNAL)",
        default=None
    )
    
    reasoning: str = Field(description="Explanation of why this intent was chosen")
    confidence: float = Field(description="Confidence score 0.0-1.0", default=1.0)

# --- Processor Class ---

class InputProcessor:
    """
    The 'Real Brain' - Human-like Intent Recognition.
    
    Classifies input into 4 buckets BEFORE processing:
    - REFLEX: Instant social responses (Hi, Thanks, Cool) → No DB lookup
    - MEMORY_WRITE: Personal facts to store (I bought X, My GF is Y) → Extract + Save
    - MEMORY_READ: Questions about stored info (What X do I have?) → Recall + Reason
    - EXTERNAL: General knowledge (Who is the president?) → Web search
    """
    
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables.")
        
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-flash-latest",  # Using stable model
            temperature=0,
            google_api_key=api_key
        )
        self.parser = PydanticOutputParser(pydantic_object=ProcessedInput)

    def process(self, raw_string: str) -> dict:
        """
        Main entry point. Processes raw string and returns structured JSON.
        This is the "Router" - the critical first decision point.
        """
        print(f"🧠 Processing: '{raw_string[:50]}...'")
        
        try:
            return self._classify_and_route(raw_string)
        except Exception as e:
            print(f"❌ Error in Intent Router: {e}")
            # Fallback: treat as MEMORY_READ to be safe (force DB check)
            return {
                "intent": "MEMORY_READ",
                "reasoning": f"System Error: {str(e)}, defaulting to safe mode",
                "search_query": raw_string,
                "confidence": 0.3
            }

    def _classify_and_route(self, text: str) -> dict:
        """
        The 3-Way Split Logic (+ EXTERNAL).
        Uses LLM to classify intent with high precision.
        """
        template = """
You are the Intent Classification Router for an AI that acts like a SMART FRIEND, not a dumb chatbot.

Your job: Classify the user's input into ONE of these intents:

1. **REFLEX** - Instant social responses (NO database needed)
   Examples: "Hi", "Thanks", "Cool", "Okay", "Lol", "Nice"
   → instant_reply: Generate a friendly, casual response
   
2. **MEMORY_WRITE** - User is sharing a PERSONAL fact to remember
   Examples: 
   - "I bought Sony WH-CH520 headphones"
   - "My girlfriend is angry at me"
   - "I like black coffee"
   - "My name is Manuth"
   → extracted_facts: Extract structured facts (subject, predicate, object, full_fact)
   
3. **MEMORY_READ** - User is asking about PERSONAL information
   Examples:
   - "What headphones do I have?"
   - "Why is my girlfriend mad?"
   - "What do I like?"
   - "Who am I?"
   → search_query: Generate semantic search query for vector DB
   
4. **EXTERNAL** - General knowledge question (NOT about the user personally)
   Examples:
   - "Who is the president?"
   - "What's the weather?"
   - "How do I make pasta?"
   - "Who is Elon Musk?"
   → external_query: Clean query for web search

CRITICAL RULES:
- If user says "I [verb] [thing]" or "My [noun] is [state]" → MEMORY_WRITE
- If user asks "What/Who/Why/When [about themselves]" → MEMORY_READ
- If user asks about WORLD FACTS → EXTERNAL
- If it's just social fluff → REFLEX
- NEVER default to REFLEX if there's ANY personal information involved
- For MEMORY_WRITE, extract ALL facts mentioned (can be multiple)

INPUT: {text}

{format_instructions}
"""

        prompt = PromptTemplate(
            template=template,
            input_variables=["text"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

        chain = prompt | self.llm | self.parser
        
        result = chain.invoke({"text": text})
        
        # Convert Pydantic object to dict
        return result.model_dump()

# --- Legacy wrapper for backward compatibility ---
def analyze_text(text, context_subgraph=None):
    """
    Legacy wrapper maintained for any old code that might call it.
    Maps new system to old expected format.
    """
    processor = InputProcessor()
    result = processor.process(text)
    
    # Map to old graph format (just nodes)
    if result.get('extracted_facts'):
        nodes = [fact['subject'] for fact in result['extracted_facts']]
    else:
        nodes = []
    
    return {"nodes": nodes, "edges": []}

if __name__ == "__main__":
    # Quick test suite
    p = InputProcessor()
    
    test_cases = [
        # REFLEX
        ("Hi", "REFLEX"),
        ("Thanks!", "REFLEX"),
        ("Cool", "REFLEX"),
        
        # MEMORY_WRITE
        ("I bought Sony WH-CH520 headphones", "MEMORY_WRITE"),
        ("My girlfriend is angry at me", "MEMORY_WRITE"),
        ("I like black coffee", "MEMORY_WRITE"),
        
        # MEMORY_READ
        ("What headphones do I have?", "MEMORY_READ"),
        ("Why is my girlfriend mad?", "MEMORY_READ"),
        ("What coffee do I like?", "MEMORY_READ"),
        
        # EXTERNAL
        ("Who is the president?", "EXTERNAL"),
        ("What is the weather today?", "EXTERNAL"),
        ("Who is Elon Musk?", "EXTERNAL"),
    ]
    
    print("\n" + "="*80)
    print("INTENT CLASSIFICATION TEST SUITE")
    print("="*80 + "\n")
    
    for text, expected_intent in test_cases:
        result = p.process(text)
        actual_intent = result.get('intent')
        status = "✅" if actual_intent == expected_intent else "❌"
        
        print(f"{status} Input: '{text}'")
        print(f"   Expected: {expected_intent} | Got: {actual_intent}")
        print(f"   Reasoning: {result.get('reasoning')}")
        
        if actual_intent == "MEMORY_WRITE":
            print(f"   Facts: {result.get('extracted_facts')}")
        elif actual_intent == "MEMORY_READ":
            print(f"   Search Query: {result.get('search_query')}")
        elif actual_intent == "EXTERNAL":
            print(f"   External Query: {result.get('external_query')}")
        elif actual_intent == "REFLEX":
            print(f"   Instant Reply: {result.get('instant_reply')}")
        
        print()
