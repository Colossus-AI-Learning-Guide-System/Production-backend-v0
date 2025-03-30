# services/query_service.py
import base64
import os
from claudette import *
from utils.query_utils import determine_k_from_query
from models.pixtral_models import process_with_pixtral_api, process_with_pixtral_local
from config.settings import get_settings

def choose_model_for_query(k, force_model='auto'):
    """
    Choose the appropriate model based on k value and user preference
    
    Args:
        k: Number of results to retrieve
        force_model: User-specified model ('auto', 'claude', or 'pixtral')
        
    Returns:
        Tuple of (use_pixtral, limited_results, adjusted_k)
    """
    settings = get_settings()
    claude_max_k = settings.CLAUDE_MAX_K
    use_pixtral = False
    limited_results = False
    
    if force_model == 'claude':
        use_pixtral = False
        if k > claude_max_k:
            limited_results = True
            k = claude_max_k
    elif force_model == 'pixtral':
        use_pixtral = True
        limited_results = False
    else:  # auto
        if k > claude_max_k:
            use_pixtral = True
            limited_results = False
        else:
            use_pixtral = False
            limited_results = False
    
    return use_pixtral, limited_results, k

def process_with_claude(results, query, limited_results=False):
    """
    Process query using Claude
    
    Args:
        results: List of RAG results
        query: User query
        limited_results: Whether results are limited
        
    Returns:
        Dictionary with Claude's response and metadata
    """
    settings = get_settings()
    
    # For single page query
    if len(results) == 1:
        result = results[0]
        image_bytes = base64.b64decode(result.base64)
        
        # Pass single image and query to Claude
        os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
        chat = Chat(models[1])
        claude_response = chat([image_bytes, query])
        
    else:
        # Multi-page query (2-4 pages)
        context_images = []
        for result in results:
            image_bytes = base64.b64decode(result.base64)
            context_images.append(image_bytes)
        
        # Create a prompt that indicates multiple pages
        if limited_results:
            prompt = f"[This query refers to {len(context_images)} pages from the document. Note that I'm showing only the most relevant pages due to technical limitations.] {query}"
        else:
            prompt = f"[This query refers to {len(context_images)} pages from the document] {query}"
        
        # Pass all images and query to Claude
        os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
        chat = Chat(models[1])
        claude_response = chat(context_images + [prompt])
    
    # Extract text content from Claude's response
    claude_content = ""
    if hasattr(claude_response, "content"):
        for block in claude_response.content:
            if hasattr(block, "text"):
                claude_content += block.text + "\n"
    else:
        claude_content = "No content available"
    
    return {
        "response": claude_content,
        "model_used": "claude"
    }

def process_query(query, document_id, k, rag_model, force_model='auto', use_local_pixtral=False):
    """
    Process a query against a document using the appropriate model
    
    Args:
        query: User query
        document_id: ID of the document to query against
        k: Number of results to retrieve
        rag_model: RAG model instance
        force_model: User-specified model ('auto', 'claude', or 'pixtral')
        use_local_pixtral: Whether to use local Pixtral (vs API)
        
    Returns:
        Dictionary with query response and metadata
    """
    settings = get_settings()
    
    # Choose model based on parameters
    use_pixtral, limited_results, adjusted_k = choose_model_for_query(k, force_model)
    
    # First check if the index exists by directly checking the filesystem
    index_exists = False
    index_path = None
    
    try:
        import os
        from pathlib import Path
        
        index_paths = [
            os.path.join(".byaldi", document_id),
            os.path.abspath(os.path.join(".byaldi", document_id)),
            os.path.join(os.getcwd(), ".byaldi", document_id),
            str(Path(".byaldi") / document_id)
        ]
        
        print(f"Checking for index directories for document ID: {document_id}")
        for path in index_paths:
            if os.path.exists(path) and os.path.isdir(path):
                index_exists = True
                index_path = path
                print(f"Found index directory at: {path}")
                break
                
        if not index_exists:
            print(f"WARNING: Could not find index directory for document ID: {document_id}")
            print(f"Checked paths: {index_paths}")
    except Exception as e:
        print(f"Error checking for index directory: {str(e)}")
    
    # Load the document-specific index before querying
    try:
        print(f"Loading document-specific index for document {document_id}")
        
        # Check if this index is already loaded
        current_index_loaded = False
        if hasattr(rag_model.model, 'index_name') and rag_model.model.index_name == document_id:
            print(f"Index for document {document_id} is already loaded, no need to reload")
            current_index_loaded = True
            # Search directly without loading
            results = rag_model.search(query, k=adjusted_k)
        # If not already loaded, try using the load_index method 
        elif hasattr(rag_model, 'load_index'):
            print("Using load_index method")
            success = rag_model.load_index(document_id)
            if success:
                print(f"Successfully loaded index for document {document_id}")
                # Search without index_name parameter
                results = rag_model.search(query, k=adjusted_k)
            else:
                print(f"Failed to load index with load_index, falling back to from_index method")
                # Fall back to creating a new instance
                from models.rag_models import EnhancedRAGMultiModalModel
                print("Creating new RAGMultiModalModel instance from index")
                document_rag_model = EnhancedRAGMultiModalModel.from_index(document_id)
                results = document_rag_model.search(query, k=adjusted_k)
        else:
            print(f"rag_model doesn't have load_index method, falling back to from_index method")
            # Fall back to creating a new instance
            from models.rag_models import EnhancedRAGMultiModalModel
            print("Creating new RAGMultiModalModel instance from index")
            document_rag_model = EnhancedRAGMultiModalModel.from_index(document_id)
            results = document_rag_model.search(query, k=adjusted_k)
    except Exception as e:
        print(f"Error loading document-specific index: {str(e)}")
        
        # If we found an index directory but couldn't load the index,
        # there might be an issue with the index format or compatibility
        if index_exists:
            print(f"WARNING: Index directory exists at {index_path} but could not be loaded")
            
        print("No passages found in this index or index is corrupted")
        # Return a meaningful error instead of trying the unsupported method
        return {
            "error": "The document index appears to be empty or corrupted. Please try re-uploading the document.",
            "document_id": document_id
        }
    
    # Check if we have results
    if not results or len(results) == 0:
        print(f"WARNING: No results found for query: '{query}'")
        return {
            "response": f"I couldn't find any relevant information for your query in the document.",
            "page_count": 0,
            "requested_k": k,
            "limited_results": False,
            "model_used": "none",
            "error": "No results found"
        }
    
    # Process with the appropriate model
    if not use_pixtral or not (settings.HF_API_TOKEN or use_local_pixtral):
        # Process with Claude
        claude_result = process_with_claude(results, query, limited_results)
        
        return {
            "response": claude_result["response"],
            "page_count": len(results),
            "requested_k": k,
            "limited_results": limited_results,
            "model_used": "claude"
        }
        
    else:
        # Process with Pixtral (local or API)
        pixtral_result = None
        
        if use_local_pixtral:
            pixtral_result = process_with_pixtral_local(query, results)
        else:
            pixtral_result = process_with_pixtral_api(query, results)
        
        if not pixtral_result["success"]:
            # Fallback to Claude if Pixtral fails
            fallback_k = min(k, settings.CLAUDE_MAX_K)
            fallback_results = results[:fallback_k]
            limited_results = True if k > settings.CLAUDE_MAX_K else False
            
            # Process with Claude as fallback
            claude_result = process_with_claude(fallback_results, query, limited_results)
            
            return {
                "response": claude_result["response"],
                "page_count": len(fallback_results),
                "requested_k": k,
                "limited_results": limited_results,
                "model_used": "claude",
                "fallback_reason": pixtral_result["error"]
            }
        else:
            # Return successful Pixtral response
            return {
                "response": pixtral_result["response"],
                "page_count": len(results),
                "requested_k": k,
                "limited_results": False,
                "model_used": "pixtral-local" if use_local_pixtral else "pixtral-api"
            }