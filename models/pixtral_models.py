# models/pixtral_models.py
import base64
import os
import requests
import time
from typing import List, Dict, Any, Optional
import threading
import torch
from threading import Lock

# Global variables for Pixtral model
pixtral_processor = None
pixtral_model = None
pixtral_lock = Lock()
pixtral_last_used = 0

def process_with_pixtral_api(query: str, results: List) -> Dict[str, Any]:
    """
    Process query using Pixtral API for larger k values.
    Returns a dictionary with the API response or error details.
    
    Args:
        query: The query text
        results: List of RAG results with base64-encoded images
        
    Returns:
        A dictionary containing the success status and either the response or error
    """
    try:
        # Prepare base64 images for API
        api_images = [result.base64 for result in results]
        
        # Prepare the prompt for Pixtral
        pixtral_prompt = f"""You are analyzing {len(api_images)} pages from a document. 
Please answer the following question based on the content of these pages:

{query}

Provide a comprehensive answer based solely on the provided pages."""

        # Check if HF API token is available
        from config.settings import get_settings
        settings = get_settings()
        if not settings.HF_API_TOKEN:
            return {
                "success": False,
                "error": "HF_API_TOKEN not configured. Cannot use Pixtral API."
            }
            
        # Call Hugging Face Inference API
        API_URL = "https://api-inference.huggingface.co/models/Weyaxi/Pixtral-12B-v0.1"
        headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}
        
        payload = {
            "inputs": {
                "prompt": pixtral_prompt,
                "images": api_images
            },
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40
            }
        }
        
        response = requests.post(API_URL, headers=headers, json=payload)
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"API returned status code {response.status_code}: {response.text}"
            }
            
        result = response.json()
        
        if isinstance(result, dict) and "error" in result:
            return {
                "success": False,
                "error": f"Pixtral API error: {result['error']}"
            }
            
        return {
            "success": True,
            "response": result[0]["generated_text"]
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Error processing with Pixtral API: {str(e)}"
        }

def load_pixtral_model():
    """
    Load the Pixtral model if it's not already loaded.
    Uses 8-bit quantization for memory efficiency.
    
    Returns:
        True if successful, False if failed
    """
    global pixtral_processor, pixtral_model, pixtral_last_used
    
    # Thread safety
    with pixtral_lock:
        if pixtral_processor is None or pixtral_model is None:
            try:
                print("Loading Pixtral-12B model with 8-bit quantization...")
                
                # Import required libraries (only when needed)
                import gc
                from transformers import AutoProcessor, AutoModelForCausalLM
                
                # Clean memory
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                # Load processor
                pixtral_processor = AutoProcessor.from_pretrained(
                    "Weyaxi/Pixtral-12B-v0.1", 
                    trust_remote_code=True
                )
                
                # Load model with 8-bit quantization for memory efficiency
                pixtral_model = AutoModelForCausalLM.from_pretrained(
                    "Weyaxi/Pixtral-12B-v0.1",
                    load_in_8bit=True,  # Use 8-bit quantization for 24GB VRAM
                    device_map="auto",
                    trust_remote_code=True
                )
                
                # Optimize for inference
                pixtral_model.config.use_cache = True
                print("Pixtral-12B model loaded successfully")
            except Exception as e:
                print(f"Error loading Pixtral model: {str(e)}")
                return False
        
        # Update last used timestamp
        pixtral_last_used = time.time()
        return True

def unload_pixtral_if_idle(max_idle_time=3600):
    """
    Unload Pixtral model if it hasn't been used for a while
    
    Args:
        max_idle_time: Maximum idle time in seconds before unloading (default: 1 hour)
    """
    global pixtral_processor, pixtral_model, pixtral_last_used
    
    with pixtral_lock:
        if pixtral_model is not None:
            current_time = time.time()
            
            # If model has been idle for too long
            if current_time - pixtral_last_used > max_idle_time:
                print("Unloading idle Pixtral model to free memory")
                del pixtral_processor
                del pixtral_model
                pixtral_processor = None
                pixtral_model = None
                
                # Clean memory
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

def process_with_pixtral_local(query, results):
    """
    Process query using local Pixtral model
    
    Args:
        query: The query text
        results: List of RAG results with base64-encoded images
        
    Returns:
        A dictionary containing the success status and either the response or error
    """
    global pixtral_processor, pixtral_model
    
    try:
        # Import required libraries only when needed
        from PIL import Image
        import io
        
        # Load model if not already loaded
        if not load_pixtral_model():
            return {
                "success": False,
                "error": "Failed to load Pixtral model"
            }
        
        # Convert base64 images to PIL images
        pil_images = []
        for result in results:
            image_bytes = base64.b64decode(result.base64)
            pil_image = Image.open(io.BytesIO(image_bytes))
            pil_images.append(pil_image)
        
        # Prepare prompt
        pixtral_prompt = f"""You are analyzing {len(pil_images)} pages from a document. 
Please answer the following question based on the content of these pages:

{query}

Provide a comprehensive answer based solely on the provided pages."""
        
        # Process with Pixtral
        inputs = pixtral_processor(
            text=pixtral_prompt,
            images=pil_images,
            return_tensors="pt"
        ).to("cuda" if torch.cuda.is_available() else "cpu")
        
        # Generate with optimized parameters
        with torch.inference_mode():
            output = pixtral_model.generate(
                **inputs,
                max_new_tokens=768,
                do_sample=True,
                temperature=0.7,
                top_p=0.95,
                top_k=40
            )
        
        # Decode response
        decoded_output = pixtral_processor.decode(output[0], skip_special_tokens=True)
        pixtral_response = decoded_output.split(pixtral_prompt)[-1].strip()
        
        # Clean up tensors explicitly
        del inputs, output
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        return {
            "success": True,
            "response": pixtral_response
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Error processing with local Pixtral: {str(e)}"
        }

# Start memory management thread
def start_memory_management():
    """Start a background thread to manage Pixtral model memory"""
    def memory_management_thread():
        while True:
            # Check every 15 minutes
            time.sleep(900)
            
            # Unload Pixtral if idle for more than 1 hour
            unload_pixtral_if_idle(3600)
    
    # Start the thread
    thread = threading.Thread(target=memory_management_thread)
    thread.daemon = True
    thread.start()
    print("Started Pixtral memory management thread")