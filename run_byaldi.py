# run_byaldi.py
from byaldi import RAGMultiModalModel

# Load the pretrained model
RAG = RAGMultiModalModel.from_pretrained("vidore/colqwen2-v1.0")

# Create an index from a directory of documents (e.g., PDFs or images)
RAG.index(
    input_path="D:/Users/Sudesh/Documents/inputdocs/FundamentalConceptsofMachineLearning.pdf",  # Path to your documents
    index_name="my_index",  # Name of the index
    store_collection_with_index=False,  # Whether to store base64 encoded documents with the index
    doc_ids=[0, 1, 2],  # Optional: Document IDs
    metadata=[{"author": "John Doe", "date": "2021-01-01"}],  # Optional: Metadata for each document
    overwrite=True  # Overwrite if the index already exists
)

# Perform a search
query = "What are access modifiers?"
results = RAG.search(query, k=3)

# Print the search results
for result in results:
    print(f"Doc ID: {result['doc_id']}, Page: {result['page_num']}, Score: {result['score']}")
    print("Metadata:", result['metadata'])
