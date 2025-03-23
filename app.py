"""
Main Flask application for Document RAG System
This application provides API endpoints for document processing, 
RAG query functionality, and document structure visualization.
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import os
import torch

# Import configurations
from config.settings import get_settings

# Import models 
from models.rag_models import init_rag_model
from models.pixtral_models import start_memory_management

# Import services
from services.document_service import init_document_processor, close_document_processor

# Import API routes
from api import document_bp, query_bp, structure_bp

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Register blueprints
app.register_blueprint(document_bp, url_prefix='/api/document')
app.register_blueprint(query_bp, url_prefix='/api/query')
app.register_blueprint(structure_bp, url_prefix='/api/structure')

# Compatibility routes - to avoid breaking existing code
# These simply forward to the proper blueprint routes
from flask import redirect

@app.route('/unified-upload', methods=['POST'])
def compat_unified_upload():
    """Compatibility endpoint for unified-upload"""
    return redirect('/api/document/unified-upload')

@app.route('/upload', methods=['POST'])
def compat_upload():
    """Compatibility endpoint for upload"""
    return redirect('/api/document/upload')

@app.route('/query', methods=['POST'])
def compat_query():
    """Compatibility endpoint for query"""
    return redirect('/api/query/query')

@app.route('/indexing-status/<document_id>', methods=['GET'])
def compat_indexing_status(document_id):
    """Compatibility endpoint for indexing-status"""
    return redirect(f'/api/document/indexing-status/{document_id}')

@app.route('/documents', methods=['GET'])
def compat_documents():
    """Compatibility endpoint for documents"""
    return redirect('/api/document/documents')

@app.route('/structure/upload', methods=['POST'])
def compat_structure_upload():
    """Compatibility endpoint for structure/upload"""
    return redirect('/api/structure/upload')

@app.route('/structure/documents', methods=['GET'])
def compat_structure_documents():
    """Compatibility endpoint for structure/documents"""
    return redirect('/api/structure/documents')

@app.route('/structure/document/<document_id>', methods=['GET', 'DELETE'])
def compat_structure_document(document_id):
    """Compatibility endpoint for structure/document/:id"""
    return redirect(f'/api/structure/document/{document_id}')

@app.route('/structure/document/<document_id>/heading', methods=['GET'])
def compat_structure_document_heading(document_id):
    """Compatibility endpoint for structure/document/:id/heading"""
    return redirect(f'/api/structure/document/{document_id}/heading?{request.query_string.decode()}')

@app.route('/document/<document_id>/original-pdf', methods=['GET'])
def compat_original_pdf(document_id):
    """Compatibility endpoint for document/:id/original-pdf"""
    return redirect(f'/api/document/document/{document_id}/original-pdf')

# Initialize application components
settings = get_settings()
rag_model = init_rag_model(settings.RAG_MODEL_NAME)
document_processor = init_document_processor()

# Check for GPU and initialize Pixtral memory management
if torch.cuda.is_available() and hasattr(settings, 'USE_LOCAL_PIXTRAL') and settings.USE_LOCAL_PIXTRAL:
    print(f"GPU detected: {torch.cuda.get_device_name(0)}")
    print(f"Available VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
    start_memory_management()
else:
    print("No CUDA GPU detected, will use CPU or API for processing")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    gpu_info = {
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count(),
    }
    
    if gpu_info["cuda_available"]:
        gpu_info["device_name"] = torch.cuda.get_device_name(0)
        gpu_info["device_capability"] = torch.cuda.get_device_capability(0)
        gpu_info["total_memory_gb"] = torch.cuda.get_device_properties(0).total_memory / 1024**3
    
    return jsonify({
        "status": "healthy",
        "gpu_info": gpu_info,
        "models": {
            "rag_model": settings.RAG_MODEL_NAME,
            "local_pixtral": hasattr(settings, 'USE_LOCAL_PIXTRAL') and settings.USE_LOCAL_PIXTRAL
        }
    })

# Application shutdown handler
@app.teardown_appcontext
def shutdown_handler(exception=None):
    """Close connections when the app shuts down"""
    close_document_processor()

if __name__ == '__main__':
    app.run(host=settings.HOST, port=settings.PORT)