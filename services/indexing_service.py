# services/indexing_service.py
import os
import threading
from typing import List, Dict, Any  # Add this import for type annotations
from PyPDF2 import PdfReader

# Global variable to track indexing status
rag_indexing_status = {}

def index_for_rag(file_path, document_id, rag_model):
    """
    Background thread function for RAG indexing with document-specific index
    
    Args:
        file_path: Path to the file to index
        document_id: ID for the document
        rag_model: RAG model to use for indexing
    """
    try:
        rag_indexing_status[document_id] = "in_progress"
        print(f"Starting background indexing for RAG (document {document_id})...")
        
        # Use document_id as the index name to create separate indexes
        rag_model.index(
            input_path=file_path,
            index_name=document_id,  # Document-specific index
            store_collection_with_index=True,
            overwrite=True
        )
        
        print(f"Background RAG indexing completed successfully for document {document_id}")
        rag_indexing_status[document_id] = "completed"
    except Exception as e:
        print(f"Error in background RAG indexing for document {document_id}: {str(e)}")
        rag_indexing_status[document_id] = "failed"
    finally:
        # Clean up the temporary file after processing
        if os.path.exists(file_path):
            os.unlink(file_path)

def start_indexing_thread(file_path, document_id, rag_model):
    """
    Start a background thread for RAG indexing
    
    Args:
        file_path: Path to the file to index
        document_id: ID for the document
        rag_model: RAG model to use for indexing
    """
    rag_thread = threading.Thread(target=index_for_rag, args=(file_path, document_id, rag_model))
    rag_thread.daemon = True
    rag_thread.start()
    return rag_thread

def get_indexing_status(document_id):
    """
    Get the indexing status of a document
    
    Args:
        document_id: ID of the document
        
    Returns:
        Status string: "completed", "in_progress", "failed", or "unknown"
    """
    return rag_indexing_status.get(document_id, "unknown")

def get_all_available_documents(document_processor):
    """
    Get a list of all available documents with their indexing status
    
    Args:
        document_processor: Document processor instance
        
    Returns:
        List of document dictionaries with status
    """
    try:
        # Get document structures from Neo4j
        documents = document_processor.get_all_documents()
        
        # Create a comprehensive document list with status
        document_list = []
        for doc_id in documents:
            try:
                # Get basic document info
                structure = document_processor.get_document_structure(doc_id)
                
                # Get RAG indexing status
                rag_status = rag_indexing_status.get(doc_id, "unknown")
                
                # Add to list
                document_list.append({
                    "document_id": doc_id,
                    "headings_count": len(structure.get("headings", [])),
                    "rag_status": rag_status,
                    "can_query": rag_status == "completed"
                })
            except Exception as e:
                print(f"Error getting info for document {doc_id}: {str(e)}")
        
        return document_list
    except Exception as e:
        print(f"Error in get_all_available_documents: {str(e)}")
        return []

def delete_document_index(document_id, rag_model):
    """
    Delete a document's RAG index
    
    Args:
        document_id: ID of the document
        rag_model: RAG model instance
        
    Returns:
        Success status
    """
    try:
        # Check if this RAG system has a delete_index method
        if hasattr(rag_model, 'delete_index'):
            rag_model.delete_index(document_id)
        
        # Remove from status tracking
        if document_id in rag_indexing_status:
            del rag_indexing_status[document_id]
        
        return True
    except Exception as e:
        print(f"Warning: Could not delete RAG index for {document_id}: {str(e)}")
        return False

