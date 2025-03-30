"""Query API endpoints"""
from flask import Blueprint, request, jsonify

from services.query_service import process_query
from services.indexing_service import get_indexing_status
from utils.query_utils import determine_k_from_query

# Create blueprint
query_bp = Blueprint('query', __name__)

@query_bp.route('/query', methods=['POST'])
def handle_query():
    """Query a document using RAG and Claude/Pixtral"""
    try:
        data = request.json
        query = data.get('query', '')
        document_id = data.get('document_id')
        k = data.get('k', None)
        force_model = data.get('model', 'auto')  # 'auto', 'claude', or 'pixtral'
        
        if not query:
            return jsonify({"error": "Query is required"}), 400
        
        if not document_id:
            return jsonify({"error": "Document ID is required"}), 400
        
        # Check if index exists by directly checking the filesystem
        # rather than relying only on the indexing_status
        import os
        from pathlib import Path
        
        index_exists = False
        index_paths = [
            os.path.join(".byaldi", document_id),
            os.path.abspath(os.path.join(".byaldi", document_id)),
            str(Path(".byaldi") / document_id)
        ]
        
        for path in index_paths:
            if os.path.exists(path) and os.path.isdir(path):
                index_exists = True
                print(f"Found index at {path}")
                break
        
        # Get the indexing status as a fallback
        rag_status = get_indexing_status(document_id)
        
        # If index doesn't exist and status isn't completed, return error
        if not index_exists and rag_status != "completed":
            return jsonify({
                "error": f"Document {document_id} index not found or indexing is not complete",
                "status": rag_status
            }), 400

        # Set k based on query analysis if not provided
        if k is None:
            k = determine_k_from_query(query)
        else:
            # Ensure k is an integer
            try:
                k = int(k)
            except ValueError:
                return jsonify({"error": "Parameter 'k' must be an integer"}), 400
        
        # Import rag_model from app context
        from app import rag_model
        
        # Determine if we should use local Pixtral
        from config.settings import get_settings
        settings = get_settings()
        use_local_pixtral = hasattr(settings, 'USE_LOCAL_PIXTRAL') and settings.USE_LOCAL_PIXTRAL
        
        # Process the query
        result = process_query(query, document_id, k, rag_model, force_model, use_local_pixtral)
        
        # Return the result
        return jsonify(result), 200
                
    except Exception as e:
        print("Error in handle_query:", str(e))
        return jsonify({"error": str(e)}), 500