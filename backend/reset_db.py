import database

def reset_db():
    print("🗑️  Wiping Neo4j Database...")
    driver = database.get_neo4j_driver()
    
    if not driver:
        print("❌ Could not connect to Neo4j.")
        return

    try:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("✅ Database Wiped Clean!")
    except Exception as e:
        print(f"❌ Error wiping database: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    reset_db()
