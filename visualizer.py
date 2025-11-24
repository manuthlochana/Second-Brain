import database
from streamlit_agraph import agraph, Node, Edge, Config

def get_graph_data():
    """
    Fetches nodes and edges from Neo4j and converts them to agraph format.
    """
    nodes = []
    edges = []
    node_ids = set()
    
    driver = database.get_neo4j_driver()
    if not driver:
        return [], [], Config()
        
    try:
        with driver.session() as session:
            # Fetch all nodes and relationships (Limit 50 for performance)
            result = session.run("MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50")
            
            for record in result:
                source_node = record["n"]
                relation = record["r"]
                target_node = record["m"]
                
                # Process Source Node
                source_id = source_node.element_id if hasattr(source_node, 'element_id') else str(source_node.id)
                source_label = source_node.get("name", "Unknown")
                
                if source_id not in node_ids:
                    nodes.append(Node(id=source_id, label=source_label, size=25, shape="circular"))
                    node_ids.add(source_id)
                
                # Process Target Node
                target_id = target_node.element_id if hasattr(target_node, 'element_id') else str(target_node.id)
                target_label = target_node.get("name", "Unknown")
                
                if target_id not in node_ids:
                    nodes.append(Node(id=target_id, label=target_label, size=25, shape="circular"))
                    node_ids.add(target_id)
                
                # Process Edge
                edges.append(Edge(source=source_id, target=target_id, label=relation.type))
                
    except Exception as e:
        print(f"Error fetching graph data: {e}")
    finally:
        driver.close()
        
    # Configuration for the graph
    config = Config(width=750, 
                    height=500, 
                    directed=True,
                    physics=True, 
                    hierarchical=False,
                    nodeHighlightBehavior=True, 
                    highlightColor="#F7A7A6",
                    collapsible=True)
                    
    return nodes, edges, config
