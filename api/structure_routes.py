"""Document structure API endpoints"""
from flask import Blueprint, request, jsonify

from services.document_service import get_document_processor

# Create blueprint
structure_bp = Blueprint('structure', __name__)

@structure_bp.route('/upload', methods=['POST'])
def upload_document_structure():
    """
    Upload a document and process its structure for visualization.
    Expects a JSON with a base64-encoded PDF in the 'file' field.
    """
    try:
        print("Received document structure upload request")
        data = request.json
        file_base64 = data.get('file', '')
        
        if not file_base64:
            return jsonify({"error": "No file provided"}), 400
        
        # Process the document and store in Neo4j
        document_processor = get_document_processor()
        document_id = document_processor.process_base64_document(file_base64)
        
        # Get the processed document structure
        document_structure = document_processor.get_document_structure(document_id)
        
        return jsonify({
            "document_id": document_id,
            "structure": document_structure
        }), 200
        
    except Exception as e:
        print("Error in upload_document_structure:", str(e))
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/documents', methods=['GET'])
def get_all_documents():
    """
    Get a list of all processed documents.
    """
    try:
        document_processor = get_document_processor()
        documents = document_processor.get_all_documents()
        return jsonify({"documents": documents}), 200
    except Exception as e:
        print("Error in get_all_documents:", str(e))
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>', methods=['GET'])
def get_document_structure(document_id):
    """
    Get the structure of a specific document.
    """
    try:
        document_processor = get_document_processor()
        structure = document_processor.get_document_structure(document_id)
        return jsonify(structure), 200
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print("Error in get_document_structure:", str(e))
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>/heading', methods=['GET'])
def get_heading_page(document_id):
    """
    Get the page image for a specific heading.
    Expects a 'heading' parameter in the query string.
    """
    try:
        heading = request.args.get('heading', '')
        if not heading:
            return jsonify({"error": "Heading parameter is required"}), 400
        
        document_processor = get_document_processor()
        heading_data = document_processor.get_heading_page(document_id, heading)
        return jsonify(heading_data), 200
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print("Error in get_heading_page:", str(e))
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>', methods=['DELETE'])
def delete_document_structure(document_id):
    """
    Delete a document and its structure from Neo4j.
    This endpoint focuses only on the document structure in Neo4j, not the RAG index.
    """
    try:
        document_processor = get_document_processor()
        success = document_processor.clear_document(document_id)
        
        # Clean up any orphaned nodes that might remain
        if success:
            orphaned_deleted = document_processor.clean_orphaned_nodes()
            if orphaned_deleted > 0:
                print(f"Cleaned up {orphaned_deleted} orphaned nodes after document structure deletion")
        
        if success:
            return jsonify({
                "message": f"Document {document_id} structure deleted successfully",
                "details": {"neo4j_deletion": "successful"}
            }), 200
        else:
            return jsonify({
                "error": f"Document {document_id} not found",
                "details": {"neo4j_deletion": "failed or not found"}
            }), 404
    except Exception as e:
        print(f"Error in delete_document_structure: {str(e)}")
        return jsonify({"error": str(e)}), 500