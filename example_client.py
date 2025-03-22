#!/usr/bin/env python3
"""
Example client for document structure extraction API using raw PDF files
"""

import requests
import sys
import json
import os
from pprint import pprint

# API base URL - adjust as needed
API_BASE_URL = "http://localhost:5000/api/structure"

def extract_document_structure_enhanced(pdf_path):
    """
    Extract document structure using the enhanced Claude 3.5 Sonnet API endpoint
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Document structure as returned by the API
    """
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        return None
        
    # Check if file is a PDF
    if not pdf_path.lower().endswith('.pdf'):
        print(f"Error: File must be a PDF: {pdf_path}")
        return None
    
    # Prepare the file for upload
    files = {'file': (os.path.basename(pdf_path), open(pdf_path, 'rb'), 'application/pdf')}
    
    print(f"Uploading {pdf_path} for enhanced document structure extraction...")
    
    # Make the API request
    response = requests.post(f"{API_BASE_URL}/extract/enhanced", files=files)
    
    # Close the file
    files['file'][1].close()
    
    # Check if the request was successful
    if response.status_code == 200:
        result = response.json()
        print(f"Document processed successfully with ID: {result['document_id']}")
        return result
    else:
        error_message = response.json().get('error', 'Unknown error')
        print(f"Error extracting document structure: {error_message}")
        return None

def save_structure_to_json(structure, output_path):
    """Save document structure to a JSON file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(structure, f, indent=2, ensure_ascii=False)
    print(f"Structure saved to {output_path}")

def main():
    """Main entry point"""
    # Check if PDF path is provided
    if len(sys.argv) < 2:
        print("Usage: python example_client.py <pdf_path> [output_json_path]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Default output path is the same as input with .json extension
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(pdf_path)[0] + "_structure.json"
    
    # Extract document structure
    result = extract_document_structure_enhanced(pdf_path)
    
    if result:
        # Save structure to JSON
        save_structure_to_json(result, output_path)
        
        # Print a summary
        print("\nDocument structure summary:")
        print(f"Title: {result['structure'].get('title', 'Untitled')}")
        print(f"Page count: {result['structure'].get('metadata', {}).get('page_count', 'Unknown')}")
        
        # Print headings
        headings = result['structure'].get('headings', [])
        print(f"Found {len(headings)} main headings:")
        for heading in headings[:5]:  # Print first 5 headings
            print(f"- {heading}")
        
        if len(headings) > 5:
            print(f"... and {len(headings) - 5} more")
            
        # Print info about structured content
        structured_content = result.get('structured_content', {})
        doc_structure = structured_content.get('document_structure', [])
        print(f"Structured content has {len(doc_structure)} main sections")
        
        # Print total count of visual references
        visual_count = 0
        for section in doc_structure:
            for subheading in section.get('subheadings', []):
                visual_count += len(subheading.get('visual_references', []))
        
        print(f"Found {visual_count} visual references (figures, tables, charts)")

if __name__ == "__main__":
    main() 