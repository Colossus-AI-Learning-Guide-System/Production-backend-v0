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
        print(f"Attempting to delete RAG index for document {document_id}")
        
        success = False
        
        # Method 1: Try using the RAG model's delete_index method if available
        if hasattr(rag_model, 'delete_index'):
            print(f"RAG model has delete_index method, calling it for {document_id}")
            try:
                result = rag_model.delete_index(document_id)
                print(f"Delete index call result: {result}")
                if result:
                    success = True
            except Exception as model_e:
                print(f"Error in rag_model.delete_index: {str(model_e)}")
        else:
            print(f"WARNING: RAG model does not have delete_index method")
        
        # Method 2: Try using force_delete_index from models.rag_models if available
        if not success:
            try:
                from models.rag_models import force_delete_index
                print(f"Trying force_delete_index function for {document_id}")
                result = force_delete_index(document_id)
                print(f"Force delete result: {result}")
                if result:
                    success = True
            except (ImportError, AttributeError) as e:
                print(f"Could not use force_delete_index: {str(e)}")
                
                # Method 3: Direct path-based deletion as fallback
                try:
                    import shutil
                    from pathlib import Path
                    import os
                    
                    # Try multiple paths
                    paths_to_try = [
                        os.path.join(".byaldi", document_id),
                        os.path.abspath(os.path.join(".byaldi", document_id)),
                        os.path.join(os.getcwd(), ".byaldi", document_id),
                        str(Path(".byaldi") / document_id)
                    ]
                    
                    for path in paths_to_try:
                        if os.path.exists(path):
                            print(f"Found index at: {path}")
                            
                            # Try method 1: shutil.rmtree
                            try:
                                print(f"Attempting to delete with shutil.rmtree: {path}")
                                shutil.rmtree(path)
                                if not os.path.exists(path):
                                    print(f"Successfully deleted index at: {path}")
                                    success = True
                                    break
                            except Exception as rmtree_e:
                                print(f"shutil.rmtree failed: {str(rmtree_e)}")
                            
                            # Try method 2: os.system with rmdir (Windows)
                            try:
                                cmd = f'rmdir /S /Q "{path}"'
                                print(f"Attempting OS command: {cmd}")
                                os.system(cmd)
                                if not os.path.exists(path):
                                    print(f"Successfully deleted index with OS command at: {path}")
                                    success = True
                                    break
                            except Exception as os_e:
                                print(f"OS command failed: {str(os_e)}")
                                
                            # Try method 3: os.system with rm -rf (Unix-like)
                            try:
                                cmd = f'rm -rf "{path}"'
                                print(f"Attempting Unix OS command: {cmd}")
                                os.system(cmd)
                                if not os.path.exists(path):
                                    print(f"Successfully deleted index with Unix OS command at: {path}")
                                    success = True
                                    break
                            except Exception as unix_e:
                                print(f"Unix OS command failed: {str(unix_e)}")
                except Exception as fallback_e:
                    print(f"Error in fallback deletion: {str(fallback_e)}")
        
        # Remove from status tracking regardless of success
        if document_id in rag_indexing_status:
            print(f"Removing document {document_id} from RAG indexing status tracking")
            del rag_indexing_status[document_id]
        else:
            print(f"Document {document_id} not found in RAG indexing status tracking")
        
        # Final verification
        index_path = Path(".byaldi") / str(document_id)
        if index_path.exists():
            print(f"WARNING: Index directory still exists at {index_path} after all deletion attempts")
            return success
        else:
            print(f"Verified index directory does not exist at {index_path}")
            return True
    except Exception as e:
        print(f"Error in delete_document_index for {document_id}: {str(e)}")
        return False

