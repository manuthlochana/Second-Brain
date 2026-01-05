import os
import math
from datetime import datetime
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from sqlalchemy import select
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

import database
from contextlib import contextmanager

load_dotenv()

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

class MemoryManager:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY Missing")
        self.llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0, google_api_key=self.api_key)

    def _calculate_score(self, vector_score: float, created_at: datetime) -> float:
        """
        Retrieval Score = (Vector Similarity * 0.7) + (Time Decay * 0.3)
        Time Decay = 1 / (1 + age_in_days)
        """
        if not created_at:
            age_days = 365 # Default old
        else:
            age_days = (datetime.now() - created_at).days
            if age_days < 0: age_days = 0
            
        time_decay = 1 / (1 + age_days * 0.1) # Soft decay
        
        # Simple Weighted Average
        # Assuming vector_score is cosine similarity (0-1)
        final = (vector_score * 0.7) + (time_decay * 0.3)
        return final

    def retrieve_context(self, query: str, user_id: str = None) -> str:
        """
        Retrieves relevant context using Hybrid Retrieval + Scoring.
        """
        print(f"🧠 Deep Memory: Searching for '{query}'...")
        contexts = []
        
        with get_db_session() as session:
            service = database.DatabaseService(session)
            
            # 1. Vector Search (Raw)
            # hybrid_search returns Note objects, but we need distance/score.
            # database.py hybrid_search uses l2_distance or cosine depending on implementation.
            # Assuming it returns closest items.
            results = service.hybrid_search(query, k=10)
            
            scored_results = []
            
            for note in results:
                # Mock vector score (Since logic is hidden in DB service or using raw search)
                # Ideally, we get distance from pgvector query.
                # Here we simulate high relevance for top results.
                # TODO: Retrieve actual distance/similarity from sqlalchemy query
                vec_score = 0.9 # Placeholder
                
                final_score = self._calculate_score(vec_score, note.created_at)
                scored_results.append((final_score, note))
                
            # 2. Sort by Final Score
            scored_results.sort(key=lambda x: x[0], reverse=True)
            
            # 3. Format Output
            top_k = scored_results[:5]
            for score, note in top_k:
                date_str = note.created_at.strftime("%Y-%m-%d") if note.created_at else "Unknown"
                contexts.append(f"[{date_str}] {note.content} (Relevance: {score:.2f})")
                
        # 4. Summarization (if too long)
        full_text = "\n".join(contexts)
        if len(full_text) > 2000:
             return self.compress_context(full_text)
             
        return full_text

    def compress_context(self, text: str) -> str:
        """
        Uses LLM to summarize extensive context.
        """
        print("   - Compressing context...")
        prompt = PromptTemplate.from_template("Summarize these memory fragments into a concise brief:\n\n{text}")
        chain = prompt | self.llm
        res = chain.invoke({"text": text})
        return res.content

    def generate_flashback(self, entity_name: str) -> str:
        """
        Retrieves dedicated entity sub-graph + recent notes.
        """
        return self.retrieve_context(f"Everything about {entity_name}")

memory_manager = MemoryManager()
