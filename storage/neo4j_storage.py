import fitz  # PyMuPDF
import re
from PyPDF2 import PdfReader
from PIL import Image
import io
import base64
import os
import tempfile
import uuid
import json
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase
from datetime import datetime
import anthropic  # Add anthropic import
from config.settings import get_settings

class Neo4jDocumentProcessor:
    """
    Document processor that stores document structure in Neo4j.
    """
    
    def __init__(self, uri, username, password):
        """
        Initialize the Neo4j document processor.
        
        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
        """
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        # Get settings for API keys
        self.settings = get_settings()
        # Initialize Anthropic client
        self.claude_client = anthropic.Anthropic(api_key=self.settings.ANTHROPIC_API_KEY)
    
    def close(self):
        """Close the Neo4j driver connection."""
        self.driver.close()
    
    def process_document(self, pdf_path: str, original_filename: str = None) -> str:
        """
        Process a PDF document and store its structure in Neo4j.
        
        Args:
            pdf_path: Path to the PDF file
            original_filename: Original filename (optional)
            
        Returns:
            document_id: Unique identifier for the processed document
        """
        try:
            print(f"Starting document processing for {pdf_path}")
            
            # Generate unique ID for the document
            document_id = str(uuid.uuid4())
            
            # Extract text content with PyPDF2
            reader = PdfReader(pdf_path)
            print(f"PDF has {len(reader.pages)} pages")
            
            # Use PyMuPDF for rendering pages
            doc = fitz.open(pdf_path)
            
            # Store original filename as a property of the document object
            if original_filename:
                # Create a temporary attribute to store the original filename
                doc._original_filename = original_filename
                print(f"Using original filename: {original_filename}")
            
            # Process document structure using Enhanced Claude method
            structure = self._extract_document_structure_with_enhanced_claude(reader, doc)
            
            # Skip the regular structure extraction to save API costs
            # regular_structure = self._extract_document_structure_with_claude(reader, doc)
            
            # Override title with original filename if provided
            if original_filename:
                filename_without_ext = os.path.splitext(original_filename)[0]
                structure["title"] = filename_without_ext
                structure["metadata"]["title"] = structure["title"]
                print(f"Title set to original filename: {structure['title']}")
            
            print(f"Extracted {len(structure['headings'])} headings from enhanced structure")
            
            # Store PDF data for future reprocessing if needed
            self._store_pdf_data(document_id, pdf_path)
            
            # Store structure in Neo4j
            self._store_document_structure(document_id, structure)
            print(f"Document structure stored in Neo4j with ID: {document_id}")
            
            # Extract structured content from the enhanced Claude response
            if "claude_structure" in structure:
                enhanced_content = {"document_structure": structure["claude_structure"]["document_structure"]}
                # Remove the temporary claude_structure
                del structure["claude_structure"]
            else:
                # Create basic structure if enhanced Claude didn't return a proper structure
                enhanced_content = {
                    "document_structure": [
                        {
                            "heading": structure["title"],
                            "page_reference": 1,
                            "subheadings": []
                        }
                    ]
                }
            
            # Create a copy of the enhanced content for the regular content to maintain backward compatibility
            regular_content = enhanced_content.copy()
            
            # Store structured content in Neo4j (both as regular and enhanced for backward compatibility)
            self.store_structured_content(document_id, regular_content, is_enhanced=False)
            self.store_structured_content(document_id, enhanced_content, is_enhanced=True)
            
            # Mark the enhanced content timestamp
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (d:Document {id: $id})
                    SET d.enhanced_content_timestamp = $timestamp
                    """,
                    id=document_id,
                    timestamp=datetime.now().isoformat()
                )
            
            print(f"Enhanced structured content extracted and stored with {len(enhanced_content['document_structure'])} main headings")
            
            return document_id
            
        except Exception as e:
            print(f"Error processing document: {str(e)}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Error processing document: {str(e)}")
    
    def process_base64_document(self, base64_data: str, original_filename: str = None) -> str:
        """
        Process a PDF document from base64 encoded data.
        
        Args:
            base64_data: Base64 encoded PDF data
            original_filename: Original filename of the document (optional)
            
        Returns:
            document_id: Unique identifier for the processed document
        """
        try:
            # Decode base64 data
            pdf_data = base64.b64decode(base64_data)
            
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                temp_file.write(pdf_data)
                temp_file_path = temp_file.name
            
            try:
                # Generate a unique ID
                document_id = str(uuid.uuid4())
                
                # Process the PDF file with the original filename if provided
                document_id = self.process_document(temp_file_path, original_filename)
                
                # Store the raw PDF data directly
                with self.driver.session() as session:
                    session.run(
                        """
                        MATCH (d:Document {id: $id})
                        SET d.pdf_data = $pdf_data
                        """,
                        id=document_id,
                        pdf_data=base64_data
                    )
                    
                return document_id
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            raise Exception(f"Error processing base64 document: {str(e)}")
    
    def _extract_document_structure_with_claude(self, reader: PdfReader, doc: fitz.Document) -> Dict[str, Any]:
        """
        Extract document structure using Claude API.
        
        Args:
            reader: PyPDF2 PdfReader object
            doc: PyMuPDF document object
            
        Returns:
            Document structure dictionary generated by Claude
        """
        # Structure to store document hierarchy
        structure = {
            "headings": [],
            "hierarchy": {},
            "page_mapping": {},
            "page_images": {},
            "metadata": {}  # Metadata dictionary
        }
        
        # Extract document title and metadata
        try:
            # Get the filename from the document path
            if hasattr(doc, 'name') and doc.name:
                file_path = doc.name
                file_name = os.path.basename(file_path)
                # Remove extension
                file_name_without_ext = os.path.splitext(file_name)[0]
                structure["title"] = file_name_without_ext
                structure["metadata"]["title"] = structure["title"]
                print(f"Using filename as title: {structure['title']}")
            else:
                # Fallback to extracting from PDF metadata or content
                if doc.metadata and doc.metadata.get('title'):
                    structure["title"] = doc.metadata.get('title')
                    structure["metadata"]["title"] = structure["title"]
                else:
                    # Try to extract title from first page
                    first_page_text = reader.pages[0].extract_text()
                    first_lines = first_page_text.split('\n')
                    if first_lines and len(first_lines[0]) < 100:  # Reasonable title length
                        structure["title"] = first_lines[0].strip()
                        structure["metadata"]["title"] = structure["title"]
        except Exception as e:
            print(f"Error extracting document title from filename: {str(e)}")
            # Fallback to a default title
            structure["title"] = f"Document {uuid.uuid4().hex[:8]}"
            structure["metadata"]["title"] = structure["title"]
        
        # Extract basic metadata
        try:
            structure["metadata"]["file_size"] = os.path.getsize(doc.name)
            structure["metadata"]["file_size_kb"] = round(structure["metadata"]["file_size"] / 1024, 2)
        except Exception as e:
            print(f"Error extracting file size: {str(e)}")
            structure["metadata"]["file_size"] = 0
            structure["metadata"]["file_size_kb"] = 0
        
        # Extract additional PDF metadata
        try:
            if doc.metadata:
                structure["metadata"]["author"] = doc.metadata.get('author', 'Unknown')
                structure["metadata"]["keywords"] = doc.metadata.get('keywords', '')
                structure["metadata"]["subject"] = doc.metadata.get('subject', '')
                structure["metadata"]["producer"] = doc.metadata.get('producer', '')
                structure["metadata"]["creator"] = doc.metadata.get('creator', '')
                
                # Creation date
                creation_date = doc.metadata.get('creationDate', None)
                if creation_date:
                    # Try to parse PDF date format (D:YYYYMMDDHHmmSS)
                    if isinstance(creation_date, str) and creation_date.startswith('D:'):
                        date_str = creation_date[2:16]  # Extract YYYYMMDDHHMMSS
                        try:
                            from datetime import datetime
                            parsed_date = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                            structure["metadata"]["creation_date"] = parsed_date.isoformat()
                        except:
                            structure["metadata"]["creation_date"] = creation_date
                    else:
                        structure["metadata"]["creation_date"] = creation_date
        except Exception as e:
            print(f"Error extracting document metadata: {str(e)}")
        
        # Store page count
        structure["metadata"]["page_count"] = len(reader.pages)
        
        # Extract full text from all pages to send to Claude
        full_text = ""
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            page_text = page.extract_text()
            full_text += f"\n\n--- Page {page_num + 1} ---\n\n{page_text}"
            
            # Render the page as an image for later use
            pix = doc.load_page(page_num).get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Resize image if too large
            max_width = 1200
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.LANCZOS)
            
            # Convert to base64 for storage
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            # Store the page image
            structure["page_images"][page_num] = img_str
        
        # Define the prompt for Claude to analyze document structure
        prompt = f"""
You are an expert document analyzer. You need to analyze the text from a PDF document and extract its hierarchical structure.

I will provide you with the full text content of a document. Your task is to:

1. Identify the main headings and subheadings in the document
2. Organize them in a hierarchical structure
3. Extract the contextual text for each heading/subheading
4. Identify any visual elements like images, figures, tables, or charts mentioned in the text
5. Return all the information in a structured JSON format that MUST BE VALID JSON

IMPORTANT RULES:
- Do NOT generate, summarize, or add any content - only use exactly what you find in the document
- Do NOT modify the original text content in any way
- For each section, include the exact page number where it starts
- Some documents may lack clear headings or have unusual formatting - do your best to identify the logical structure
- If the document has no clear headings, create a simple structure with the title and page-based sections
- For visual references, only include those explicitly mentioned in the text (like "Figure 1", "Table 2", etc.)
- Ensure your response is valid, well-formed JSON that can be parsed

The response should be in the following JSON format:

{{
  "document_structure": [
    {{
      "heading": "Main Heading 1",
      "page_reference": 1,
      "subheadings": [
        {{
          "title": "Subheading 1.1",
          "context": "The exact text content under this subheading...",
          "page_reference": 1,
          "visual_references": [
            {{
              "image_caption": "Figure 1: Description of figure as it appears in the text",
              "image_reference": "image_001",
              "page_reference": 1
            }}
          ]
        }}
      ]
    }}
  ]
}}

Here is the document text to analyze:

{full_text}

Respond ONLY with the JSON output. Do not include any explanations or additional text. Ensure your JSON is properly formatted and valid.
"""
        
        # Call Claude API to process the document structure
        print(f"Sending document to Claude for structure analysis (text length: {len(full_text)} characters)")
        try:
            # Set a larger max_tokens to ensure we get complete output
            response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=8192,  # Maximum allowed for Claude 3.5 Sonnet
                temperature=0,
                system="You are an expert document structure analyzer that extracts document structure in JSON format. You never add, modify or summarize content. You always provide valid, parseable JSON output.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the response content
            claude_response = response.content[0].text
            
            # Properly extract and fix JSON from the response
            json_str = self._extract_and_fix_json(claude_response)
            
            # Parse the JSON response
            try:
                claude_structure = json.loads(json_str)
                print(f"Claude successfully extracted document structure with {len(claude_structure['document_structure'])} main headings")
                
                # Now map the Claude structure to our expected format
                for heading_entry in claude_structure["document_structure"]:
                    heading_text = heading_entry["heading"]
                    page_reference = heading_entry["page_reference"] - 1  # Convert to 0-indexed
                    
                    # Add to our structure
                    structure["headings"].append(heading_text)
                    structure["hierarchy"][heading_text] = []
                    structure["page_mapping"][heading_text] = page_reference
                    
                    # Process subheadings
                    if "subheadings" in heading_entry:
                        for subheading_entry in heading_entry["subheadings"]:
                            subheading_text = subheading_entry["title"]
                            subheading_page = subheading_entry["page_reference"] - 1  # Convert to 0-indexed
                            
                            # Add to our hierarchy
                            structure["hierarchy"][heading_text].append(subheading_text)
                            structure["page_mapping"][subheading_text] = subheading_page
                
                # If Claude didn't find any headings, create a simple structure with the document title
                if not structure["headings"]:
                    print("WARNING: Claude didn't detect any headings. Creating simple title-based structure.")
                    self._create_simple_structure(structure, reader)
                
                # Store the original Claude structure for later use in extracting structured content
                structure["claude_structure"] = claude_structure
                
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing Claude response as JSON or missing key: {str(e)}")
                print(f"JSON string sample: {json_str[:200]}...")
                
                # Create a basic document structure using the title and page structure
                print("Creating fallback document structure from PDF content")
                self._create_simple_structure(structure, reader)
                
                # Try to salvage any partial structure from Claude's response
                try:
                    fallback_structure = self._create_default_structure_with_partial_content(json_str)
                    fallback_json = json.loads(fallback_structure)
                    if fallback_json["document_structure"] and len(fallback_json["document_structure"]) > 1:
                        print(f"Successfully salvaged partial structure with {len(fallback_json['document_structure'])} headings")
                        structure["claude_structure"] = fallback_json
                    else:
                        structure["claude_structure"] = self._generate_page_based_structure(reader)
                except Exception as fallback_error:
                    print(f"Error creating fallback structure: {str(fallback_error)}")
                    structure["claude_structure"] = self._generate_page_based_structure(reader)
        
        except Exception as e:
            print(f"Error calling Claude API: {str(e)}")
            # Create a basic document structure using the title
            title = structure["title"]
            structure["headings"].append(title)
            structure["hierarchy"][title] = []
            structure["page_mapping"][title] = 0
            
            # Create a basic Claude structure for return
            structure["claude_structure"] = {
                "document_structure": [
                    {
                        "heading": title,
                        "page_reference": 1,
                        "subheadings": []
                    }
                ]
            }
            
            # For each page, add a "Page X" entry
            for page_num in range(len(reader.pages)):
                page_text = reader.pages[page_num].extract_text()
                structure["claude_structure"]["document_structure"][0]["subheadings"].append({
                    "title": f"Page {page_num + 1}",
                    "context": page_text[:2000] if page_text else "",  # Limit context to 2000 chars
                    "page_reference": page_num + 1,
                    "visual_references": []
                })
        
        return structure
    
    def _create_simple_structure(self, structure, reader):
        """Create a simple document structure using the document title and page-based sections"""
        title = structure["title"]
        structure["headings"].append(title)
        structure["hierarchy"][title] = []
        structure["page_mapping"][title] = 0
            
    def _generate_page_based_structure(self, reader):
        """Generate a basic document structure based on page numbers"""
        document_structure = []
        
        # Create a main heading
        main_heading = {
            "heading": "Document Content",
            "page_reference": 1,
            "subheadings": []
        }
        
        # Add page-based subheadings
        for page_num in range(len(reader.pages)):
            page_text = reader.pages[page_num].extract_text()
            # Try to find a meaningful title in the first few lines of the page
            lines = page_text.split('\n')
            title = f"Page {page_num + 1}"
            
            # Use the first non-empty line as title if it's reasonably short
            for line in lines[:5]:  # Check first 5 lines
                line = line.strip()
                if line and 3 < len(line) < 100:  # Reasonable title length
                    title = line
                    break
            
            main_heading["subheadings"].append({
                "title": title,
                "context": page_text[:2000] if page_text else "",  # Limit context to 2000 chars
                "page_reference": page_num + 1,
                "visual_references": []
            })
        
        document_structure.append(main_heading)
        return {"document_structure": document_structure}
    
    def _extract_document_structure_with_enhanced_claude(self, reader: PdfReader, doc: fitz.Document) -> Dict[str, Any]:
        """
        Extract document structure using an enhanced Claude API approach for better structure extraction.
        
        Args:
            reader: PyPDF2 PdfReader object
            doc: PyMuPDF document object
            
        Returns:
            Document structure dictionary generated by Claude with enhanced prompting
        """
        # Structure to store document hierarchy
        structure = {
            "headings": [],
            "hierarchy": {},
            "page_mapping": {},
            "page_images": {},
            "metadata": {}  # Metadata dictionary
        }
        
        # Extract document title and metadata (same as original method)
        try:
            # Get the filename from the document path
            if hasattr(doc, 'name') and doc.name:
                file_path = doc.name
                file_name = os.path.basename(file_path)
                # Remove extension
                file_name_without_ext = os.path.splitext(file_name)[0]
                structure["title"] = file_name_without_ext
                structure["metadata"]["title"] = structure["title"]
                print(f"Using filename as title: {structure['title']}")
            else:
                # Fallback to extracting from PDF metadata or content
                if doc.metadata and doc.metadata.get('title'):
                    structure["title"] = doc.metadata.get('title')
                    structure["metadata"]["title"] = structure["title"]
                else:
                    # Try to extract title from first page
                    first_page_text = reader.pages[0].extract_text()
                    first_lines = first_page_text.split('\n')
                    if first_lines and len(first_lines[0]) < 100:  # Reasonable title length
                        structure["title"] = first_lines[0].strip()
                        structure["metadata"]["title"] = structure["title"]
        except Exception as e:
            print(f"Error extracting document title from filename: {str(e)}")
            # Fallback to a default title
            structure["title"] = f"Document {uuid.uuid4().hex[:8]}"
            structure["metadata"]["title"] = structure["title"]
        
        # Extract metadata (same as original method)
        try:
            structure["metadata"]["file_size"] = os.path.getsize(doc.name)
            structure["metadata"]["file_size_kb"] = round(structure["metadata"]["file_size"] / 1024, 2)
        except Exception as e:
            print(f"Error extracting file size: {str(e)}")
            structure["metadata"]["file_size"] = 0
            structure["metadata"]["file_size_kb"] = 0
        
        # Extract additional PDF metadata (same as original method)
        try:
            if doc.metadata:
                structure["metadata"]["author"] = doc.metadata.get('author', 'Unknown')
                structure["metadata"]["keywords"] = doc.metadata.get('keywords', '')
                structure["metadata"]["subject"] = doc.metadata.get('subject', '')
                structure["metadata"]["producer"] = doc.metadata.get('producer', '')
                structure["metadata"]["creator"] = doc.metadata.get('creator', '')
                
                # Creation date
                creation_date = doc.metadata.get('creationDate', None)
                if creation_date:
                    # Try to parse PDF date format (D:YYYYMMDDHHmmSS)
                    if isinstance(creation_date, str) and creation_date.startswith('D:'):
                        date_str = creation_date[2:16]  # Extract YYYYMMDDHHMMSS
                        try:
                            from datetime import datetime
                            parsed_date = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                            structure["metadata"]["creation_date"] = parsed_date.isoformat()
                        except:
                            structure["metadata"]["creation_date"] = creation_date
                    else:
                        structure["metadata"]["creation_date"] = creation_date
        except Exception as e:
            print(f"Error extracting document metadata: {str(e)}")
        
        # Store page count
        structure["metadata"]["page_count"] = len(reader.pages)
        
        # Extract full text and render page images (same as original method)
        full_text = ""
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            page_text = page.extract_text()
            full_text += f"\n\n--- Page {page_num + 1} ---\n\n{page_text}"
            
            # Render the page as an image for later use
            pix = doc.load_page(page_num).get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Resize image if too large
            max_width = 1200
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.LANCZOS)
            
            # Convert to base64 for storage
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            # Store the page image
            structure["page_images"][page_num] = img_str
        
        # Define the enhanced prompt for Claude to analyze document structure
        enhanced_prompt = f"""
You are an expert document structure analyzer. Your task is to extract the hierarchical structure of a PDF document with extremely high precision and accuracy.

# INPUT
I will provide you with the full text content of a PDF document, with page markers that indicate page boundaries.

# TASK
Extract the following elements from the document:

1. HEADINGS AND SUBHEADINGS:
   - Identify all heading levels (main headings, subheadings, sub-subheadings, etc.)
   - Determine the hierarchical relationships between headings
   - Detect numbered and unnumbered headings (e.g., "1. Introduction", "Methodology", "2.3 Results")
   - Consider typography hints in the text (ALL CAPS, indentation patterns, numbering schemes)
   - For academic papers, identify sections like Abstract, Introduction, Methodology, Results, Discussion, Conclusion
   - For technical documents, identify Executive Summary, Overview, Requirements, Specifications, etc.

2. CONTEXT:
   - Extract the full text content under each heading/subheading
   - Include the text exactly as it appears, without summarizing or modifying

3. PAGE REFERENCES:
   - Record the exact page number where each section begins
   - Page numbers should be 1-indexed (starting from 1)

4. VISUAL ELEMENTS:
   - Identify ALL figures, tables, charts, diagrams, and other visual elements
   - Capture the exact caption text for each visual element (e.g., "Figure 1: Annual Revenue Growth")
   - Record the page number where each visual element appears
   - Note any references to visual elements in the text

# RULES
- ACCURACY: Your primary goal is 100% accurate extraction of the document structure
- COMPLETENESS: Include all headings, subheadings, and relevant visual elements
- PRESERVATION: Maintain the exact text as it appears in the document
- HIERARCHY: Correctly represent the hierarchical relationships between headings
- EXCLUSIVITY: Do not add, generate, or summarize any content
- PRECISION: Ensure page numbers are accurately assigned to each element

# OUTPUT FORMAT
Return the document structure as valid, well-formed JSON in the following format:

{{
  "document_structure": [
    {{
      "heading": "Main Heading 1",
      "page_reference": 1,
      "subheadings": [
        {{
          "title": "Subheading 1.1",
          "context": "The exact text content under this subheading...",
          "page_reference": 1,
          "visual_references": [
            {{
              "image_caption": "Figure 1: Description of figure as it appears in the text",
              "image_reference": "figure_001",
              "page_reference": 1
            }}
          ]
        }},
        {{
          "title": "Subheading 1.2",
          "context": "The exact text content under this subheading...",
          "page_reference": 2,
          "visual_references": []
        }}
      ]
    }},
    {{
      "heading": "Main Heading 2",
      "page_reference": 3,
      "subheadings": [...]
    }}
  ]
}}

# DOCUMENT TEXT
Here is the document text to analyze:

{full_text}

Respond ONLY with the JSON output. Do not include any explanations or additional text. Ensure your JSON is properly formatted and valid.
"""
        
        # Call Claude API to process the document structure
        print(f"Sending document to Claude 3.5 Sonnet for enhanced structure analysis (text length: {len(full_text)} characters)")
        try:
            # Set a larger max_tokens to ensure we get complete output
            response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=8192,  # Maximum allowed for Claude 3.5 Sonnet
                temperature=0,
                system="You are an expert document structure analyzer specializing in extracting hierarchical document structure with perfect accuracy. You excel at identifying headings, subheadings, body content, and visual elements like figures, tables, and charts. You always return valid, parseable JSON and never add, modify or summarize the original content.",
                messages=[
                    {"role": "user", "content": enhanced_prompt}
                ]
            )
            
            # Extract the response content
            claude_response = response.content[0].text
            
            # Properly extract and fix JSON from the response
            json_str = self._extract_and_fix_json(claude_response)
            
            # Parse the JSON response
            try:
                claude_structure = json.loads(json_str)
                print(f"Claude 3.5 Sonnet successfully extracted enhanced document structure with {len(claude_structure['document_structure'])} main headings")
                
                # Now map the Claude structure to our expected format
                for heading_entry in claude_structure["document_structure"]:
                    heading_text = heading_entry["heading"]
                    page_reference = heading_entry["page_reference"] - 1  # Convert to 0-indexed
                    
                    # Add to our structure
                    structure["headings"].append(heading_text)
                    structure["hierarchy"][heading_text] = []
                    structure["page_mapping"][heading_text] = page_reference
                    
                    # Process subheadings
                    if "subheadings" in heading_entry:
                        for subheading_entry in heading_entry["subheadings"]:
                            subheading_text = subheading_entry["title"]
                            subheading_page = subheading_entry["page_reference"] - 1  # Convert to 0-indexed
                            
                            # Add to our hierarchy
                            structure["hierarchy"][heading_text].append(subheading_text)
                            structure["page_mapping"][subheading_text] = subheading_page
                
                # If Claude didn't find any headings, create a simple structure with the document title
                if not structure["headings"]:
                    print("WARNING: Claude didn't detect any headings. Creating simple title-based structure.")
                    self._create_simple_structure(structure, reader)
                
                # Store the original Claude structure for later use in extracting structured content
                structure["claude_structure"] = claude_structure
                
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing Claude response as JSON or missing key: {str(e)}")
                print(f"JSON string sample: {json_str[:200]}...")
                
                # Create a basic document structure using the title and page structure
                print("Creating fallback document structure from PDF content")
                self._create_simple_structure(structure, reader)
                
                # Try to salvage any partial structure from Claude's response
                try:
                    fallback_structure = self._create_default_structure_with_partial_content(json_str)
                    fallback_json = json.loads(fallback_structure)
                    if fallback_json["document_structure"] and len(fallback_json["document_structure"]) > 1:
                        print(f"Successfully salvaged partial structure with {len(fallback_json['document_structure'])} headings")
                        structure["claude_structure"] = fallback_json
                    else:
                        structure["claude_structure"] = self._generate_page_based_structure(reader)
                except Exception as fallback_error:
                    print(f"Error creating fallback structure: {str(fallback_error)}")
                    structure["claude_structure"] = self._generate_page_based_structure(reader)
        
        except Exception as e:
            print(f"Error calling Claude API for enhanced document structure: {str(e)}")
            # Fallback to creating a basic document structure
            title = structure["title"]
            structure["headings"].append(title)
            structure["hierarchy"][title] = []
            structure["page_mapping"][title] = 0
            
            # Create a basic Claude structure for return
            structure["claude_structure"] = {
                "document_structure": [
                    {
                        "heading": title,
                        "page_reference": 1,
                        "subheadings": []
                    }
                ]
            }
            
            # For each page, add a "Page X" entry
            for page_num in range(len(reader.pages)):
                page_text = reader.pages[page_num].extract_text()
                structure["claude_structure"]["document_structure"][0]["subheadings"].append({
                    "title": f"Page {page_num + 1}",
                    "context": page_text[:2000] if page_text else "",  # Limit context to 2000 chars
                    "page_reference": page_num + 1,
                    "visual_references": []
                })
        
        return structure
    
    def _extract_and_fix_json(self, text: str) -> str:
        """
        Extract and fix potentially malformed JSON from Claude's response.
        
        Args:
            text: Text containing JSON
            
        Returns:
            Fixed JSON string
        """
        # First try to extract JSON from code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            print("Extracted JSON from code block")
        else:
            # Find the outermost JSON structure
            try:
                # Find starting and ending braces
                start_idx = text.find('{')
                if start_idx == -1:
                    print("No JSON structure found, creating minimal structure")
                    return self._create_default_structure()
                
                # Count braces to find matching end
                brace_count = 0
                end_idx = -1
                in_string = False
                escape_char = False
                
                for i in range(start_idx, len(text)):
                    char = text[i]
                    
                    # Handle string detection
                    if char == '"' and not escape_char:
                        in_string = not in_string
                    
                    # Handle escape character
                    if char == '\\' and not escape_char:
                        escape_char = True
                    else:
                        escape_char = False
                    
                    # Only count braces outside of strings
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                
                if end_idx > start_idx:
                    json_str = text[start_idx:end_idx]
                    print(f"Extracted JSON using brace matching: {start_idx} to {end_idx}")
                else:
                    print("Could not find matching end brace, using basic extraction")
                    # Just extract from first { to last }
                    json_str = text[start_idx:]
                    end_idx = json_str.rfind('}') + 1
                    if end_idx > 0:
                        json_str = json_str[:end_idx]
                    else:
                        print("No closing brace found, creating default structure")
                        return self._create_default_structure()
            except Exception as e:
                print(f"Error during JSON extraction: {str(e)}")
                return self._create_default_structure()
        
        # Try parsing as is first
        try:
            parsed = json.loads(json_str)
            print("JSON parsed successfully without repairs")
            return json_str
        except json.JSONDecodeError as e:
            print(f"JSON needs repair: {str(e)}")
            
            # Store original for comparison
            original_json_str = json_str
            
            # Apply fixes in sequence, checking after each fix
            
            # 1. Fix line breaks in strings (common Claude error)
            json_str = re.sub(r'("(?:\\.|[^"\\])*?)\n((?:\\.|[^"\\])*?")', r'\1\\n\2', json_str)
            if self._check_json(json_str):
                print("Fixed JSON by replacing newlines in strings")
                return json_str
            
            # 2. Fix missing commas between objects in arrays
            json_str = re.sub(r'}\s*{', '},{', json_str)
            if self._check_json(json_str):
                print("Fixed JSON by adding missing commas between objects")
                return json_str
            
            # 3. Fix trailing commas in arrays and objects
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            if self._check_json(json_str):
                print("Fixed JSON by removing trailing commas")
                return json_str
                
            # 4. Fix issues with quotes and escaping
            # Replace curly quotes with straight quotes
            json_str = json_str.replace('"', '"').replace('"', '"')
            # Ensure quotes around keys
            json_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)(\s*:)', r'\1"\2"\3', json_str)
            if self._check_json(json_str):
                print("Fixed JSON by correcting quotes")
                return json_str
            
            # 5. Try using a lenient JSON parser (json5)
            try:
                import json5
                parsed = json5.loads(json_str)
                print("Successfully parsed with json5")
                return json.dumps(parsed)  # Convert back to standard JSON
            except:
                print("json5 parsing failed or module not available")
            
            # 6. Try intelligent truncation based on error position
            try:
                json.loads(json_str)
            except json.JSONDecodeError as e2:
                print(f"Attempting intelligent truncation at position {e2.pos}")
                if e2.pos > 0:
                    # Try advanced truncation and repair
                    truncated = json_str[:e2.pos]
                    
                    # Check what's missing
                    open_braces = truncated.count('{') - truncated.count('}')
                    open_brackets = truncated.count('[') - truncated.count(']')
                    open_quotes = truncated.count('"') % 2  # Odd count means unclosed quote
                    
                    # Case 1: Missing closing quote
                    if open_quotes == 1:
                        truncated += '"'
                        print("Added missing closing quote")
                    
                    # Case 2: Missing commas or structural issues
                    # If we're after a closing brace/bracket but before opening a new one
                    if e2.msg.startswith('Expecting'):
                        # Check the content around the error
                        error_context = json_str[max(0, e2.pos-10):min(len(json_str), e2.pos+10)]
                        print(f"Error context: {error_context}")
                        
                        # Fix common structural issues based on error message
                        if e2.msg.startswith('Expecting \',\''):
                            # Try adding a comma at the error position
                            fixed = json_str[:e2.pos] + ',' + json_str[e2.pos:]
                            if self._check_json(fixed):
                                print("Fixed by adding missing comma")
                                return fixed
                        
                        if e2.msg.startswith('Expecting property name'):
                            # Try closing the object
                            fixed = json_str[:e2.pos] + '}' + json_str[e2.pos:]
                            if self._check_json(fixed):
                                print("Fixed by closing object")
                                return fixed
                            
                    # Case 3: Final closure fixing
                    # Add missing closing braces/brackets
                    closure = '"' * open_quotes + '}' * open_braces + ']' * open_brackets
                    if closure:
                        fixed = truncated + closure
                        if self._check_json(fixed):
                            print(f"Fixed JSON with intelligent closure: {closure}")
                            return fixed
                        
                        # Try more aggressive truncation + closure
                        # Find the last complete object/array
                        last_good_object = self._find_last_complete_object(truncated)
                        if last_good_object and self._check_json(last_good_object):
                            print("Fixed by extracting last complete valid object")
                            return last_good_object
                        
            # If we got here, all our repair attempts failed
            print("Could not repair JSON after multiple attempts, creating default structure")
            
            # Create default structure with partial extraction if possible
            return self._create_default_structure_with_partial_content(original_json_str)
    
    def _check_json(self, json_str):
        """Check if a JSON string is valid by attempting to parse it"""
        try:
            json.loads(json_str)
            return True
        except:
            return False
    
    def _find_last_complete_object(self, json_str):
        """Find the last complete JSON object in a string"""
        # Try to find the last valid object by progressively removing characters
        for i in range(len(json_str), 0, -1):
            subset = json_str[:i]
            # Count braces to ensure we have a complete object
            if subset.count('{') == subset.count('}') and subset.count('[') == subset.count(']'):
                try:
                    # See if it's valid JSON
                    json.loads(subset)
                    return subset
                except:
                    pass
        return None
    
    def _create_default_structure(self):
        """Create a minimal valid document structure JSON"""
        return json.dumps({
            "document_structure": [
                {
                    "heading": "Document Content",
                    "page_reference": 1,
                    "subheadings": []
                }
            ]
        })
    
    def _create_default_structure_with_partial_content(self, original_json_str):
        """Create a default structure but try to extract any valid subcomponents"""
        # Default structure to start with
        default_structure = {
            "document_structure": [
                {
                    "heading": "Document Content",
                    "page_reference": 1,
                    "subheadings": []
                }
            ]
        }
        
        # Try to extract any valid subheadings or content
        try:
            # First try to extract partial document_structure array
            structure_match = re.search(r'"document_structure"\s*:\s*\[(.*?)\]', original_json_str, re.DOTALL)
            if structure_match:
                structure_content = structure_match.group(1)
                
                # Try to extract each object in the array
                heading_objects = []
                object_pattern = r'{(.*?)}'
                object_matches = re.finditer(object_pattern, structure_content, re.DOTALL)
                
                for match in object_matches:
                    heading_obj = match.group(0)
                    try:
                        # Try to fix and parse each object individually
                        fixed_obj = self._fix_heading_object(heading_obj)
                        if fixed_obj:
                            heading_objects.append(fixed_obj)
                    except:
                        pass
                
                if heading_objects:
                    default_structure["document_structure"] = heading_objects
                    print(f"Extracted {len(heading_objects)} partial heading objects")
                    return json.dumps(default_structure)
            
            # If that didn't work, try extracting individual properties
            heading_matches = re.findall(r'"heading"\s*:\s*"([^"]+)"', original_json_str)
            page_matches = re.findall(r'"page_reference"\s*:\s*(\d+)', original_json_str)
            
            # Extract subheadings pattern
            subheading_sections = re.findall(r'"subheadings"\s*:\s*\[(.*?)\]', original_json_str, re.DOTALL)
            subheadings_by_section = []
            
            # Process each subheadings section
            for section in subheading_sections:
                subheadings = []
                # Extract individual subheading objects
                subheading_objects = re.finditer(r'{(.*?)}', section, re.DOTALL)
                for match in subheading_objects:
                    subheading_obj = match.group(0)
                    # Extract title and page reference
                    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', subheading_obj)
                    page_match = re.search(r'"page_reference"\s*:\s*(\d+)', subheading_obj)
                    
                    if title_match:
                        subheading = {
                            "title": title_match.group(1),
                            "page_reference": int(page_match.group(1)) if page_match else 1,
                            "visual_references": []
                        }
                        
                        # Try to extract context if available
                        context_match = re.search(r'"context"\s*:\s*"(.*?)"', subheading_obj, re.DOTALL)
                        if context_match:
                            # Fix escaping in the context
                            context = context_match.group(1).replace('\\"', '"').replace('\\n', '\n')
                            subheading["context"] = context
                            
                        subheadings.append(subheading)
                
                subheadings_by_section.append(subheadings)
            
            # If we found headings, use them
            if heading_matches:
                default_structure["document_structure"] = []
                
                for i in range(len(heading_matches)):
                    heading_entry = {
                        "heading": heading_matches[i],
                        "page_reference": int(page_matches[i]) if i < len(page_matches) else 1,
                        "subheadings": subheadings_by_section[i] if i < len(subheadings_by_section) else []
                    }
                    default_structure["document_structure"].append(heading_entry)
                    
                print(f"Extracted {len(heading_matches)} partial headings with {sum(len(s) for s in subheadings_by_section)} subheadings")
            
        except Exception as e:
            print(f"Error creating partial structure: {str(e)}")
            # If all parsing attempts failed, extract basic titles from document
            try:
                # Just try to find main section titles in the text
                title_pattern = r'"title"\s*:\s*"([^"]+)"'
                titles = re.findall(title_pattern, original_json_str)
                
                if titles and len(titles) > 0:
                    default_structure["document_structure"] = []
                    for i, title in enumerate(titles):
                        if len(title) > 3:  # Skip very short titles that might be parsing artifacts
                            default_structure["document_structure"].append({
                                "heading": f"Section: {title}",
                                "page_reference": i + 1,
                                "subheadings": []
                            })
                    print(f"Extracted {len(default_structure['document_structure'])} section titles as fallback")
            except:
                pass
            
        return json.dumps(default_structure)
    
    def _fix_heading_object(self, heading_obj):
        """Try to fix and parse an individual heading object"""
        try:
            # Make sure it's a complete object with balanced braces
            if heading_obj.count('{') != heading_obj.count('}'):
                # Add missing closing brace if needed
                if heading_obj.count('{') > heading_obj.count('}'):
                    heading_obj += '}'
                else:
                    heading_obj = '{' + heading_obj
            
            # Fix common issues
            # Ensure commas between properties
            heading_obj = re.sub(r'"\s*}\s*"', '", "', heading_obj)
            # Fix quoted values
            heading_obj = re.sub(r'(\w+):', r'"\1":', heading_obj)
            
            # Try various parsing approaches
            try:
                # Standard parsing
                return json.loads(heading_obj)
            except:
                try:
                    # Try using json5 if available
                    import json5
                    return json5.loads(heading_obj)
                except:
                    # Extract individual properties through regex as last resort
                    heading = {}
                    
                    # Extract main properties
                    heading_match = re.search(r'"heading"\s*:\s*"([^"]+)"', heading_obj)
                    page_match = re.search(r'"page_reference"\s*:\s*(\d+)', heading_obj)
                    
                    if heading_match:
                        heading["heading"] = heading_match.group(1)
                        heading["page_reference"] = int(page_match.group(1)) if page_match else 1
                        heading["subheadings"] = []
                        
                        # Try to extract subheadings if present
                        subheadings_match = re.search(r'"subheadings"\s*:\s*\[(.*?)\]', heading_obj, re.DOTALL)
                        if subheadings_match:
                            # Process subheadings
                            subheadings_content = subheadings_match.group(1)
                            subheading_objects = re.finditer(r'{(.*?)}', subheadings_content, re.DOTALL)
                            
                            for match in subheading_objects:
                                try:
                                    subheading_obj = match.group(0)
                                    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', subheading_obj)
                                    page_match = re.search(r'"page_reference"\s*:\s*(\d+)', subheading_obj)
                                    
                                    if title_match:
                                        subheading = {
                                            "title": title_match.group(1),
                                            "page_reference": int(page_match.group(1)) if page_match else 1,
                                            "visual_references": []
                                        }
                                        heading["subheadings"].append(subheading)
                                except:
                                    pass
                        
                        return heading
                    return None
        except:
            return None
    
    def _contains_visual_reference(self, text: str) -> bool:
        """Check if text contains reference to a figure, table, or other visual element"""
        patterns = [
            r'figure\s+[0-9]+', 
            r'fig\.\s*[0-9]+',
            r'table\s+[0-9]+',
            r'chart\s+[0-9]+', 
            r'graph\s+[0-9]+',
            r'image\s+[0-9]+'
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _store_document_structure(self, document_id: str, structure: Dict[str, Any]) -> None:
        """
        Store document structure in Neo4j.
        
        Args:
            document_id: Document ID
            structure: Document structure dictionary
        """
        with self.driver.session() as session:
            # Create document node with enhanced metadata
            title = structure.get("title", f"Document {document_id[:8]}")
            upload_date = datetime.now().isoformat()
            metadata = structure.get("metadata", {})
            
            # Create a parameters dictionary for the Neo4j query
            document_params = {
                "id": document_id,
                "title": title,
                "upload_date": upload_date,
                "page_count": metadata.get("page_count", len(structure["page_images"])),
                "file_size_kb": metadata.get("file_size_kb", 0),
                "author": metadata.get("author", "Unknown"),
                "creation_date": metadata.get("creation_date", None),
                "keywords": metadata.get("keywords", ""),
                "subject": metadata.get("subject", ""),
                "producer": metadata.get("producer", ""),
                "creator": metadata.get("creator", "")
            }
            
            # Create document node with all metadata
            session.run(
                """
                CREATE (d:Document {
                    id: $id, 
                    title: $title, 
                    upload_date: $upload_date,
                    page_count: $page_count,
                    file_size_kb: $file_size_kb,
                    author: $author,
                    creation_date: $creation_date,
                    keywords: $keywords,
                    subject: $subject,
                    producer: $producer,
                    creator: $creator
                })
                """,
                **document_params
            )
            
            # Create page nodes and connect to document
            for page_num, image in structure["page_images"].items():
                session.run(
                    """
                    MATCH (d:Document {id: $doc_id})
                    CREATE (p:Page {number: $page_num, image: $image})
                    CREATE (d)-[:HAS_PAGE]->(p)
                    CREATE (d)-[:CONTAINS]->(p)
                    """,
                    doc_id=document_id,
                    page_num=page_num,
                    image=image
                )
            
            # Create heading nodes and connect to pages
            for heading in structure["headings"]:
                page_num = structure["page_mapping"][heading]
                session.run(
                    """
                    MATCH (d:Document {id: $doc_id})
                    MATCH (p:Page {number: $page_num})
                    CREATE (h:Heading {text: $heading, type: 'main'})
                    CREATE (d)-[:HAS_HEADING]->(h)
                    CREATE (d)-[:CONTAINS]->(h)
                    CREATE (h)-[:APPEARS_ON]->(p)
                    """,
                    doc_id=document_id,
                    heading=heading,
                    page_num=page_num
                )
                
                # Create subheading nodes and connect to headings
                for subheading in structure["hierarchy"].get(heading, []):
                    subheading_page = structure["page_mapping"][subheading]
                    session.run(
                        """
                        MATCH (d:Document {id: $doc_id})
                        MATCH (h:Heading {text: $heading})
                        MATCH (p:Page {number: $subheading_page})
                        CREATE (s:Heading {text: $subheading, type: 'sub'})
                        CREATE (d)-[:HAS_HEADING]->(s)
                        CREATE (h)-[:HAS_SUBHEADING]->(s)
                        CREATE (h)-[:CONTAINS]->(s)
                        CREATE (d)-[:CONTAINS]->(s)
                        CREATE (s)-[:APPEARS_ON]->(p)
                        """,
                        doc_id=document_id,
                        heading=heading,
                        subheading=subheading,
                        subheading_page=subheading_page
                    )
    
    def get_document_structure(self, document_id: str) -> Dict[str, Any]:
        """
        Get the structure of a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Document structure
        """
        with self.driver.session() as session:
            # Check if document exists
            result = session.run(
                "MATCH (d:Document {id: $id}) RETURN d",
                id=document_id
            )
            
            document = result.single()
            if not document:
                raise ValueError(f"Document with ID {document_id} not found")
            
            # Get document data
            result = session.run(
                """
                MATCH (d:Document {id: $id})
                OPTIONAL MATCH (d)-[:HAS_HEADING]->(h:Heading)
                OPTIONAL MATCH (h)-[:HAS_SUBHEADING]->(s:Subheading)
                RETURN d, collect(DISTINCT h) as headings, collect(DISTINCT s) as subheadings
                """,
                id=document_id
            )
            
            record = result.single()
            if not record:
                return {"error": "Document found but no structure available"}
            
            document_node = record["d"]
            heading_nodes = record["headings"]
            
            # Get page count
            page_count = self._get_document_page_count(document_id)
            
            # Build structure
            structure = {
                "id": document_id,
                "title": document_node.get("title", "Untitled Document"),
                "headings": [],
                "hierarchy": {},
                "page_mapping": {},
                "metadata": {
                    "title": document_node.get("title", "Untitled Document"),
                    "page_count": page_count
                }
            }
            
            # Add metadata if available
            for key in ["author", "keywords", "subject", "producer", "creator", "creation_date", "file_size", "file_size_kb"]:
                if key in document_node:
                    structure["metadata"][key] = document_node[key]
            
            # Get headings
            if heading_nodes:
                for heading_node in heading_nodes:
                    heading_text = heading_node.get("text", "")
                    if not heading_text:
                        continue
                        
                    structure["headings"].append(heading_text)
                    structure["hierarchy"][heading_text] = []
                    structure["page_mapping"][heading_text] = heading_node.get("page", 0)
                    
                    # Get subheadings for this heading
                    result = session.run(
                        """
                        MATCH (h:Heading {id: $heading_id})-[:HAS_SUBHEADING]->(s:Subheading)
                        RETURN s ORDER BY s.page, s.id
                        """,
                        heading_id=heading_node.get("id", "")
                    )
                    
                    for subheading_record in result:
                        subheading_node = subheading_record["s"]
                        subheading_text = subheading_node.get("text", "")
                        if not subheading_text:
                            continue
                            
                        structure["hierarchy"][heading_text].append(subheading_text)
                        structure["page_mapping"][subheading_text] = subheading_node.get("page", 0)
            
            return structure
            
    def document_exists(self, document_id: str) -> bool:
        """
        Check if a document exists in the database.
        
        Args:
            document_id: Document ID
            
        Returns:
            True if document exists, False otherwise
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (d:Document {id: $id}) RETURN count(d) as count",
                id=document_id
            )
            
            record = result.single()
            return record and record["count"] > 0
    
    def get_document_pdf_data(self, document_id: str) -> Optional[bytes]:
        """
        Get the original PDF data for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            PDF data as bytes if available, None otherwise
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (d:Document {id: $id}) RETURN d.pdf_data as pdf_data",
                id=document_id
            )
            
            record = result.single()
            if not record or not record["pdf_data"]:
                return None
                
            # PDF data is stored as base64 string, convert back to bytes
            pdf_data_base64 = record["pdf_data"]
            try:
                return base64.b64decode(pdf_data_base64)
            except Exception as e:
                print(f"Error decoding PDF data: {str(e)}")
                return None

    def store_structured_content(self, document_id: str, structured_content: Dict[str, Any], is_enhanced: bool = False) -> bool:
        """
        Store structured content for a document.
        
        Args:
            document_id: Document ID
            structured_content: Structured content
            is_enhanced: Whether this is enhanced structured content
            
        Returns:
            True if successful, False otherwise
        """
        with self.driver.session() as session:
            try:
                # Convert to JSON string
                content_json = json.dumps(structured_content)
                
                # Store in Neo4j
                if is_enhanced:
                    # Store as enhanced structured content
                    result = session.run(
                        """
                        MATCH (d:Document {id: $id})
                        SET d.enhanced_structured_content = $content,
                            d.enhanced_content_timestamp = $timestamp
                        RETURN d
                        """,
                        id=document_id,
                        content=content_json,
                        timestamp=datetime.now().isoformat()
                    )
                else:
                    # Store as regular structured content
                    result = session.run(
                        """
                        MATCH (d:Document {id: $id})
                        SET d.structured_content = $content
                        RETURN d
                        """,
                        id=document_id,
                        content=content_json
                    )
                
                return result.single() is not None
                
            except Exception as e:
                print(f"Error storing structured content: {str(e)}")
                return False
    
    def get_structured_content(self, document_id: str, enhanced: bool = True) -> Dict[str, Any]:
        """
        Get structured content for a document.
        
        Args:
            document_id: Document ID
            enhanced: Whether to get enhanced structured content (default: True)
                      When set to True, will return enhanced content if available,
                      falling back to regular content if enhanced is not available.
                      When set to False, will always return regular content.
            
        Returns:
            Structured content
        """
        with self.driver.session() as session:
            # First check if enhanced content is available if requested
            if enhanced:
                result = session.run(
                    """
                    MATCH (d:Document {id: $id})
                    RETURN d.enhanced_structured_content as content,
                           d.enhanced_content_timestamp as timestamp
                    """,
                    id=document_id
                )
                
                record = result.single()
                if record and record["content"]:
                    try:
                        content = json.loads(record["content"])
                        # Add flags to indicate this is enhanced content
                        content["enhanced"] = True
                        if record["timestamp"]:
                            content["processing_timestamp"] = record["timestamp"]
                        return content
                    except json.JSONDecodeError as e:
                        # If enhanced content is corrupted, fall back to regular
                        print(f"JSON decode error for document {document_id}: {str(e)}")
            
            # Fetch regular content (as fallback or if enhanced not requested)
            result = session.run(
                """
                MATCH (d:Document {id: $id})
                RETURN d.structured_content as content
                """,
                id=document_id
            )
            
            record = result.single()
            if not record or not record["content"]:
                raise ValueError(f"No structured content found for document {document_id}")
                
            # Parse JSON
            try:
                content = json.loads(record["content"])
                # Add flag to indicate this is regular content
                content["enhanced"] = False
                return content
            except json.JSONDecodeError as e:
                print(f"JSON decode error for document {document_id}: {str(e)}")
                raise ValueError(f"Invalid JSON content for document {document_id}")
    
    def get_visual_reference(self, document_id: str, reference: str) -> Dict[str, Any]:
        """
        Get a visual reference by its reference ID.
        
        Args:
            document_id: ID of the document
            reference: Reference ID of the visual
            
        Returns:
            Visual reference data including the page image
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(v:VisualReference {reference: $ref})
                MATCH (v)-[:APPEARS_ON]->(p:Page)
                RETURN v.caption as caption,
                       v.reference as reference,
                       p.number as page_number,
                       p.image as page_image
                """,
                doc_id=document_id,
                ref=reference
            )
            
            record = result.single()
            if not record:
                raise KeyError(f"Visual reference {reference} not found for document {document_id}")
            
            return {
                "caption": record["caption"],
                "reference": record["reference"],
                "page_number": record["page_number"] + 1,  # Convert to 1-indexed for display
                "page_image": record["page_image"]
            }
    
    def delete_document(self, document_id: str) -> bool:
        """
        Delete a document and all related nodes from Neo4j.
        
        Args:
            document_id: Document ID
            
        Returns:
            True if successful, False otherwise
        """
        with self.driver.session() as session:
            try:
                # First check if document exists
                if not self.document_exists(document_id):
                    raise ValueError(f"Document with ID {document_id} not found")
                
                # Delete all relationships and nodes related to the document
                # This includes: Pages, Headings, and any other connected nodes
                session.run(
                    """
                    MATCH (d:Document {id: $id})
                    OPTIONAL MATCH (d)-[r1]->(n1)
                    OPTIONAL MATCH (n1)-[r2]->(n2)
                    OPTIONAL MATCH (n2)-[r3]->(n3)
                    DETACH DELETE n3, n2, n1, d
                    """,
                    id=document_id
                )
                
                # Verify the document is deleted
                result = session.run(
                    "MATCH (d:Document {id: $id}) RETURN count(d) as count",
                    id=document_id
                )
                record = result.single()
                
                if record and record["count"] > 0:
                    print(f"Warning: Document {document_id} was not fully deleted")
                    return False
                
                print(f"Document {document_id} and all related nodes successfully deleted")
                return True
                
            except Exception as e:
                print(f"Error deleting document {document_id}: {str(e)}")
                return False
    
    def _extract_images_from_page(self, page: fitz.Page, page_idx: int, document_id: str) -> List[Dict[str, Any]]:
        """
        Extract images from a page and save them as separate entities.
        
        Args:
            page: PyMuPDF page object
            page_idx: Page index
            document_id: Document ID
            
        Returns:
            List of image information dictionaries
        """
        images = []
        image_list = page.get_images(full=True)
        
        for img_idx, img in enumerate(image_list):
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            
            # Create a unique reference ID for this image
            image_ref = f"image_{document_id[:8]}_{page_idx+1}_{img_idx+1}"
            
            # Convert image bytes to base64
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Create image info
            image_info = {
                "reference": image_ref,
                "page": page_idx,
                "index": img_idx,
                "base64": image_b64,
                "width": base_image.get("width", 0),
                "height": base_image.get("height", 0)
            }
            
            images.append(image_info)
        
        return images
        
    def _store_pdf_data(self, document_id: str, pdf_path: str) -> bool:
        """
        Store the raw PDF data in the document node for future reprocessing.
        
        Args:
            document_id: Document ID
            pdf_path: Path to the PDF file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Read the PDF file as binary
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()
            
            # Convert to base64 for storage
            pdf_data_base64 = base64.b64encode(pdf_data).decode()
            
            # Store in Neo4j
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (d:Document {id: $id})
                    SET d.pdf_data = $pdf_data
                    RETURN d
                    """,
                    id=document_id,
                    pdf_data=pdf_data_base64
                )
                
                return result.single() is not None
                
        except Exception as e:
            print(f"Error storing PDF data: {str(e)}")
            return False
    
    def _get_document_page_count(self, document_id: str) -> int:
        """
        Get the page count for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Page count as integer
        """
        with self.driver.session() as session:
            # Get page count from document metadata if available
            result = session.run(
                "MATCH (d:Document {id: $id}) RETURN d.page_count as page_count",
                id=document_id
            )
            record = result.single()
            if record and record["page_count"] is not None:
                return record["page_count"]
            
            # Otherwise count the pages
            result = session.run(
                """
                MATCH (d:Document {id: $id})-[:HAS_PAGE]->(p:Page)
                RETURN count(p) as page_count
                """,
                id=document_id
            )
            record = result.single()
            return record["page_count"] if record else 0
    
    def get_all_documents_with_metadata(self) -> List[Dict[str, Any]]:
        """
        Get all documents with their metadata.
        
        Returns:
            List of document objects with metadata
        """
        with self.driver.session() as session:
            # Query all documents with their metadata
            result = session.run(
                """
                MATCH (d:Document)
                OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
                WITH d, count(p) as page_count
                RETURN d.id as id, 
                       d.title as title, 
                       d.upload_date as upload_date,
                       d.page_count as stored_page_count,
                       page_count,
                       d.file_size_kb as file_size_kb,
                       d.author as author,
                       d.creation_date as creation_date,
                       d.enhanced_content_timestamp as enhanced_timestamp
                ORDER BY d.upload_date DESC
                """
            )
            
            documents = []
            for record in result:
                # Use stored page count if available, otherwise use counted pages
                final_page_count = record["stored_page_count"] if record["stored_page_count"] is not None else record["page_count"]
                
                document = {
                    "id": record["id"],
                    "title": record["title"] if record["title"] else "Untitled Document",
                    "upload_date": record["upload_date"],
                    "page_count": final_page_count,
                    "file_size_kb": record["file_size_kb"] if record["file_size_kb"] is not None else 0,
                    "author": record["author"] if record["author"] is not None else "Unknown",
                    "creation_date": record["creation_date"],
                    "has_enhanced_content": record["enhanced_timestamp"] is not None
                }
                documents.append(document)
                
            return documents
        