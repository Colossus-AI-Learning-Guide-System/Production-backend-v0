# services/document_service.py
from config.settings import get_settings
from storage.neo4j_storage import Neo4jDocumentProcessor

# Global variable for document processor
_document_processor = None

def init_document_processor():
    """
    Initialize the document processor with Neo4j connection.
    Returns a singleton instance of Neo4jDocumentProcessor.
    """
    global _document_processor
    
    if _document_processor is None:
        settings = get_settings()
        try:
            _document_processor = Neo4jDocumentProcessor(
                settings.NEO4J_URI,
                settings.NEO4J_USER,
                settings.NEO4J_PASSWORD
            )
            print(f"Neo4j document processor initialized at {settings.NEO4J_URI}")
        except Exception as e:
            print(f"Error initializing Neo4j document processor: {str(e)}")
            raise
            
    return _document_processor

def get_document_processor():
    """Get the document processor instance."""
    global _document_processor
    
    if _document_processor is None:
        return init_document_processor()
    
    return _document_processor

def close_document_processor():
    """Close the document processor connection."""
    global _document_processor
    
    if _document_processor is not None:
        try:
            _document_processor.close()
            print("Neo4j document processor connection closed")
        except Exception as e:
            print(f"Error closing Neo4j connection: {str(e)}")
        finally:
            _document_processor = None