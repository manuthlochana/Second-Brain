import os
import json
from typing import List, Dict, Any, Optional
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

import database
from contextlib import contextmanager

# Load environment variables
load_dotenv()

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

class GraphEngine:
    def __init__(self):
        self.llm = get_llm()

    def get_full_graph(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches all nodes and edges for visualization (react-force-graph compatible).
        """
        print("🕸️ Graph Engine: Fetching full graph...")
        with get_db_session() as session:
            # 1. Fetch Nodes (Entities & Notes treated as nodes)
            entities = session.execute(select(database.Entity)).scalars().all()
            notes = session.execute(select(database.Note).limit(100)).scalars().all() # Limit notes to prevent clutter
            
            nodes = []
            for e in entities:
                nodes.append({
                    "id": str(e.id),
                    "label": e.name,
                    "type": e.entity_type,
                    "val": 5 # Size
                })
            
            # Treat Notes as smaller nodes if needed, or specific Note Entities
            for n in notes:
                nodes.append({
                    "id": str(n.id),
                    "label": n.content[:20] + "...",
                    "type": "Note",
                    "val": 2,
                    "full_text": n.content
                })

            # 2. Fetch Edges (Relationships)
            # Standard relationships
            relationships = session.execute(select(database.Relationship)).scalars().all()
            edges = []
            for r in relationships:
                edges.append({
                    "source": str(r.source_id),
                    "target": str(r.target_id),
                    "label": r.relation_type,
                    "weight": r.strength
                })
            
            # Explicit Entity-Note links (if stored in association table, we need to query it)
            # Using the `entity_notes` table via SQLAlchemy relationship is tricky without eager loading or explicit query
            # For visualization, we skip Note-Entity links here to keep it clean unless requested, 
            # OR we can iterate notes and their entities if joinedload is used.
            # Simplified: Focusing on Entity-Entity relationships for the Mindmap.
            
            return {"nodes": nodes, "links": edges}

    def get_subgraph(self, entity_id: str, depth: int = 1) -> Dict[str, Any]:
        """
        Fetches a localized graph around a specific entity.
        """
        # Placeholder for complex traversal.
        # For now, just returns direct neighbors.
        # Implementation would involve recursive CTEs or iterative Python queries.
        return self.get_full_graph() # Fallback

    def link_entity(self, entity_id: str, entity_name: str, description: str):
        """
        Autonomously discovers and creates relationships for a specific entity
        using Vector Search + LLM classification.
        """
        print(f"🔗 Graph Engine: Auto-linking '{entity_name}'...")
        with get_db_session() as session:
            # 1. Semantic Search using new Memory Manager
            import memory_manager
            search_query = f"{entity_name} {description}"
            # We use the internal search logic to get Note IDs first
            matches = memory_manager.memory_manager.vector_store.search_memory(query=search_query, top_k=5)
            note_ids = [m['metadata'].get('note_id') for m in matches if m['metadata'].get('note_id')]
            
            relevant_notes = []
            if note_ids:
                relevant_notes = session.execute(
                    select(database.Note).where(database.Note.id.in_(note_ids))
                ).scalars().all()
            
            # Collect potential target entities from these notes
            candidate_entities = set()
            for note in relevant_notes:
                for linked_entity in note.entities:
                    if str(linked_entity.id) != entity_id:
                        candidate_entities.add(linked_entity)
            
            if not candidate_entities:
                print("   - No candidates found.")
                return

            # 2. LLM Classification for each candidate
            new_relationships = []
            
            template = """
            Analyze the relationship between two entities.
            
            Entity A: {name_a} ({desc_a})
            Entity B: {name_b} ({desc_b})
            
            Determine the relationship type.
            Options: PART_OF, RELATED_TO, REQUISITE_FOR, FINANCIAL_IMPACT, OWNER_OF, MEMBER_OF, BLOCKS.
            If no strong relationship, return "NONE".
            
            Output strictly the relationship type.
            """
            prompt = PromptTemplate(template=template, input_variables=["name_a", "desc_a", "name_b", "desc_b"])
            chain = prompt | self.llm
            
            for candidate in candidate_entities:
                response = chain.invoke({
                    "name_a": entity_name,
                    "desc_a": description or "No description",
                    "name_b": candidate.name,
                    "desc_b": candidate.description or "No description"
                })
                
                relation_type = response.content.strip().upper()
                
                if relation_type != "NONE":
                    print(f"   - Found Link: {entity_name} --[{relation_type}]--> {candidate.name}")
                    
                    # Store Relationship
                    # Check existing?
                    rel = database.Relationship(
                        source_id=entity_id, # UUID provided as str, sqlalchemy handles casting usually if type is UUID
                        target_id=candidate.id,
                        relation_type=relation_type,
                        strength=0.8
                    )
                    session.add(rel)
                    new_relationships.append(rel)
            
            session.commit()
            print(f"   ✅ Created {len(new_relationships)} new links.")

    def run_inference(self):
        """
        Analyzes the graph to find clusters or missing high-level concepts.
        Placeholder implementation.
        """
        print("🧠 Graph Engine: Running Semantic Inference...")
        # 1. Community Detection (NetworkX) or LLM analysis of recent nodes
        # 2. Suggest new Project entities
        print("   - (Inference logic placeholder)")

# --- Singleton ---
graph_engine = GraphEngine()
