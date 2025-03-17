"""API blueprints for the application"""
from flask import Blueprint

# Create Blueprints for the different API sections
document_bp = Blueprint('document', __name__)
query_bp = Blueprint('query', __name__)
structure_bp = Blueprint('structure', __name__)

# Import routes after creating blueprints to avoid circular imports
from api.document_routes import *
from api.query_routes import *
from api.structure_routes import *

__all__ = ["document_bp", "query_bp", "structure_bp"]