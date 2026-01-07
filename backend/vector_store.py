import os
import logging
from typing import List, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Load environment variables
load_dotenv()

# Setup logging
logger = logging.getLogger("CEO_BRAIN.vector_store")

class VectorStore:
    """
    Pinecone Vector Store for Memory Management.
    
    Handles all vector embedding operations:
    - Save memories with embeddings
    - Search for relevant context
    - Batch operations
    
    Uses:
    - Pinecone for vector storage (768-dim Gemini embeddings)
    - Index name: "quickstart"
    """
    
    def __init__(self):
        """Initialize Pinecone connection and embedding model."""
        # Get API keys
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        google_api_key = os.getenv("GOOGLE_API_KEY")
        
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=pinecone_api_key)
        
        # Connect to index
        index_name = "quickstart"
        
        try:
            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            index_names = [idx['name'] for idx in existing_indexes]
            
            if index_name not in index_names:
                logger.warning(f"Index '{index_name}' not found. Creating it...")
                # Create index with 768 dimensions (Gemini text-embedding-004)
                self.pc.create_index(
                    name=index_name,
                    dimension=768,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
                logger.info(f"✅ Created index '{index_name}'")
            
            self.index = self.pc.Index(index_name)
            logger.info(f"✅ Connected to Pinecone index: {index_name}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            raise
        
        # Initialize embeddings model (768 dimensions)
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=google_api_key
        )
        logger.info("✅ Initialized Gemini embeddings (768-dim)")
    
    def save_memory(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        vector_id: Optional[str] = None
    ) -> str:
        """
        Save a memory to Pinecone with embeddings.
        
        Args:
            text: The text content to embed and store
            metadata: Additional metadata to store with the vector
            vector_id: Optional custom ID (generates UUID if not provided)
        
        Returns:
            The vector ID that was stored
        """
        try:
            # Generate embedding
            logger.debug(f"Generating embedding for: '{text[:50]}...'")
            embedding = self.embeddings.embed_query(text)
            
            # Ensure vector_id is a string (important for Pinecone)
            if vector_id:
                vector_id = str(vector_id)
            else:
                vector_id = str(uuid4())
            
            # Prepare metadata
            if metadata is None:
                metadata = {}
            
            # Sanitize metadata: Pinecone only accepts str, int, float, bool, or list of str
            sanitized_metadata = {}
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    sanitized_metadata[k] = v
                elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                    sanitized_metadata[k] = v
                else:
                    # Convert everything else (UUID, datetime, etc) to string
                    sanitized_metadata[k] = str(v)
            
            # Add default fields
            sanitized_metadata['text'] = text
            sanitized_metadata['created_at'] = datetime.now().isoformat()
            
            # Upsert to Pinecone
            self.index.upsert(
                vectors=[(vector_id, embedding, sanitized_metadata)],
                namespace=""
            )
            
            logger.info(f"✅ Saved memory: {vector_id}")
            return vector_id
            
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            raise
    
    def search_memory(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        namespace: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant memories in Pinecone.
        
        Args:
            query: The search query
            top_k: Number of results to return
            filter: Optional metadata filter
            namespace: Pinecone namespace to search
        
        Returns:
            List of matches with scores and metadata
        """
        try:
            logger.debug(f"Searching for: '{query[:50]}...'")
            
            # Generate query embedding
            query_embedding = self.embeddings.embed_query(query)
            
            # Search Pinecone
            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=filter,
                namespace=namespace
            )
            
            # Format results
            matches = []
            for match in results.get('matches', []):
                matches.append({
                    'id': match['id'],
                    'score': match['score'],
                    'metadata': match.get('metadata', {}),
                    'text': match.get('metadata', {}).get('text', '')
                })
            
            logger.info(f"✅ Found {len(matches)} memories (scores: {[f'{m['score']:.3f}' for m in matches[:3]]})")
            return matches
            
        except Exception as e:
            logger.error(f"Failed to search memory: {e}")
            return []
    
    def batch_save_memories(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """
        Save multiple memories in a batch operation.
        
        Args:
            texts: List of text contents
            metadatas: Optional list of metadata dicts (same length as texts)
        
        Returns:
            List of vector IDs that were stored
        """
        try:
            if metadatas and len(metadatas) != len(texts):
                raise ValueError("metadatas must be same length as texts")
            
            # Generate embeddings for all texts
            logger.info(f"Batch generating {len(texts)} embeddings...")
            embeddings = self.embeddings.embed_documents(texts)
            
            # Prepare vectors for upsert
            vectors = []
            vector_ids = []
            
            for idx, (text, embedding) in enumerate(zip(texts, embeddings)):
                vector_id = str(uuid4())
                vector_ids.append(vector_id)
                
                metadata = metadatas[idx] if metadatas else {}
                metadata['text'] = text
                metadata['created_at'] = datetime.now().isoformat()
                
                vectors.append((vector_id, embedding, metadata))
            
            # Batch upsert
            self.index.upsert(vectors=vectors, namespace="")
            
            logger.info(f"✅ Batch saved {len(vector_ids)} memories")
            return vector_ids
            
        except Exception as e:
            logger.error(f"Failed to batch save memories: {e}")
            raise
    
    def delete_memory(self, vector_id: str, namespace: str = "") -> bool:
        """
        Delete a memory from Pinecone.
        
        Args:
            vector_id: The ID of the vector to delete
            namespace: Pinecone namespace
        
        Returns:
            True if successful
        """
        try:
            self.index.delete(ids=[vector_id], namespace=namespace)
            logger.info(f"✅ Deleted memory: {vector_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        try:
            stats = self.index.describe_index_stats()
            return {
                'total_vectors': stats.get('total_vector_count', 0),
                'dimension': stats.get('dimension', 0),
                'index_fullness': stats.get('index_fullness', 0)
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

# Global singleton instance
_vector_store = None

def get_vector_store() -> VectorStore:
    """Get or create the global VectorStore instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store

if __name__ == "__main__":
    # Quick test
    print("\n" + "="*80)
    print("PINECONE VECTOR STORE TEST")
    print("="*80 + "\n")
    
    try:
        vs = get_vector_store()
        
        # Get stats
        stats = vs.get_stats()
        print(f"📊 Index Stats: {stats}\n")
        
        # Test save
        print("💾 Testing save_memory...")
        vector_id = vs.save_memory(
            text="I bought Sony WH-CH520 headphones",
            metadata={"user_id": "test_user", "category": "purchase"}
        )
        print(f"   ✅ Saved with ID: {vector_id}\n")
        
        # Test search
        print("🔍 Testing search_memory...")
        results = vs.search_memory("What headphones do I have?", top_k=3)
        for idx, result in enumerate(results, 1):
            print(f"   {idx}. Score: {result['score']:.3f} | Text: {result['text']}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
