# models/rag_models.py
from byaldi import RAGMultiModalModel

def init_rag_model(model_name, verbose=1):
    """
    Initialize the RAG model with the given model name.
    
    Args:
        model_name: The name of the model to load
        verbose: Verbosity level (0=silent, 1=normal, 2=verbose)
    
    Returns:
        The initialized RAG model
    """
    print(f"Initializing RAG model {model_name}...")
    return RAGMultiModalModel.from_pretrained(model_name, verbose=verbose)