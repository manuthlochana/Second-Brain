import os
import time
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pinecone import Pinecone
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Load environment variables
load_dotenv()

# Initialize Embedding Model
def get_embeddings():
    api_key = os.getenv("GOOGLE_API_KEY")
    return GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=api_key)

def get_neo4j_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    
    if not all([uri, user, password]):
        print("❌ Neo4j credentials missing.")
        return None
        
    try:
        return GraphDatabase.driver(uri, auth=(user, password))
    except Exception as e:
        print(f"❌ Failed to create driver: {e}")
        return None

def find_similar_nodes(query: str) -> list[str]:
    """
    Searches Neo4j for nodes that might be relevant to the user's input.
    Uses a simple case-insensitive CONTAINS search on the 'name' property.
    """
    print(f"🔍 Searching for similar nodes to: '{query}'")
    driver = get_neo4j_driver()
    if not driver:
        return []

    found_nodes = set()
    
    # Split query into words and filter out short words/stopwords
    words = [w for w in query.split() if len(w) > 3]
    
    if not words:
        return []

    try:
        with driver.session() as session:
            for word in words:
                # Cypher query to find nodes containing the word (case-insensitive)
                # We limit to 5 matches per word to avoid context flooding
                cypher = """
                MATCH (n:Entity)
                WHERE toLower(n.name) CONTAINS toLower($word)
                RETURN n.name AS name LIMIT 5
                """
                result = session.run(cypher, word=word)
                for record in result:
                    found_nodes.add(record["name"])
                    
        print(f"✅ Found {len(found_nodes)} similar nodes: {list(found_nodes)}")
        return list(found_nodes)
        
    except Exception as e:
        print(f"❌ Error searching for nodes: {e}")
        return []
    finally:
        driver.close()

def save_node_embedding(node_name):
    """
    Embeds the node name and saves it to Pinecone with id=node_name.
    This allows us to find nodes by semantic similarity.
    """
    print(f"Saving Node Embedding: '{node_name}'")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        return

    try:
        embeddings = get_embeddings()
        vector = embeddings.embed_query(node_name)
        
        pc = Pinecone(api_key=pinecone_api_key)
        indexes = pc.list_indexes()
        index_names = [i.name for i in indexes] if hasattr(indexes, 'names') else [i['name'] for i in indexes] if isinstance(indexes, list) else indexes
        
        if not index_names:
            return
            
        index = pc.Index(index_names[0])
        
        # Upsert with ID = Node Name
        index.upsert(
            vectors=[
                {
                    "id": node_name, # Key difference: ID is the node name itself
                    "values": vector,
                    "metadata": {"type": "node", "text": node_name}
                }
            ]
        )
        print(f"✅ Node embedding saved for '{node_name}'")
        
    except Exception as e:
        print(f"❌ Error saving node embedding: {e}")

def get_context_subgraph(query_text: str) -> str:
    """
    GraphRAG:
    1. Vector Search Pinecone for similar nodes.
    2. Fetch subgraph (Node + 1-hop neighbors) from Neo4j.
    3. Return natural language summary.
    """
    print(f"🕸️ GraphRAG: Retrieving context for '{query_text}'")
    
    # Step A: Vector Search
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        return ""
        
    matched_nodes = []
    try:
        embeddings = get_embeddings()
        vector = embeddings.embed_query(query_text)
        
        pc = Pinecone(api_key=pinecone_api_key)
        indexes = pc.list_indexes()
        index_names = [i.name for i in indexes] if hasattr(indexes, 'names') else [i['name'] for i in indexes] if isinstance(indexes, list) else indexes
        
        if index_names:
            index = pc.Index(index_names[0])
            results = index.query(vector=vector, top_k=3, include_metadata=True)
            
            for match in results.matches:
                # We assume ID is the node name (from save_node_embedding)
                # Or we can use metadata['text']
                node_name = match.id
                matched_nodes.append(node_name)
                
    except Exception as e:
        print(f"❌ Vector search failed: {e}")
        return ""
        
    if not matched_nodes:
        print("   - No similar nodes found in vector DB.")
        return ""
        
    print(f"   - Found similar nodes: {matched_nodes}")
    
    # Step B: Graph Traversal
    driver = get_neo4j_driver()
    if not driver:
        return ""
        
    subgraph_facts = []
    try:
        with driver.session() as session:
            # Cypher to get node and its immediate relationships
            # We match nodes where 'name' is in our matched list
            cypher = """
            MATCH (n:Entity)-[r]-(m:Entity)
            WHERE n.name IN $names
            RETURN n.name AS source, type(r) AS relation, m.name AS target
            LIMIT 20
            """
            result = session.run(cypher, names=matched_nodes)
            
            for record in result:
                fact = f"{record['source']} {record['relation']} {record['target']}"
                subgraph_facts.append(fact)
                
    except Exception as e:
        print(f"❌ Graph traversal failed: {e}")
    finally:
        driver.close()
        
    # Step C: Formatter
    if not subgraph_facts:
        return ""
        
    context_str = "Context found:\n" + "\n".join(subgraph_facts)
    print(f"✅ GraphRAG Context:\n{context_str}")
    return context_str

def save_to_graph(data):
    """
    Saves extracted nodes and edges to Neo4j.
    Input: {'nodes': ['Name1', 'Name2'], 'edges': [['Name1', 'RELATION', 'Name2']]}
    """
    print(f"Saving to Graph: {data}")
    driver = get_neo4j_driver()
    if not driver:
        return

    try:
        with driver.session() as session:
            # 1. Create Nodes
            for node_name in data.get("nodes", []):
                session.run("MERGE (n:Entity {name: $name})", name=node_name)
            
            # 2. Create Relationships
            for edge in data.get("edges", []):
                source, relation, target = edge
                
                # Sanitize relationship type (replace spaces with _, uppercase)
                # Cypher requires relationship types to be static or injected safely
                safe_relation = relation.replace(" ", "_").upper()
                
                # We use f-string for the relationship type because it cannot be a parameter
                query = (
                    "MATCH (a:Entity {name: $source}), (b:Entity {name: $target}) "
                    f"MERGE (a)-[:{safe_relation}]->(b)"
                )
                
                session.run(query, source=source, target=target)
                
        print("✅ Data saved to Neo4j successfully!")
        
    except Exception as e:
        print(f"❌ Error saving to Neo4j: {e}")
    finally:
        driver.close()

def save_to_vector(text):
    """
    Generates a vector for the text and saves it to Pinecone.
    """
    print(f"Saving to Vector: '{text[:50]}...'")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        print("❌ PINECONE_API_KEY missing.")
        return

    try:
        # 1. Generate Vector
        embeddings = get_embeddings()
        vector = embeddings.embed_query(text)
        
        # 2. Connect to Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        
        # Get the first available index
        indexes = pc.list_indexes()
        index_names = [i.name for i in indexes] if hasattr(indexes, 'names') else [i['name'] for i in indexes] if isinstance(indexes, list) else indexes
        
        if not index_names:
            print("❌ No Pinecone indexes found.")
            return
            
        index_name = index_names[0] # Use the first index
        index = pc.Index(index_name)
        
        # 3. Upsert Vector
        # ID is a simple timestamp
        vector_id = str(int(time.time()))
        
        index.upsert(
            vectors=[
                {
                    "id": vector_id,
                    "values": vector,
                    "metadata": {"text": text}
                }
            ]
        )
        
        print(f"✅ Vector saved to Pinecone index '{index_name}' with ID {vector_id}!")
        
    except Exception as e:
        print(f"❌ Error saving to Pinecone: {e}")

def search_memory(query):
    """
    Searches Pinecone for relevant context.
    Returns a string of concatenated context.
    """
    print(f"Searching Memory for: '{query}'")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        return ""

    try:
        # 1. Generate Vector
        embeddings = get_embeddings()
        vector = embeddings.embed_query(query)
        
        # 2. Connect to Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        indexes = pc.list_indexes()
        index_names = [i.name for i in indexes] if hasattr(indexes, 'names') else [i['name'] for i in indexes] if isinstance(indexes, list) else indexes
        
        if not index_names:
            return ""
            
        index = pc.Index(index_names[0])
        
        # 3. Search
        results = index.query(vector=vector, top_k=3, include_metadata=True)
        
        # 4. Extract Context
        contexts = []
        for match in results.matches:
            if match.metadata and "text" in match.metadata:
                contexts.append(match.metadata["text"])
                
        return "\n\n".join(contexts)
        
    except Exception as e:
        print(f"❌ Error searching memory: {e}")
        return ""

def test_connections():
    print("--- Starting Connection Tests ---")
    
    # 1. Neo4j Check
    print("\nTesting Neo4j...")
    driver = get_neo4j_driver()
    if driver:
        try:
            driver.verify_connectivity()
            records, summary, keys = driver.execute_query("RETURN 'Neo4j Connected!' AS message")
            for record in records:
                print(f"✅ {record['message']}")
            driver.close()
        except Exception as e:
            print(f"❌ Neo4j Connection Failed: {e}")

    # 2. Pinecone Check
    print("\nTesting Pinecone...")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")

    if not pinecone_api_key:
        print("❌ PINECONE_API_KEY missing in .env")
    else:
        try:
            pc = Pinecone(api_key=pinecone_api_key)
            indexes = pc.list_indexes()
            # Handle the response which might be an object or list depending on version
            index_names = [i.name for i in indexes] if hasattr(indexes, 'names') else [i['name'] for i in indexes] if isinstance(indexes, list) else indexes
            print(f"✅ Pinecone Connected! Available Indexes: {index_names}")
        except Exception as e:
            print(f"❌ Pinecone Connection Failed: {e}")

if __name__ == "__main__":
    # 1. Run connection tests
    test_connections()
    
    # 2. Test Graph Storage
    print("\n--- Testing Graph Storage ---")
    dummy_data = {
        "nodes": ["Steve Jobs", "Apple"], 
        "edges": [["Steve Jobs", "FOUNDED", "Apple"]]
    }
    save_to_graph(dummy_data)
    
    # 3. Test Vector Storage
    print("\n--- Testing Vector Storage ---")
    save_to_vector("Steve Jobs was a visionary who changed the world with the iPhone.")
