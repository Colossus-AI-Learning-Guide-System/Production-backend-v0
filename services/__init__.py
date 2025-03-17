# services/__init__.py
from .document_service import init_document_processor
from .indexing_service import index_for_rag, get_all_available_documents
from .query_service import process_query, choose_model_for_query

__all__ = [
    "init_document_processor", 
    "index_for_rag", 
    "get_all_available_documents", 
    "process_query", 
    "choose_model_for_query"
]