# utils/file_utils.py
import os
import tempfile
import base64

def save_temp_file(file_base64, suffix=".pdf"):
    """
    Save base64 data to a temporary file
    
    Args:
        file_base64: Base64-encoded file data
        suffix: File suffix
        
    Returns:
        Path to the temporary file
    """
    file_bytes = base64.b64decode(file_base64)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(file_bytes)
        return temp_file.name

def clean_temp_file(file_path):
    """
    Clean up a temporary file
    
    Args:
        file_path: Path to the file to clean up
    """
    if os.path.exists(file_path):
        os.unlink(file_path)