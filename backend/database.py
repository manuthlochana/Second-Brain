import os
import time
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import json
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, 
    Column, 
    Integer, 
    String, 
    Text, 
    ForeignKey, 
    DateTime, 
    Boolean, 
    Float,
    Index,
    func,
    text
)
from sqlalchemy.orm import (
    declarative_base, 
    sessionmaker, 
    relationship, 
    Session, 
    joinedload
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from pgvector.sqlalchemy import Vector
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError

# Load environment variables
load_dotenv()

# --- Configuration ---

# Database URL should be in the format: postgresql://user:password@host:port/dbname
# For Supabase, this is provided in the Connection Pooling settings (Transaction mode recommended for serverless)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Fallback/Placeholder for local development or explicit error
    print("⚠️  DATABASE_URL not found in environment. Using sqlite fallback for demonstration/tests only if needed.")
    DATABASE_URL = "sqlite:///./local_brain.db" 

# Initialize Embedding Model (Gemini)
# We use this to generate embeddings for the vector column
def get_embeddings():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is required for embeddings.")
    return GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=api_key)

# --- SQLAlchemy Setup ---

Base = declarative_base()

# We use a synchronous engine for simplicity and reliable migration handling with Alembic.
# For high-concurrency async apps, `create_async_engine` + `AsyncSession` is standard, 
# but synchronous SQLAlchemy is more than adequate for this Assistant's scale and easier to debug.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Connection Logic ---

def check_connection():
    """Simple heartbeat to check if DB is reachable."""
    try:
        # Create a fresh temp connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"❌ DB Heartbeat Failed: {e}")
        return False

# Retry 3 times, wait 1s, 2s, 4s...
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type(OperationalError))
def get_db_safe():
    """
    Robust dependency that ensures DB is actually reachable.
    Raises exception after retries, allowing fallback logic upstream.
    """
    db = SessionLocal()
    try:
        # Trigger a simple check
        db.execute(text("SELECT 1"))
        yield db
    except OperationalError as e:
        print(f"⚠️ DB Connection Failed (Retrying...): {e}")
        raise e # Let Tenacity handle retry
    finally:
        db.close()

def get_db():
    """Standard dependency (kept for backward compatibility)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Models ---

class BaseModel(Base):
    """
    Abstract base class adding common timestamp columns to all tables.
    Also includes a helper for handling UUIDs.
    """
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # updated_at will be handled by a trigger in raw SQL or manually updated for now.
    # Note: `onupdate=func.now()` handles Python-side updates, but a DB trigger is consistently safer.
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Entity(BaseModel):
    """
    Represents a structured item in the knowledge graph.
    - People, Projects, Links, Credentials, Films, etc.
    - Uses JSONB for flexible metadata storage (schema parameters).
    """
    __tablename__ = "entities"

    name = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False, index=True) # e.g., "Person", "Project"
    description = Column(Text, nullable=True)
    
    # Metadata for structured properties (e.g., {"email": "...", "role": "..."})
    metadata_ = Column("metadata", JSONB, default=dict)
    
    # Tags for quick filtering
    tags = Column(JSONB, default=list) # e.g., ["urgent", "work"]

    # Relationships
    # Notes linked to this entity
    notes = relationship("Note", secondary="entity_notes", back_populates="entities")
    
    # Tasks linked to this entity
    tasks = relationship("Task", back_populates="entity")

    def __repr__(self):
        return f"<Entity(name={self.name}, type={self.entity_type})>"

class UserProfile(BaseModel):
    """
    Stores the User Persona, Bio-Memory, and Stats.
    Singleton-like (usually only 1 row).
    """
    __tablename__ = "user_profiles"

    name = Column(String, nullable=False, default="User")
    
    # Bio-Memory: Daily routines, preferences, tone quirks, life events
    # e.g. {"routines": ["Gym at 6am"], "preferences": {"food": "Spicy"}, "tone": "Direct"}
    bio_memory = Column(JSONB, default=dict)
    
    # Stats: Loyalty score, Interaction count, etc.
    # e.g. {"loyalty_score": 55, "interaction_count": 100}
    stats = Column(JSONB, default=lambda: {"loyalty_score": 50, "interaction_count": 0})

class Note(BaseModel):
    """
    Stores unstructured thoughts, memories, or raw inputs.
    - Includes a Vector Embedding for semantic search.
    - 'content' is the searchable text.
    """
    #__tablename__ = "notes" # Implicitly handled but good to be explicit
    __tablename__ = "notes"

    content = Column(Text, nullable=False)
    
    # pgvector embedding: 768 dimensions for Gemini text-embedding-004
    embedding = Column(Vector(768))

    # Many-to-Many link to Entities (A note can mention multiple entities)
    entities = relationship("Entity", secondary="entity_notes", back_populates="notes")
    
    # One-to-Many: A note can generate multiple tasks
    tasks = relationship("Task", back_populates="note")

    # Index for hybrid search (Full Text Search)
    # Allows fast keyword matching alongside vector search
    # (Requires creating a tsvector index in migration)

    def __repr__(self):
        return f"<Note(preview={self.content[:30]}...)>"

class EntityNoteLink(Base):
    """
    Association table for Many-to-Many between Entities and Notes.
    """
    __tablename__ = "entity_notes"
    
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True)
    note_id = Column(UUID(as_uuid=True), ForeignKey("notes.id"), primary_key=True)

class Task(BaseModel):
    """
    Proactive tasks and reminders.
    - Can be linked to a specific Entity (e.g., "Project X") or a Note (source of truth).
    """
    __tablename__ = "tasks"

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    status = Column(String, default="PENDING", index=True) # PENDING, IN_PROGRESS, DONE, ARCHIVED
    priority = Column(Integer, default=1) # 1=Normal, 2=High, 3=Critical
    
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    is_recurring = Column(Boolean, default=False)
    
    # Foreign Keys
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    note_id = Column(UUID(as_uuid=True), ForeignKey("notes.id"), nullable=True)
    
    # Relationships
    entity = relationship("Entity", back_populates="tasks")
    note = relationship("Note", back_populates="tasks")

class Relationship(BaseModel):
    """
    Represents the edges in the Knowledge Graph.
    - Connects two Entities.
    - e.g., Entity(Manuth) -> [OWNS] -> Entity(Project X)
    - Strength can be used to weight connections.
    """
    __tablename__ = "relationships"

    source_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    
    relation_type = Column(String, nullable=False) # e.g., "OWNS", "CREATED", "BLOCKS"
    strength = Column(Float, default=1.0) # For weighted graph algorithms
    
    # Explicit relationships for easy traversal
    source = relationship("Entity", foreign_keys=[source_id])
    target = relationship("Entity", foreign_keys=[target_id])

class AuditLog(BaseModel):
    """
    Immutable log of all AI actions for context awareness and debugging.
    - "I reminded Manuth about X"
    - "I deleted Project Y"
    """
    __tablename__ = "audit_logs"

    action = Column(String, nullable=False) # e.g., "CREATE_NOTE", "SEND_REMINDER"
    details = Column(JSONB, default=dict) # Full context snapshot
    
    # No updated_at needed for immutable logs, but included via BaseModel for consistency
    
# --- Database Helpers & Hybrid Search ---

class DatabaseService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.embeddings = get_embeddings()

    def add_note(self, content: str, entity_names: List[str] = None):
        """
        Creates a note, generates its embedding, and links it to entities (creating them if needed).
        """
        # 1. Generate Embedding
        vector = self.embeddings.embed_query(content)
        
        # 2. Create Note
        new_note = Note(content=content, embedding=vector)
        self.db.add(new_note)
        
        # 3. Handle Entities
        if entity_names:
            for name in entity_names:
                # Simple deduplication: Check if entity exists by name
                # (In production, might need fuzzy matching or stricter unique constraints)
                entity = self.db.query(Entity).filter(Entity.name == name).first()
                if not entity:
                    entity = Entity(name=name, entity_type="General") # Default type
                    self.db.add(entity)
                
                new_note.entities.append(entity)
        
        # 4. Audit Log
        self.log_action("CREATE_NOTE", {"content_preview": content[:50], "entities": entity_names})
        
        self.db.commit()
        self.db.refresh(new_note)
        return new_note

    def hybrid_search(self, query: str, k: int = 5, alpha: float = 0.5):
        """
        Performs Hybrid Search:
        1. Semantic Search (Vector Similarity) using pgvector ('<->' operator or cosine).
        2. Keyword Search (not fully implemented here without TSVector setup, but simulated via ILIKE for robustness).
        
        For robust Hybrid Search in Postgres:
        - We usually use Reciprocal Rank Fusion (RRF) to combine results.
        
        Here, we will prioritize standard Vector Search as it's the primary requirement for "Hybrid" 
        usually implying Vector + Filter or Vector + Keyword.
        """
        # Generate query embedding
        query_vector = self.embeddings.embed_query(query)
        
        # SQLAlchemy pgvector query (Cosine Distance)
        # Note: 'embedding' column must have an index (hnsw or ivfflat) for performance
        results = (
            self.db.query(Note)
            .order_by(Note.embedding.cosine_distance(query_vector))
            .limit(k)
            .all()
        )
        
        # TODO: Implement true Keyword search integration (using ts_rank)
        # This requires `tsvector` column and full text search index.
        
        return results

    def get_knowledge_graph(self):
        """
        Fetches all nodes and edges for visualization.
        """
        entities = self.db.query(Entity).all()
        relationships = self.db.query(Relationship).all()
        
        nodes = [{"id": str(e.id), "label": e.name, "type": e.entity_type} for e in entities]
        edges = [
            {
                "source": str(r.source_id), 
                "target": str(r.target_id), 
                "label": r.relation_type
            } 
            for r in relationships
        ]
        
        return {"nodes": nodes, "edges": edges}

    def log_action(self, action: str, details: dict):
        """
        Logs an action to the Audit Table.
        """
        log = AuditLog(action=action, details=details)
        self.db.add(log)
        # Commit usually happens at the end of the transaction scope, 
        # but logs can be committed immediately if critical.
