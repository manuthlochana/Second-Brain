import os
from dotenv import load_dotenv
from pinecone import Pinecone
import database

load_dotenv()

def reset_db():
    print("🚀 Starting Full System Wipe...")
    
    # 1. Wipe Neo4j
    print("🗑️  Wiping Neo4j Graph...")
    driver = database.get_neo4j_driver()
    if driver:
        try:
            with driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                print("✅ Neo4j Wiped!")
        finally:
            driver.close()

    # 2. Wipe Pinecone
    print("🗑️  Wiping Pinecone Vectors...")
    api_key = os.getenv("PINECONE_API_KEY")
    if api_key:
        try:
            pc = Pinecone(api_key=api_key)
            # List indexes to find the correct one
            indexes = pc.list_indexes()
            # Handle different response formats (object vs list)
            index_names = [i.name for i in indexes] if hasattr(indexes, 'names') else [i['name'] for i in indexes] if isinstance(indexes, list) else indexes
            
            if index_names:
                target_index = index_names[0]
                index = pc.Index(target_index)
                index.delete(delete_all=True)
                print(f"✅ Pinecone Index '{target_index}' Cleared!")
            else:
                print("⚠️ No Pinecone indexes found.")
        except Exception as e:
            print(f"❌ Pinecone Error: {e}")
    
    print("✨ System Reset Complete!")

if __name__ == "__main__":
    reset_db()
