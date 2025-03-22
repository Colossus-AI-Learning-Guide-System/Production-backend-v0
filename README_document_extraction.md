# Enhanced Document Structure Extraction API

This module provides an enhanced API for extracting structured information from PDF documents using Claude 3.5 Sonnet. It's designed to accurately identify headings, subheadings, context, and visual elements like figures, tables, and charts.

## Features

- **Raw PDF Uploads**: Direct upload of PDF files without base64 encoding
- **Enhanced Structure Extraction**: Using Claude 3.5 Sonnet with a sophisticated prompt
- **Hierarchical Document Structure**: Extracts headings and their relationships
- **Visual Element Detection**: Identifies figures, tables, and charts with captions
- **Page Mapping**: Tracks page numbers for all structural elements
- **Context Preservation**: Maintains original document text for each section

## API Endpoints

### Enhanced Document Structure Extraction

```
POST /api/structure/extract/enhanced
```

This endpoint accepts raw PDF files and processes them with our enhanced Claude 3.5 Sonnet prompt.

**Request Format**:

- Content-Type: `multipart/form-data`
- Body: PDF file in the `file` field

**Response Format**:

```json
{
  "document_id": "unique-id",
  "structure": {
    "title": "Document Title",
    "headings": ["Heading 1", "Heading 2", ...],
    "hierarchy": {
      "Heading 1": ["Subheading 1.1", "Subheading 1.2"],
      "Heading 2": ["Subheading 2.1"]
    },
    "page_mapping": {
      "Heading 1": 0,
      "Subheading 1.1": 1
    },
    "metadata": {
      "title": "Document Title",
      "page_count": 10,
      "author": "Author Name",
      "file_size_kb": 1024
    }
  },
  "structured_content": {
    "document_structure": [
      {
        "heading": "Heading 1",
        "page_reference": 1,
        "subheadings": [
          {
            "title": "Subheading 1.1",
            "context": "Text content for this subheading...",
            "page_reference": 1,
            "visual_references": [
              {
                "image_caption": "Figure 1: Description",
                "image_reference": "figure_001",
                "page_reference": 2
              }
            ]
          }
        ]
      }
    ]
  }
}
```

## How It Works

1. The API accepts a raw PDF file upload
2. The PDF is processed to extract text and page images
3. Claude 3.5 Sonnet analyzes the document with our specialized prompt
4. The prompt instructs Claude to identify:
   - Hierarchical heading structure
   - Contextual content for each section
   - Visual elements with captions
   - Page references for all elements
5. The extracted structure is stored in Neo4j and returned as JSON

## Prompt Design

The Claude 3.5 Sonnet prompt is designed to handle a variety of document types with high accuracy:

- **Academic papers**: Identifies standard sections like Abstract, Introduction, Methods, Results, Discussion
- **Technical documents**: Extracts Executive Summaries, Requirements, Specifications
- **Reports**: Captures hierarchical section structures with proper relationships
- **Visual content**: Identifies figures, tables, and charts with their captions

The prompt includes specific instructions for detecting:

- Numbered and unnumbered headings
- Typography hints (ALL CAPS, indentation patterns)
- Hierarchical relationships between sections
- Page references for all elements
- Visual element captions and references

## Usage Example

### Python Client

```python
import requests

def extract_document_structure(pdf_path):
    """Extract document structure from a PDF file"""

    # Prepare file for upload
    files = {'file': open(pdf_path, 'rb')}

    # Make API request
    response = requests.post(
        "http://localhost:5000/api/structure/extract/enhanced",
        files=files
    )

    # Close file
    files['file'].close()

    # Return result if successful
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.text}")
        return None

# Example usage
result = extract_document_structure("example.pdf")
if result:
    document_id = result["document_id"]
    structure = result["structure"]
    structured_content = result["structured_content"]

    # Access extracted heading structure
    for heading in structure["headings"]:
        print(f"Heading: {heading}")
        for subheading in structure["hierarchy"].get(heading, []):
            print(f"  - {subheading}")

    # Access visual elements
    for section in structured_content["document_structure"]:
        for subheading in section.get("subheadings", []):
            for visual in subheading.get("visual_references", []):
                print(f"Visual: {visual['image_caption']} on page {visual['page_reference']}")
```

### Command Line

You can also use the provided `example_client.py` script:

```
python example_client.py /path/to/document.pdf [output.json]
```

This will extract the document structure and save it to a JSON file.

## Notes

- The API is optimized for PDFs with clearly structured content
- It can handle documents with different heading styles and numbering schemes
- Visual element detection is based on explicit references in the text (e.g., "Figure 1")
- The raw PDF approach avoids the overhead of base64 encoding/decoding
