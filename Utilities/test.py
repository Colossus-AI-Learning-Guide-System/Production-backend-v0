import torch
print(torch.cuda.is_available())  # Should return True
print(torch.backends.cudnn.version())  # Should return a version number




# from flask import Flask, request, jsonify
# from flask_cors import CORS
# import base64
# import os
# import sys
# from byaldi import RAGMultiModalModel
# from claudette import *
# from PyPDF2 import PdfReader
# import tempfile
# from dotenv import load_dotenv

# # Better Live Share detection
# IS_LIVE_SHARE = any([
#     os.environ.get("VSLS_SESSION_ID") is not None,  # Check for VS Code Live Share env variable
#     os.path.exists("/.vsls.json"),                   # Check for Live Share config file
#     "vsls:" in os.getcwd(),                          # Check if current directory has vsls prefix
#     "liveshare" in os.getcwd().lower(),              # Backup check for liveshare in path
#     len(sys.argv) > 1 and "liveshare" in sys.argv[1].lower()  # Check command line args
# ])

# print(f"Current working directory: {os.getcwd()}")
# print(f"Live Share detection result: {IS_LIVE_SHARE}")

# # Handle environment variables based on the session type
# if IS_LIVE_SHARE:
#     # In Live Share, prompt for credentials
#     print("⚠️ Live Share session detected ⚠️")
#     print("API keys will be requested interactively to protect your credentials.")
    
#     # Get credentials from environment first (if set during this session)
#     # or prompt the user
#     HF_TOKEN = os.environ.get("HF_TOKEN")
#     if not HF_TOKEN:
#         HF_TOKEN = input("Enter your Hugging Face token: ")
#         os.environ["HF_TOKEN"] = HF_TOKEN
    
#     ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
#     if not ANTHROPIC_API_KEY:
#         ANTHROPIC_API_KEY = input("Enter your Anthropic API key: ")
#         os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
# else:
#     # Normal local execution - use .env file
#     print("Loading credentials from .env file...")
#     load_dotenv()
#     HF_TOKEN = os.getenv("HF_TOKEN")
#     ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# # Check if the environment variables are set
# if not HF_TOKEN or not ANTHROPIC_API_KEY:
#     raise ValueError("Missing required API keys. Please check your credentials.")

# # Set HF_TOKEN as environment variable
# os.environ["HF_TOKEN"] = HF_TOKEN

# app = Flask(__name__)
# CORS(app)

# # Load Byaldi RAG model
# RAG = RAGMultiModalModel.from_pretrained("vidore/colpali-v1.2", verbose=1)

# @app.route('/upload', methods=['POST'])
# def upload_files():
#     try:
#         print("Received upload request")  # Log the incoming request
#         data = request.json
#         files = data.get('files', [])
#         if not files:
#             return jsonify({"error": "No files provided"}), 400

#         # Save files temporarily (optional)
#         for idx, file_base64 in enumerate(files):
#             print(f"Processing file {idx + 1}")  # Log file processing
#             file_bytes = base64.b64decode(file_base64)  # Decode base64 to binary

#             # Save the binary data to a temporary file
#             with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
#                 temp_file.write(file_bytes)
#                 temp_file_path = temp_file.name

#             try:
#                 # Verify the file is a valid PDF
#                 reader = PdfReader(temp_file_path)
#                 print(f"File {idx + 1} is a valid PDF with {len(reader.pages)} pages.")

#                 # Index the document
#                 print("Indexing the document...")  # Log indexing
#                 RAG.index(
#                     input_path=temp_file_path,  # Use the temporary file for indexing
#                     index_name="attention",
#                     store_collection_with_index=True,
#                     overwrite=True
#                 )
#             finally:
#                 # Ensure the temporary file is deleted after processing
#                 os.unlink(temp_file_path)

#         return jsonify({"message": "Files uploaded and indexed successfully"}), 200
#     except Exception as e:
#         print("Error in upload_files:", str(e))  # Log the error
#         return jsonify({"error": str(e)}), 500

# @app.route('/query', methods=['POST'])
# def handle_query():
#     try:
#         data = request.json
#         query = data.get('query', '')
#         if not query:
#             return jsonify({"error": "Query is required"}), 400

#         # Query the RAG model
#         results = RAG.search(query, k=1)

#         # Check if results are valid
#         if not results or len(results) == 0:
#             return jsonify({"error": "No results found"}), 404

#         # Extract the image from the RAG result
#         result = results[0]
#         image_bytes = base64.b64decode(result.base64)  # Decode the base64 image

#         # Pass the image and query to Claude
#         os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY  # Set the API key
#         chat = Chat(models[1])
#         claude_response = chat([image_bytes, query])

#         print("Claude response type:", type(claude_response))  # Log the type of Claude's response
#         print("Claude response attributes:", dir(claude_response))  # Log all attributes of Claude's response
#         print("Claude response content:", claude_response.content)  # Log the content of Claude's response

#         # Extract text content from Claude's response
#         claude_content = ""
#         if hasattr(claude_response, "content"):  # Check if the response has a "content" attribute
#             for block in claude_response.content:
#                 if hasattr(block, "text"):  # Check if the block has a "text" attribute
#                     claude_content += block.text + "\n"
#         else:
#             claude_content = "No content available"

#         # Return the raw Claude response without parsing
#         return jsonify({"response": claude_content}), 200
#     except Exception as e:
#         print("Error in handle_query:", str(e))  # Log the error
#         return jsonify({"error": str(e)}), 500

# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5001)