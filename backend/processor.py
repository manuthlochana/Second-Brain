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

class Entity(BaseModel):
    name: str = Field(description="Name of the entity (e.g., 'Manuth', 'SpaceX')")
    entity_type: str = Field(description="Type of entity (e.g., 'Person', 'Organization', 'Date', 'URL', 'Value')")
    confidence: float = Field(description="Confidence score (0.0 to 1.0)")

class ProcessedInput(BaseModel):
    intent: Literal["STORE_NOTE", "CREATE_TASK", "SEARCH_MEMORY", "GET_CREDENTIALS", "UNKNOWN"] = Field(
        description="The classification of the user's intent."
    )
    entities: List[Entity] = Field(description="List of entities extracted from the input.")
    dates_times: Optional[List[str]] = Field(description="Extracted dates or times strings for reminders.")
    urls: Optional[List[str]] = Field(description="Extracted URLs.")
    values: Optional[List[str]] = Field(description="Extracted numerical values or distinct identifiers (e.g. account numbers).")
    priority: int = Field(description="Priority level from 1 (Low) to 5 (Critical). Default is 1.", default=1)
    reasoning: str = Field(description="Explanation of why this intent and data were chosen.")
    response_if_unknown: Optional[str] = Field(description="A clarification question if intent is UNKNOWN.")
    keywords_for_mindmap: List[str] = Field(description="Keywords to creation relationships in the mindmap.")

# --- Processor Class ---

class InputProcessor:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables.")
        
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-flash-latest", 
            temperature=0,
            google_api_key=api_key
        )
        self.parser = PydanticOutputParser(pydantic_object=ProcessedInput)

    def process(self, raw_string: str) -> dict:
        """
        Main entry point. Processes raw string and returns structured JSON.
        """
        print(f"🧠 Processing: '{raw_string[:50]}...'")
        
        try:
            return self._classify_and_extract(raw_string)
        except Exception as e:
            print(f"❌ Error in Semantic Router: {e}")
            # Fallback for critical failures
            return {
                "intent": "UNKNOWN",
                "reasoning": f"System Error: {str(e)}",
                "entities": [],
                "priority": 1,
                "keywords_for_mindmap": []
            }

    def _classify_and_extract(self, text: str) -> dict:
        template = """
        You are the Semantic Router for a high-performance database-backed AI Assistant (CEO Brain).
        Your job is to analyze raw user input and output a STRICT JSON object matching the provided schema.

        INTENT DEFINITIONS:
        - STORE_NOTE: Converting thoughts, facts, or random ideas into long-term memory.
        - CREATE_TASK: Actionable items (e.g., "Remind me", "I need to", "Buy milk").
        - SEARCH_MEMORY: Asking questions about the past or stored knowledge.
        - GET_CREDENTIALS: Explicit requests for secure data (e.g., "What is my bank account?").
        - UNKNOWN: Inputs that are ambiguous, incomplete, or nonsensical.

        RULES:
        1. "Evolution" Logic: If UNKNOWN, you MUST formulate a polite clarification question in 'response_if_unknown' (mixed English/Sinhala/Casual tone is okay if appropriate, but keep it professional).
        2. Priority: Infer priority from urgency words ("ASAP", "Emergency", "Now").
        3. Mindmap: keywords_for_mindmap should be nouns or semantic anchors.
        
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

# --- Legacy wrapper for backward compatibility if needed ---
def analyze_text(text, context_subgraph=None):
    """
    Legacy wrapper. In a full refactor, this should be removed.
    For now, we map the new processor output to the old expected format 
    if strictly necessary, BUT the new requirement says 'return a structured JSON object'.
    So we'll just use the new processor.
    """
    processor = InputProcessor()
    result = processor.process(text)
    
    # Map to old graph format for simple compatibility if legacy code calls it
    # This is a loose approximation to prevent crashes if something still calls analyze_text
    nodes = [e['name'] for e in result.get('entities', [])]
    # Edges are hard to infer without the specific graph prompt, but we do our best 
    # or just return nodes.
    return {"nodes": nodes, "edges": []} 

if __name__ == "__main__":
    # Test
    p = InputProcessor()
    
    test_inputs = [
        "Remind me to call functionality at 5pm",
        "Save my HNB bank account details: 123456789",
        "Who is certain Manuth?",
        "shabalabadingdong"
    ]
    
    for txt in test_inputs:
        print("\nInput:", txt)
        res = p.process(txt)
        print(json.dumps(res, indent=2))
