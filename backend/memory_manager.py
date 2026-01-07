import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

from vector_store import get_vector_store
import database
from contextlib import contextmanager

load_dotenv()

# Setup logging
logger = logging.getLogger("CEO_BRAIN.memory_manager")

@contextmanager
def get_db_session():
    """Yields a DB session for Supabase (structured data only)."""
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
    """
    Memory Manager using Pinecone for vectors + Supabase for structured data.
    
    Architecture:
    - Pinecone: Vector embeddings (semantic search)
    - Supabase: Structured data (Note text, timestamps, entities)
    
    Flow:
    - save_memory() → Save to both Pinecone (embedding) + Supabase (text)
    - search_memory() → Query Pinecone → Fetch full notes from Supabase
    """
    
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY Missing")
        
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-flash-latest", 
            temperature=0, 
            google_api_key=self.api_key
        )
        
        # Initialize Pinecone vector store
        self.vector_store = get_vector_store()
        logger.info("✅ MemoryManager initialized with Pinecone")

    def save_memory(
        self, 
        text: str, 
        user_id: str, 
        entities: List[str] = None
    ) -> Dict[str, str]:
        """
        Save a memory to both Pinecone (vector) and Supabase (structured).
        
        Args:
            text: The memory content
            user_id: User ID
            entities: Optional list of entity names to link
        
        Returns:
            Dict with note_id and vector_id
        """
        try:
            logger.info(f"💾 Saving memory: '{text[:50]}...'")
            
            # 1. Save to Supabase (structured data)
            with get_db_session() as session:
                service = database.DatabaseService(session)
                note = service.add_note(text, entities or [])
                note_id = str(note.id)
                created_at = note.created_at
            
            logger.debug(f"   ✅ Saved to Supabase: {note_id}")
            
            # 2. Save to Pinecone (vector embedding)
            vector_id = self.vector_store.save_memory(
                text=text,
                metadata={
                    "note_id": note_id,
                    "user_id": user_id,
                    "timestamp": created_at.isoformat() if created_at else datetime.now().isoformat(),
                    "entities": entities or []
                },
                vector_id=note_id  # Use same ID for easy lookup
            )
            
            logger.info(f"   ✅ Saved to Pinecone: {vector_id}")
            
            return {
                "note_id": note_id,
                "vector_id": vector_id
            }
            
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            raise

    def search_memory(
        self, 
        query: str, 
        user_id: Optional[str] = None,
        top_k: int = 5
    ) -> str:
        """
        Search for relevant memories using Pinecone + Supabase.
        
        Flow:
        1. Query Pinecone for semantic matches
        2. Fetch full Note objects from Supabase
        3. Apply time-based scoring
        4. Format as context string
        
        Args:
            query: Search query
            user_id: Optional user ID filter
            top_k: Number of results
        
        Returns:
            Formatted context string
        """
        try:
            logger.info(f"🔍 Searching memory: '{query[:50]}...'")
            
            # 1. Search Pinecone
            filter_dict = {"user_id": user_id} if user_id else None
            matches = self.vector_store.search_memory(
                query=query,
                top_k=top_k * 2,  # Get more to allow for time-based filtering
                filter=filter_dict
            )
            
            if not matches:
                logger.info("   No matches found")
                return ""
            
            # 2. Fetch full notes from Supabase
            note_ids = [m['metadata'].get('note_id') for m in matches if m['metadata'].get('note_id')]
            
            notes_dict = {}
            if note_ids:
                with get_db_session() as session:
                    from sqlalchemy import select
                    notes = session.execute(
                        select(database.Note).where(database.Note.id.in_(note_ids))
                    ).scalars().all()
                    
                    # Map by ID for easy lookup
                    notes_dict = {str(note.id): note for note in notes}
            
            # 3. Score and format results
            scored_results = []
            for match in matches:
                note_id = match['metadata'].get('note_id')
                if not note_id or note_id not in notes_dict:
                    continue
                
                note = notes_dict[note_id]
                vector_score = match['score']
                
                # Time decay scoring
                created_at = note.created_at
                if created_at:
                    age_days = (datetime.now() - created_at.replace(tzinfo=None)).days
                else:
                    age_days = 365
                
                time_decay = 1 / (1 + age_days * 0.1)
                
                # Combined score (70% vector similarity, 30% time decay)
                final_score = (vector_score * 0.7) + (time_decay * 0.3)
                
                scored_results.append({
                    'score': final_score,
                    'note': note,
                    'vector_score': vector_score,
                    'time_decay': time_decay
                })
            
            # 4. Sort by final score and take top_k
            scored_results.sort(key=lambda x: x['score'], reverse=True)
            top_results = scored_results[:top_k]
            
            # 5. Format as context string
            context_parts = []
            for result in top_results:
                note = result['note']
                date_str = note.created_at.strftime("%Y-%m-%d") if note.created_at else "Unknown"
                score = result['score']
                
                context_parts.append(
                    f"[{date_str}] {note.content} (Relevance: {score:.2f})"
                )
            
            full_context = "\n".join(context_parts)
            
            logger.info(f"   ✅ Found {len(top_results)} relevant memories")
            
            # 6. Compress if too long
            if len(full_context) > 2000:
                return self.compress_context(full_context)
            
            return full_context
            
        except Exception as e:
            logger.error(f"Failed to search memory: {e}")
            return ""

    def compress_context(self, text: str) -> str:
        """
        Uses LLM to summarize extensive context.
        """
        logger.debug("   Compressing context...")
        try:
            prompt = PromptTemplate.from_template(
                "Summarize these memory fragments into a concise brief:\n\n{text}"
            )
            chain = prompt | self.llm
            res = chain.invoke({"text": text})
            return res.content
        except Exception as e:
            logger.error(f"Failed to compress context: {e}")
            # Return truncated version if compression fails
            return text[:2000] + "..."

    def retrieve_context(self, query: str, user_id: Optional[str] = None) -> str:
        """
        Alias for search_memory() for backward compatibility.
        """
        return self.search_memory(query, user_id)

    def delete_memory(self, note_id: str) -> bool:
        """
        Delete a memory from both Pinecone and Supabase.
        
        Args:
            note_id: The note ID to delete
        
        Returns:
            True if successful
        """
        try:
            # Delete from Pinecone
            self.vector_store.delete_memory(note_id)
            
            # Delete from Supabase
            with get_db_session() as session:
                note = session.query(database.Note).filter(database.Note.id == note_id).first()
                if note:
                    session.delete(note)
                    session.commit()
            
            logger.info(f"✅ Deleted memory: {note_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False

# Global singleton
memory_manager = MemoryManager()

if __name__ == "__main__":
    # Quick test
    print("\n" + "="*80)
    print("MEMORY MANAGER TEST")
    print("="*80 + "\n")
    
    try:
        # Test save
        print("💾 Testing save_memory...")
        result = memory_manager.save_memory(
            text="I bought Sony WH-CH520 headphones last week",
            user_id="test_user",
            entities=["Sony WH-CH520"]
        )
        print(f"   ✅ Saved: {result}\n")
        
        # Test search
        print("🔍 Testing search_memory...")
        context = memory_manager.search_memory(
            query="What headphones do I have?",
            user_id="test_user"
        )
        print(f"   Context:\n{context}\n")
        
        print("✅ All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
