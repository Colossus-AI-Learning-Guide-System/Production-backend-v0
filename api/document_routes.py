"""Document management API endpoints"""
from flask import Blueprint, request, jsonify
import base64
import tempfile
import os
from PyPDF2 import PdfReader
import uuid

from services.document_service import get_document_processor
from services.indexing_service import (
    index_for_rag, 
    get_indexing_status,
    get_all_available_documents,
    delete_document_index,
    rag_indexing_status
)
from utils.file_utils import save_temp_file, clean_temp_file

# Create blueprint
document_bp = Blueprint('document', __name__)

@document_bp.route('/unified-upload', methods=['POST'])
def unified_upload():
    """Upload a document and process it for both structure and RAG"""
    try:
        print("Received unified upload request")
        data = request.json
        file_base64 = data.get('file', '')
        filename = data.get('filename', '')  # Get the original filename
        
        if not file_base64:
            return jsonify({"error": "No file provided"}), 400
            
        # Save the binary data to a temporary file
        file_bytes = base64.b64decode(file_base64)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name
        
        try:
            # Verify the file is a valid PDF
            reader = PdfReader(temp_file_path)
            print(f"Valid PDF with {len(reader.pages)} pages.")
            
            # 1. Process for document structure visualization FIRST
            print("Processing document structure...")
            document_processor = get_document_processor()
            document_id = document_processor.process_document(temp_file_path, original_filename=filename)
            
            # Get the document structure immediately
            document_structure = document_processor.get_document_structure(document_id)
            
            # 2. Create a copy of the file for RAG indexing
            rag_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
            with open(temp_file_path, "rb") as src, open(rag_temp_file, "wb") as dst:
                dst.write(src.read())
            
            # Import the RAG model from app context
            from app import rag_model
            
            # Start the background thread for RAG indexing
            index_for_rag(rag_temp_file, document_id, rag_model)
            
            # Return the document structure immediately
            return jsonify({
                "message": "Document structure processed successfully. RAG indexing in progress.",
                "document_id": document_id,
                "structure": document_structure,
                "rag_status": "indexing_in_progress"
            }), 200
            
        finally:
            # Clean up the original temporary file
            clean_temp_file(temp_file_path)
            
    except Exception as e:
        print("Error in unified_upload:", str(e))
        return jsonify({"error": str(e)}), 500

@document_bp.route('/indexing-status/<document_id>', methods=['GET'])
def document_indexing_status(document_id):
    """Check the status of RAG indexing for a document"""
    status = get_indexing_status(document_id)
    return jsonify({"document_id": document_id, "rag_status": status})

@document_bp.route('/documents', methods=['GET'])
def get_documents_list():
    """Get a list of all available documents with their indexing status"""
    try:
        document_processor = get_document_processor()
        document_list = get_all_available_documents(document_processor)
        return jsonify({"documents": document_list}), 200
    except Exception as e:
        print("Error in get_documents_list:", str(e))
        return jsonify({"error": str(e)}), 500

@document_bp.route('/upload', methods=['POST'])  # Legacy endpoint
def upload_files():
    """Legacy endpoint for uploading and indexing files"""
    try:
        print("Received upload request")
        data = request.json
        files = data.get('files', [])
        if not files:
            return jsonify({"error": "No files provided"}), 400

        document_ids = []

        # Import the RAG model from app context
        from app import rag_model
        
        # Process each file
        for idx, file_base64 in enumerate(files):
            print(f"Processing file {idx + 1}")
            temp_file_path = save_temp_file(base64.b64decode(file_base64), suffix=".pdf")

            try:
                # Verify the file is a valid PDF
                reader = PdfReader(temp_file_path)
                print(f"File {idx + 1} is a valid PDF with {len(reader.pages)} pages.")
                
                # Generate a document ID
                document_id = str(uuid.uuid4())
                document_ids.append(document_id)
                
                # Index the document with the document ID as index name
                print(f"Indexing the document with ID {document_id}...")
                # Call RAG indexing directly (not in background)
                rag_model.index(
                    input_path=temp_file_path,
                    index_name=document_id,
                    store_collection_with_index=True,
                    overwrite=True
                )
                
                # Update status
                rag_indexing_status[document_id] = "completed"
            finally:
                clean_temp_file(temp_file_path)

        return jsonify({
            "message": "Files uploaded and indexed successfully",
            "document_ids": document_ids
        }), 200
    except Exception as e:
        print("Error in upload_files:", str(e))
        return jsonify({"error": str(e)}), 500

@document_bp.route('/document/<document_id>', methods=['DELETE'])
def delete_document(document_id):
    """Delete a document from the database and its RAG index"""
    try:
        # Import the RAG model from app context
        from app import rag_model
        
        # Delete from Neo4j with cascading delete
        document_processor = get_document_processor()
        neo4j_success = document_processor.clear_document(document_id)
        
        # Delete RAG index
        rag_success = delete_document_index(document_id, rag_model)
        
        # Log the deletion status
        results = {
            "neo4j_deletion": "successful" if neo4j_success else "failed or not found",
            "rag_deletion": "successful" if rag_success else "failed or not found",
        }
        print(f"Document deletion results for {document_id}: {results}")
        
        # Clean up any orphaned nodes that might remain
        if neo4j_success:
            orphaned_deleted = document_processor.clean_orphaned_nodes()
            if orphaned_deleted > 0:
                print(f"Cleaned up {orphaned_deleted} orphaned nodes after document deletion")
        
        if neo4j_success or rag_success:
            return jsonify({
                "message": f"Document {document_id} deleted successfully",
                "details": results
            }), 200
        else:
            return jsonify({
                "error": f"Document {document_id} not found",
                "details": results
            }), 404
    except Exception as e:
        print(f"Error in delete_document: {str(e)}")
        return jsonify({"error": str(e)}), 500

@document_bp.route('/documents-with-metadata', methods=['GET'])
def get_documents_with_metadata():
    """Get all documents with metadata"""
    try:
        # Get document processor from your service
        document_processor = get_document_processor()
        
        # Get documents with metadata
        documents = document_processor.get_all_documents_with_metadata()
        
        return jsonify(documents)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@document_bp.route('/document/<document_id>/page/<int:page_number>', methods=['GET'])
def get_document_page(document_id, page_number):
    """Get a specific page image for a document"""
    try:
        document_processor = get_document_processor()
        page_data = document_processor.get_page_image(document_id, page_number)
        return jsonify(page_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@document_bp.route('/document/<document_id>/heading/<heading>', methods=['GET'])
def get_document_heading_page(document_id, heading):
    """Get the page image for a specific heading"""
    try:
        document_processor = get_document_processor()
        heading_data = document_processor.get_heading_page(document_id, heading)
        return jsonify(heading_data)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"Error in get_document_heading_page: {str(e)}")
        return jsonify({"error": str(e)}), 500

@document_bp.route('/document/<document_id>/metadata', methods=['GET'])
def get_document_metadata(document_id):
    """Get metadata for a specific document"""
    try:
        document_processor = get_document_processor()
        metadata = document_processor.get_document_metadata(document_id)
        return jsonify(metadata)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"Error in get_document_metadata: {str(e)}")
        return jsonify({"error": str(e)}), 500

