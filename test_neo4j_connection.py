from neo4j import GraphDatabase
from config.settings import get_settings

def test_connection():
    """Test connection to Neo4j database."""
    settings = get_settings()
    
    print(f"Connecting to Neo4j at {settings.NEO4J_URI}...")
    
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        
        with driver.session() as session:
            # Simple test query
            result = session.run("RETURN 'Connection successful!' AS message")
            message = result.single()["message"]
            print(f"Neo4j says: {message}")
        
        driver.close()
        print("Connection test completed successfully")
        return True
        
    except Exception as e:
        print(f"Connection error: {str(e)}")
        return False

if __name__ == "__main__":
    test_connection()