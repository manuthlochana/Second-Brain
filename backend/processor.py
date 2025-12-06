import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
import json

# Load environment variables
load_dotenv()

def get_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ GOOGLE_API_KEY not found in environment variables.")
        return None
    
    return ChatGoogleGenerativeAI(
        model="gemini-flash-latest", 
        temperature=0,
        google_api_key=api_key
    )

def analyze_text(text, existing_nodes=None):
    """
    Analyzes text to extract entities (nodes) and relationships (edges).
    Returns a JSON object with 'nodes' and 'edges'.
    """
    
    llm = get_llm()
    if not llm:
        return {"nodes": [], "edges": []}

    existing_nodes_str = ", ".join(existing_nodes) if existing_nodes else "None"

    # UPDATED PROMPT TO ENFORCE LIST FORMAT
    template = """
    You are the Keeper of Manuth's Second Brain.
    Structure thoughts into a Hierarchical Graph.
    
    RULES:
    ROOT: "Manuth".
    CATEGORIES: Relations, Ideas, Own, Buying List, Knowledge.

    EXISTING NODES:
    {existing_nodes}

    CRITICAL LOGIC FOR POSSESSIONS:
    If an item belongs to "Manuth", link: Manuth -> Own -> Item.
    IF AN ITEM BELONGS TO SOMEONE ELSE (e.g., "Adeesha has a Samsung Phone"):
    First, link the Person to Manuth: Manuth -> Relations -> "Adeesha".
    Then, link the Item to THAT PERSON: "Adeesha" -> OWNS -> "Samsung Phone".

    SMART LINKING:
    Check the 'EXISTING NODES' list above.
    If a mentioned entity matches or is very similar to an existing node, reuse that EXACT name to ensure connection.
    Do not create duplicates. (e.g., if "Samsung A06" exists, use "Samsung A06" instead of "Phone").

    IMPORTANT OUTPUT FORMAT:
    You must return a valid JSON object.
    - 'nodes': A list of strings.
    - 'edges': A list of lists, where each list is strictly ["Source", "Relation", "Target"].

    Example Output:
    {{
      "nodes": ["Manuth", "Own", "Bike"],
      "edges": [
        ["Manuth", "HAS_CATEGORY", "Own"],
        ["Own", "CONTAINS", "Bike"]
      ]
    }}

    Input Text: {text} 
    Return ONLY the JSON string. Do not add Markdown formatting.
    """
    
    prompt = PromptTemplate(template=template, input_variables=["text", "existing_nodes"])
    chain = prompt | llm
    
    try:
        response = chain.invoke({"text": text, "existing_nodes": existing_nodes_str})
        # Clean up response if it contains markdown formatting
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
            
        return json.loads(content)
    except Exception as e:
        print(f"Error processing text: {e}")
        return {"nodes": [], "edges": []}

if __name__ == "__main__":
    # Test with a sample sentence
    sample_text = "Elon Musk started SpaceX."
    print(f"Analyzing: '{sample_text}'")
    
    result = analyze_text(sample_text)
    print("\\nExtracted Data:")
    print(json.dumps(result, indent=2))
