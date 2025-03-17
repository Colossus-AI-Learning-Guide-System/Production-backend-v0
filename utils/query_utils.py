# utils/query_utils.py
def determine_k_from_query(query):
    """
    Determine appropriate k value based on query analysis
    
    Args:
        query: The query text
        
    Returns:
        Appropriate k value for the query
    """
    query_lower = query.lower()
    
    # Check for summarization queries
    if any(word in query_lower for word in ["summarize", "summary", "summarization", "overview", "gist"]):
        return 10  # Large k for summarization
    
    # Check for document-wide queries
    if "entire document" in query_lower or "whole document" in query_lower or "full document" in query_lower:
        return 15  # Very large k for full document questions
    
    # Check for comparison queries
    if any(word in query_lower for word in ["compare", "comparison", "difference", "similarities"]):
        return 5  # Medium k for comparisons
    
    # Check for specific but potentially multi-page concepts
    if any(word in query_lower for word in ["explain", "describe", "elaborate"]):
        return 3  # Small-medium k for concept explanations
    
    # Default for specific questions
    return 1  # Single page for specific questions