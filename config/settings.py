# config/settings.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    """Application settings loaded from environment variables"""
    
    def __init__(self):
        # API keys
        self.HF_TOKEN = os.getenv("HF_TOKEN")
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        self.HF_API_TOKEN = os.getenv("HF_API_TOKEN")  # For Pixtral API calls
        
        # Set HF_TOKEN as environment variable for byaldi
        if self.HF_TOKEN:
            os.environ["HF_TOKEN"] = self.HF_TOKEN
            
        # Neo4j configuration
        self.NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
        self.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
        
        # Server configuration
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.PORT = int(os.getenv("PORT", "5002"))
        
        # Model configuration
        self.RAG_MODEL_NAME = os.getenv("RAG_MODEL_NAME", "vidore/colpali-v1.2")
        self.CLAUDE_MAX_K = int(os.getenv("CLAUDE_MAX_K", "4"))
        
        # Check required settings
        self._validate_settings()
    
    def _validate_settings(self):
        """Validate that required settings are present"""
        if not self.HF_TOKEN:
            raise ValueError("HF_TOKEN environment variable is not set")
        if not self.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

# Create a singleton instance
_settings = None

def get_settings():
    """Get the application settings"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings