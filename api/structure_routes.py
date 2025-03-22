"""Document structure API endpoints"""
from flask import Blueprint, request, jsonify
import tempfile
import os
import uuid
from datetime import datetime

from services.document_service import get_document_processor

# Create blueprint
structure_bp = Blueprint('structure', __name__)

@structure_bp.route('/upload', methods=['POST'])
def upload_document_structure():
    """
    Upload a document and process its structure for visualization.
    Uses the enhanced Claude method for better document structure extraction.
    
    Expects a JSON with a base64-encoded PDF in the 'file' field.
    """
    try:
        print("Received document structure upload request")
        data = request.json
        file_base64 = data.get('file', '')
        filename = data.get('filename', '')
        
        if not file_base64:
            return jsonify({"error": "No file provided"}), 400
        
        # Process the document and store in Neo4j
        document_processor = get_document_processor()
        document_id = document_processor.process_base64_document(file_base64, filename)
        
        # Get the processed document structure
        document_structure = document_processor.get_document_structure(document_id)
        
        # Also get the structured content
        structured_content = document_processor.get_structured_content(document_id)
        
        return jsonify({
            "document_id": document_id,
            "structure": document_structure,
            "structured_content": structured_content
        }), 200
        
    except Exception as e:
        print("Error in upload_document_structure:", str(e))
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/upload/raw', methods=['POST'])
def upload_raw_document():
    """
    Upload a raw PDF document and process its structure for visualization.
    Uses the enhanced Claude method for better document structure extraction.
    
    Accepts a multipart/form-data request with a 'file' field containing the PDF.
    
    Returns:
        JSON with document_id and extracted structure
    """
    try:
        print("Received raw document upload request")
        if 'file' not in request.files:
            return jsonify({"error": "No file provided in the request"}), 400
        
        pdf_file = request.files['file']
        if pdf_file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file must be a PDF"}), 400
        
        # Create a temporary file to store the uploaded PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            pdf_file.save(temp_file)
            temp_file_path = temp_file.name
        
        try:
            # Process the document and store in Neo4j using the original filename
            document_processor = get_document_processor()
            document_id = document_processor.process_document(temp_file_path, original_filename=pdf_file.filename)
            
            # Get the processed document structure
            document_structure = document_processor.get_document_structure(document_id)
            
            # Also get the structured content
            structured_content = document_processor.get_structured_content(document_id)
            
            return jsonify({
                "document_id": document_id,
                "structure": document_structure,
                "structured_content": structured_content
            }), 200
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
            
    except Exception as e:
        print("Error in upload_raw_document:", str(e))
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/extract/enhanced', methods=['POST'])
def extract_enhanced_document_structure():
    """
    Enhanced document structure extraction API endpoint using Claude 3.5 Sonnet.
    
    This endpoint is now the default method for document structure extraction,
    as it produces higher quality results compared to the regular method.
    
    Accepts:
        A multipart/form-data request with a 'file' field containing the PDF
    
    Returns:
        JSON with document_id and the extracted document structure
    """
    try:
        print("Received document structure extraction request")
        if 'file' not in request.files:
            return jsonify({"error": "No file provided in the request"}), 400
        
        pdf_file = request.files['file']
        if pdf_file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file must be a PDF"}), 400
        
        # Create a temporary file to store the uploaded PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            pdf_file.save(temp_file)
            temp_file_path = temp_file.name
        
        try:
            # Get an instance of the document processor
            document_processor = get_document_processor()
            
            # Create a PdfReader instance to get the text content
            from PyPDF2 import PdfReader
            reader = PdfReader(temp_file_path)
            
            # Create a PyMuPDF document instance
            import fitz
            doc = fitz.open(temp_file_path)
            
            # Set original filename
            if pdf_file.filename:
                doc._original_filename = pdf_file.filename
            
            # Process with the enhanced Claude method directly
            structure = document_processor._extract_document_structure_with_enhanced_claude(reader, doc)
            
            # Override title with original filename if provided
            if pdf_file.filename:
                filename_without_ext = os.path.splitext(pdf_file.filename)[0]
                structure["title"] = filename_without_ext
                structure["metadata"]["title"] = structure["title"]
            
            # Generate unique ID for the document
            document_id = str(uuid.uuid4())
            
            # Store structure in Neo4j
            document_processor._store_document_structure(document_id, structure)
            
            # Extract structured content directly from Claude response
            if "claude_structure" in structure:
                structured_content = {"document_structure": structure["claude_structure"]["document_structure"]}
                # Remove the temporary claude_structure from the structure dictionary
                del structure["claude_structure"]
            else:
                # Fallback to a basic structure
                structured_content = {
                    "document_structure": [
                        {
                            "heading": structure["title"],
                            "page_reference": 1,
                            "subheadings": []
                        }
                    ]
                }
            
            # Store both as enhanced and regular structured content for backward compatibility
            document_processor.store_structured_content(document_id, structured_content, is_enhanced=False)
            document_processor.store_structured_content(document_id, structured_content, is_enhanced=True)
            
            # Mark the enhanced content timestamp
            with document_processor.driver.session() as session:
                session.run(
                    """
                    MATCH (d:Document {id: $id})
                    SET d.enhanced_content_timestamp = $timestamp
                    """,
                    id=document_id,
                    timestamp=datetime.now().isoformat()
                )
            
            # Get the processed document structure to return
            document_structure = document_processor.get_document_structure(document_id)
            
            return jsonify({
                "document_id": document_id,
                "structure": document_structure,
                "structured_content": structured_content
            }), 200
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
            
    except Exception as e:
        print(f"Error in extract_enhanced_document_structure: {str(e)}")
        import traceback
        traceback.print_exc()
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
        success = document_processor.delete_document(document_id)
        
        if success:
            return jsonify({"message": f"Document {document_id} deleted successfully"}), 200
        else:
            return jsonify({"error": f"Failed to delete document {document_id}"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print("Error in delete_document_structure:", str(e))
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>/structured', methods=['GET'])
def get_document_structured_content(document_id):
    """
    Get structured content for a document.
    
    By default, returns enhanced content if available, falling back to regular content.
    
    Query parameters:
        enhanced (bool): Whether to get enhanced structured content (default: true)
                        Set to 'false' to explicitly request regular (non-enhanced) content
    """
    try:
        # Check if regular content was explicitly requested (enhanced=false)
        use_enhanced = request.args.get('enhanced', 'true').lower() != 'false'
        
        document_processor = get_document_processor()
        structured_content = document_processor.get_structured_content(document_id, enhanced=use_enhanced)
        return jsonify(structured_content), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"Error in get_document_structured_content: {str(e)}")
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>/enhanced-available', methods=['GET'])
def check_enhanced_structure_available(document_id):
    """
    Check if enhanced document structure is available for a document.
    
    Returns:
        JSON with available flag and timestamp if available
    """
    try:
        document_processor = get_document_processor()
        
        # Check if document exists
        if not document_processor.document_exists(document_id):
            return jsonify({"error": f"Document with ID {document_id} not found"}), 404
            
        # Check if enhanced content is available
        with document_processor.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {id: $id})
                RETURN d.enhanced_structured_content IS NOT NULL as available,
                       d.enhanced_content_timestamp as timestamp
                """,
                id=document_id
            )
            
            record = result.single()
            if not record:
                return jsonify({"available": False}), 200
                
            return jsonify({
                "available": record["available"],
                "timestamp": record["timestamp"] if record["available"] else None
            }), 200
            
    except Exception as e:
        print(f"Error in check_enhanced_structure_available: {str(e)}")
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>/enhanced', methods=['GET'])
def get_document_enhanced_structure(document_id):
    """
    Get enhanced document structure using Claude 3.5 Sonnet.
    
    By default, returns the existing enhanced structure if available.
    
    Query parameters:
        force (bool): Whether to force regeneration of enhanced structure (default: false)
                     Set to 'true' to request fresh processing with Claude 3.5 Sonnet
    
    Returns:
        JSON with enhanced structured content
    """
    try:
        document_processor = get_document_processor()
        
        # First, check if document exists
        if not document_processor.document_exists(document_id):
            return jsonify({"error": f"Document with ID {document_id} not found"}), 404
        
        # Check if regeneration is requested
        force_regenerate = request.args.get('force', 'false').lower() == 'true'
        
        # Try to get existing enhanced content if not forcing regeneration
        if not force_regenerate:
            try:
                enhanced_content = document_processor.get_structured_content(document_id, enhanced=True)
                if enhanced_content.get("enhanced", False) is True:
                    return jsonify(enhanced_content), 200
            except ValueError:
                # If there's no enhanced content yet, continue to generation
                pass
        
        # Check if we have stored the PDF data for regeneration
        pdf_data = document_processor.get_document_pdf_data(document_id)
        
        if not pdf_data:
            return jsonify({
                "error": "PDF data not available for this document. It may have been processed without storing the original PDF."
            }), 404
        
        # Create a temporary file to store the PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_data)
            temp_file_path = temp_file.name
        
        try:
            # Create a PdfReader instance
            from PyPDF2 import PdfReader
            reader = PdfReader(temp_file_path)
            
            # Create a PyMuPDF document instance
            import fitz
            doc = fitz.open(temp_file_path)
            
            # Process with the enhanced Claude method directly
            structure = document_processor._extract_document_structure_with_enhanced_claude(reader, doc)
            
            # Extract structured content from Claude response
            if "claude_structure" in structure:
                enhanced_content = {"document_structure": structure["claude_structure"]["document_structure"]}
                # Remove the temporary claude_structure
                del structure["claude_structure"]
            else:
                # Fallback to existing structured content
                enhanced_content = document_processor.get_structured_content(document_id, enhanced=False)
            
            # Store the enhanced structure with a special flag to indicate it's the enhanced version
            enhanced_content["enhanced"] = True
            enhanced_content["document_id"] = document_id
            enhanced_content["processing_time"] = datetime.now().isoformat()
            
            # Store the enhanced content
            document_processor.store_structured_content(document_id, enhanced_content, is_enhanced=True)
            
            return jsonify(enhanced_content), 200
            
        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)
            
    except Exception as e:
        print(f"Error in get_document_enhanced_structure: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>/page/<int:page_number>', methods=['GET'])
def get_document_page(document_id, page_number):
    """
    Get a page image for a document.
    
    Args:
        document_id: Document ID
        page_number: Page number (1-indexed in URL, converted to 0-indexed for storage)
        
    Returns:
        JSON with page image data
    """
    try:
        document_processor = get_document_processor()
        # Convert from 1-indexed (API) to 0-indexed (storage)
        page_data = document_processor.get_page_image(document_id, page_number - 1)
        return jsonify(page_data), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"Error in get_document_page: {str(e)}")
        return jsonify({"error": str(e)}), 500

@structure_bp.route('/document/<document_id>/visual/<reference>', methods=['GET'])
def get_document_visual_reference(document_id, reference):
    """
    Get a visual reference by its reference ID.
    
    This endpoint retrieves the page image containing the visual reference
    and returns information needed to display it.
    
    Args:
        document_id: Document ID
        reference: Visual reference ID (e.g., "image_001")
        
    Returns:
        JSON with visual reference data including the page image
    """
    try:
        document_processor = get_document_processor()
        
        # Get the structured content to find the visual reference
        structured_content = document_processor.get_structured_content(document_id)
        
        # Find the visual reference in the structured content
        visual_ref = None
        for heading in structured_content["document_structure"]:
            for subheading in heading["subheadings"]:
                for visual in subheading.get("visual_references", []):
                    if visual["image_reference"] == reference:
                        visual_ref = visual
                        break
                if visual_ref:
                    break
            if visual_ref:
                break
        
        if not visual_ref:
            return jsonify({"error": f"Visual reference '{reference}' not found"}), 404
        
        # Get the page image for this visual reference
        page_num = visual_ref["page_reference"] - 1  # Convert to 0-indexed
        page_data = document_processor.get_page_image(document_id, page_num)
        
        # Return the visual reference data with the page image
        return jsonify({
            "visual_reference": visual_ref,
            "page_image": page_data["image"],
            "document_id": document_id
        }), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"Error in get_document_visual_reference: {str(e)}")
        return jsonify({"error": str(e)}), 500