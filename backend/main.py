from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import processor
import database

# Load environment variables
load_dotenv()

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")

llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key)

# Pydantic Models
class ChatRequest(BaseModel):
    message: str

class InsertRequest(BaseModel):
    text: str

# Endpoints

import brain

# ... (keep existing imports and setup)

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # Process the thought through the LangGraph Brain
        result = brain.process_thought(request.message)
        
        return {
            "answer": result["final_answer"],
            "context": result.get("memory_context") or result.get("web_context") or ""
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Removed /insert endpoint as it is now handled by the brain's intent classification

@app.get("/graph")
async def get_graph():
    try:
        driver = database.get_neo4j_driver()
        if not driver:
            return {"nodes": [], "links": []}
            
        nodes = []
        links = []
        node_ids = set()
        
        with driver.session() as session:
            # Use OPTIONAL MATCH to get all nodes, even those without relationships
            result = session.run("MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100")
            
            for record in result:
                source = record["n"]
                relation = record["r"]
                target = record["m"]
                
                source_id = source.element_id if hasattr(source, 'element_id') else str(source.id)
                source_name = source.get("name", "Unknown")
                
                if source_id not in node_ids:
                    nodes.append({"id": source_id, "name": source_name, "val": 1})
                    node_ids.add(source_id)
                
                # If there is a relationship, process target and link
                if relation is not None and target is not None:
                    target_id = target.element_id if hasattr(target, 'element_id') else str(target.id)
                    target_name = target.get("name", "Unknown")
                    
                    if target_id not in node_ids:
                        nodes.append({"id": target_id, "name": target_name, "val": 1})
                        node_ids.add(target_id)
                        
                    links.append({
                        "source": source_id,
                        "target": target_id,
                        "label": relation.type
                    })
                
        return {"nodes": nodes, "links": links}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'driver' in locals() and driver:
            driver.close()
