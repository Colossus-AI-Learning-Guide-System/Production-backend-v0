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
            
            # Process document structure using Claude (no fallback)
            structure = self._extract_document_structure_with_claude(reader, doc)
            
            # Override title with original filename if provided
            if original_filename:
                filename_without_ext = os.path.splitext(original_filename)[0]
                structure["title"] = filename_without_ext
                structure["metadata"]["title"] = structure["title"]
                print(f"Title set to original filename: {structure['title']}")
            
            print(f"Extracted {len(structure['headings'])} headings")
            
            # Store structure in Neo4j
            self._store_document_structure(document_id, structure)
            print(f"Document structure stored in Neo4j with ID: {document_id}")
            
            # Extract structured content directly from Claude response if available
            if "claude_structure" in structure:
                structured_content = {"document_structure": structure["claude_structure"]["document_structure"]}
                # Remove the temporary claude_structure from the structure dictionary
                del structure["claude_structure"]
            else:
                # Create basic page-based structure if Claude didn't return a proper structure
                structured_content = {
                    "document_structure": [
                        {
                            "heading": structure["title"],
                            "page_reference": 1,
                            "subheadings": []
                        }
                    ]
                }
            
            # Store structured content in Neo4j
            self.store_structured_content(document_id, structured_content)
            print(f"Structured content extracted and stored with {len(structured_content['document_structure'])} main headings")
            
            return document_id
            
        except Exception as e:
            print(f"Error processing document: {str(e)}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Error processing document: {str(e)}")
    
    def process_base64_document(self, base64_data: str) -> str:
        """
        Process a PDF document from base64 encoded data.
        
        Args:
            base64_data: Base64 encoded PDF data
            
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
                # Process the PDF file
                document_id = self.process_document(temp_file_path)
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
                    title = structure["title"]
                    structure["headings"].append(title)
                    structure["hierarchy"][title] = []
                    structure["page_mapping"][title] = 0
                        
                # Store the original Claude structure for later use in extracting structured content
                structure["claude_structure"] = claude_structure
                
            except json.JSONDecodeError as e:
                print(f"Error parsing Claude response as JSON: {str(e)}")
                print(f"JSON string: {json_str[:500]}...")
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
            
            # For each page, add a "Page X" entry with context
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
                    # No JSON found, create a minimal structure
                    return '{"document_structure": []}'
                
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
                        # No closing brace found, create minimal structure
                        return '{"document_structure": []}'
            except Exception as e:
                print(f"Error during JSON extraction: {str(e)}")
                # Return minimal valid JSON
                return '{"document_structure": []}'
        
        # REPAIR JSON
        try:
            # Try parsing as is
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError as e:
            print(f"JSON needs repair: {str(e)}")
            
            # 1. Fix line breaks in strings (common Claude error)
            # This regex pattern matches unescaped line breaks within JSON strings
            pattern = r'("(?:\\.|[^"\\])*?)\n((?:\\.|[^"\\])*?")'
            json_str = re.sub(pattern, r'\1\\n\2', json_str)
            
            # 2. Fix missing commas between objects in arrays
            json_str = re.sub(r'}\s*{', '},{', json_str)
            
            # 3. Fix trailing commas in arrays and objects
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            
            # 4. Try to truncate at the end of valid JSON
            # If we still have issues, try to find a valid truncation point
            try:
                json.loads(json_str)
            except json.JSONDecodeError as e2:
                print(f"Attempting to truncate JSON at position {e2.pos}")
                if e2.pos > 0:
                    # Try truncating at the error position and adding needed closure
                    truncated = json_str[:e2.pos]
                    # Count unclosed braces and brackets
                    open_braces = truncated.count('{') - truncated.count('}')
                    open_brackets = truncated.count('[') - truncated.count(']')
                    # Close them
                    closure = '}' * open_braces + ']' * open_brackets
                    if open_braces > 0 or open_brackets > 0:
                        json_str = truncated + closure
                
            # 5. Final attempt: if all else fails, return a minimal valid structure
            try:
                json.loads(json_str)
                return json_str
            except:
                print("Could not repair JSON, returning minimal structure")
                return '{"document_structure": []}'
    
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
        Get the structure of a processed document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            Document structure dictionary
        """
        with self.driver.session() as session:
            # Get all headings, subheadings, and page images
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:HAS_HEADING]->(h:Heading {type: 'main'})
                OPTIONAL MATCH (h)-[:HAS_SUBHEADING]->(s:Heading)
                OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
                RETURN h.text as heading, 
                       collect(s.text) as subheadings,
                       collect({number: p.number, image: p.image}) as pages
                ORDER BY h.text
                """,
                doc_id=document_id
            )
            
            structure = {
                "headings": [],
                "hierarchy": {},
                "page_images": {}
            }
            
            for record in result:
                heading = record["heading"]
                subheadings = record["subheadings"]
                pages = record["pages"]
                
                structure["headings"].append(heading)
                structure["hierarchy"][heading] = [s for s in subheadings if s is not None]
                
                # Add page images to the structure
                for page in pages:
                    if page["number"] is not None and page["image"] is not None:
                        structure["page_images"][page["number"]] = page["image"]
            
            return structure
    
    def get_heading_page(self, document_id: str, heading: str) -> Dict[str, Any]:
        """
        Get the page image for a specific heading.
        
        Args:
            document_id: ID of the document
            heading: The heading text
            
        Returns:
            Dictionary with heading, page number, and page image
        """
        with self.driver.session() as session:
            # Get page number and image for the heading
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:HAS_HEADING]->(h:Heading {text: $heading})-[:APPEARS_ON]->(p:Page)
                RETURN p.number as page_num, p.image as page_image
                """,
                doc_id=document_id,
                heading=heading
            )
            
            record = result.single()
            
            if not record:
                raise KeyError(f"Heading '{heading}' not found in document")
            
            return {
                "heading": heading,
                "page_number": record["page_num"],
                "page_image": record["page_image"]
            }
    
    def get_all_documents(self) -> List[str]:
        """
        Get a list of all document IDs in the database.
        
        Returns:
            List of document IDs
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)
                RETURN d.id as document_id
                """
            )
            
            return [record["document_id"] for record in result]
    
    def get_all_documents_with_metadata(self) -> List[Dict[str, Any]]:
        """
        Get a list of all documents with metadata.
        
        Returns:
            List of document dictionaries with id and metadata
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)
                OPTIONAL MATCH (d)-[:HAS_HEADING]->(h:Heading)
                OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
                WITH d, 
                     count(DISTINCT h) as heading_count,
                     count(DISTINCT p) as actual_page_count
                RETURN d.id as document_id, 
                       d.title as title,
                       d.upload_date as upload_date,
                       d.page_count as page_count,
                       d.file_size_kb as file_size_kb,
                       d.author as author,
                       d.creation_date as creation_date,
                       d.keywords as keywords,
                       d.subject as subject,
                       heading_count,
                       actual_page_count
                """
            )
            
            return [dict(record) for record in result]
    
    def clear_document(self, document_id: str) -> bool:
        """
        Delete a document and all its related nodes from Neo4j.
        
        Args:
            document_id: ID of the document to delete
            
        Returns:
            True if document was deleted, False if not found
        """
        with self.driver.session() as session:
            # Check if document exists
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})
                RETURN count(d) as doc_count
                """,
                doc_id=document_id
            )
            
            if result.single()["doc_count"] == 0:
                return False
                
            # First count all nodes to be deleted for verification
            count_result = session.run(
                """
                MATCH (d:Document {id: $doc_id})
                OPTIONAL MATCH (d)-[:CONTAINS|HAS_PAGE|HAS_HEADING]->(n)
                RETURN count(DISTINCT n) as related_node_count
                """,
                doc_id=document_id
            )
            related_node_count = count_result.single()["related_node_count"]
            
            # Delete all related nodes first
            session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:CONTAINS|HAS_PAGE|HAS_HEADING]->(n)
                DETACH DELETE n
                """,
                doc_id=document_id
            )
            
            # Then delete the document node
            delete_result = session.run(
                """
                MATCH (d:Document {id: $doc_id})
                DETACH DELETE d
                RETURN count(d) as deleted_count
                """,
                doc_id=document_id
            )
            
            deleted_count = delete_result.single()["deleted_count"]
            print(f"Deleted document {document_id} with {related_node_count} related nodes")
            
            # Verify no orphaned nodes remain by checking for any nodes that were connected to this document
            verify_result = session.run(
                """
                MATCH (n)
                WHERE EXISTS {
                    MATCH (n)-[r]-()
                    WHERE type(r) IN ['HAS_PAGE', 'HAS_HEADING', 'HAS_SUBHEADING', 'APPEARS_ON', 'CONTAINS']
                      AND NOT EXISTS {
                        MATCH (d:Document)-[:CONTAINS|HAS_PAGE|HAS_HEADING]->(n)
                      }
                }
                RETURN count(n) as orphan_count
                """
            )
            
            orphan_count = verify_result.single()["orphan_count"]
            if orphan_count > 0:
                print(f"Warning: Found {orphan_count} orphaned nodes after deletion")
                # Perform cleanup of orphaned nodes if found
                session.run(
                    """
                    MATCH (n)
                    WHERE EXISTS {
                        MATCH (n)-[r]-()
                        WHERE type(r) IN ['HAS_PAGE', 'HAS_HEADING', 'HAS_SUBHEADING', 'APPEARS_ON', 'CONTAINS']
                          AND NOT EXISTS {
                            MATCH (d:Document)-[:CONTAINS|HAS_PAGE|HAS_HEADING]->(n)
                          }
                    }
                    DETACH DELETE n
                    """
                )
            
            return True
    
    def get_page_image(self, document_id: str, page_number: int) -> Dict[str, Any]:
        """
        Get the image data for a specific page.
        
        Args:
            document_id: ID of the document
            page_number: Page number to retrieve
            
        Returns:
            Dictionary containing page image data
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:HAS_PAGE]->(p:Page {number: $page_number})
                RETURN p.image as image
                """,
                doc_id=document_id,
                page_number=page_number
            )
            
            record = result.single()
            if not record:
                raise KeyError(f"Page {page_number} not found in document")
            
            return {
                "page_number": page_number,
                "image": record["image"]
            }
    
    def get_document_metadata(self, document_id: str) -> Dict[str, Any]:
        """
        Get metadata for a specific document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            Dictionary containing document metadata
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})
                OPTIONAL MATCH (d)-[:HAS_HEADING]->(h:Heading)
                OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
                RETURN d.id as document_id,
                       d.title as title,
                       d.upload_date as upload_date,
                       d.page_count as page_count,
                       d.file_size_kb as file_size_kb,
                       d.author as author,
                       d.creation_date as creation_date,
                       d.keywords as keywords,
                       d.subject as subject,
                       d.producer as producer,
                       d.creator as creator,
                       count(DISTINCT h) as heading_count,
                       count(DISTINCT p) as actual_page_count
                """,
                doc_id=document_id
            )
            
            record = result.single()
            if not record:
                raise KeyError(f"Document {document_id} not found")
            
            return dict(record)
    
    def clean_orphaned_nodes(self) -> int:
        """
        Clean up any orphaned nodes in the database.
        These are nodes that have no connection to any Document node.
        
        Returns:
            The number of orphaned nodes deleted
        """
        with self.driver.session() as session:
            # First, count orphaned nodes
            count_result = session.run(
                """
                MATCH (n) 
                WHERE (n:Page OR n:Heading) 
                AND NOT EXISTS {
                    MATCH (n)<-[:CONTAINS]-(d:Document)
                }
                RETURN count(n) as orphan_count
                """
            )
            
            orphan_count = count_result.single()["orphan_count"]
            
            if orphan_count > 0:
                print(f"Found {orphan_count} orphaned nodes to clean up")
                
                # Delete orphaned nodes
                session.run(
                    """
                    MATCH (n) 
                    WHERE (n:Page OR n:Heading) 
                    AND NOT EXISTS {
                        MATCH (n)<-[:CONTAINS]-(d:Document)
                    }
                    DETACH DELETE n
                    """
                )
            
            return orphan_count
    
    def store_structured_content(self, document_id: str, structured_content: Dict[str, Any]) -> None:
        """
        Store structured content in Neo4j.
        
        Args:
            document_id: Document ID
            structured_content: Structured content dictionary
        """
        with self.driver.session() as session:
            # Retrieve the document node
            document_query = """
            MATCH (d:Document {id: $doc_id})
            RETURN d
            """
            document_result = session.run(document_query, doc_id=document_id).single()
            
            if not document_result:
                raise ValueError(f"Document with ID {document_id} not found")
            
            # Create nodes for each heading
            for heading_data in structured_content["document_structure"]:
                heading_id = str(uuid.uuid4())
                
                # Create heading node
                session.run(
                    """
                    MATCH (d:Document {id: $doc_id})
                    CREATE (h:Heading {
                        id: $heading_id,
                        text: $heading_text,
                        type: 'main',
                        page_reference: $page_reference
                    })
                    CREATE (d)-[:HAS_HEADING]->(h)
                    CREATE (d)-[:CONTAINS]->(h)
                    WITH d, h
                    MATCH (p:Page {number: $page_num})
                    WHERE (d)-[:HAS_PAGE]->(p)
                    CREATE (h)-[:APPEARS_ON]->(p)
                    """,
                    doc_id=document_id,
                    heading_id=heading_id,
                    heading_text=heading_data["heading"],
                    page_reference=heading_data["page_reference"] - 1,  # Convert to 0-indexed
                    page_num=heading_data["page_reference"] - 1  # Convert to 0-indexed
                )
                
                # Create subheading nodes
                for subheading_data in heading_data["subheadings"]:
                    subheading_id = str(uuid.uuid4())
                    
                    # Create subheading node
                    session.run(
                        """
                        MATCH (d:Document {id: $doc_id})
                        MATCH (h:Heading {id: $heading_id})
                        CREATE (s:Heading {
                            id: $subheading_id,
                            text: $subheading_text,
                            type: 'sub',
                            page_reference: $page_reference,
                            context: $context
                        })
                        CREATE (d)-[:HAS_HEADING]->(s)
                        CREATE (h)-[:HAS_SUBHEADING]->(s)
                        CREATE (h)-[:CONTAINS]->(s)
                        CREATE (d)-[:CONTAINS]->(s)
                        WITH d, s
                        MATCH (p:Page {number: $page_num})
                        WHERE (d)-[:HAS_PAGE]->(p)
                        CREATE (s)-[:APPEARS_ON]->(p)
                        """,
                        doc_id=document_id,
                        heading_id=heading_id,
                        subheading_id=subheading_id,
                        subheading_text=subheading_data["title"],
                        page_reference=subheading_data["page_reference"] - 1,  # Convert to 0-indexed
                        context=subheading_data["context"],
                        page_num=subheading_data["page_reference"] - 1  # Convert to 0-indexed
                    )
                    
                    # Create visual reference nodes
                    for visual_ref in subheading_data["visual_references"]:
                        visual_id = str(uuid.uuid4())
                        
                        session.run(
                            """
                            MATCH (d:Document {id: $doc_id})
                            MATCH (s:Heading {id: $subheading_id})
                            CREATE (v:VisualReference {
                                id: $visual_id,
                                caption: $caption,
                                reference: $reference,
                                page_reference: $page_reference
                            })
                            CREATE (s)-[:HAS_VISUAL]->(v)
                            CREATE (d)-[:CONTAINS]->(v)
                            WITH d, v
                            MATCH (p:Page {number: $page_num})
                            WHERE (d)-[:HAS_PAGE]->(p)
                            CREATE (v)-[:APPEARS_ON]->(p)
                            """,
                            doc_id=document_id,
                            subheading_id=subheading_id,
                            visual_id=visual_id,
                            caption=visual_ref["image_caption"],
                            reference=visual_ref["image_reference"],
                            page_reference=visual_ref["page_reference"] - 1,  # Convert to 0-indexed
                            page_num=visual_ref["page_reference"] - 1  # Convert to 0-indexed
                        )
        
    def get_structured_content(self, document_id: str) -> Dict[str, Any]:
        """
        Get the structured content for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            Structured content dictionary
        """
        with self.driver.session() as session:
            # First, check if the document exists
            document_query = """
            MATCH (d:Document {id: $doc_id})
            RETURN d
            """
            document_result = session.run(document_query, doc_id=document_id).single()
            
            if not document_result:
                raise ValueError(f"Document with ID {document_id} not found")
            
            # Get all main headings with their subheadings
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:HAS_HEADING]->(h:Heading {type: 'main'})
                OPTIONAL MATCH (h)-[:HAS_SUBHEADING]->(s:Heading)
                WITH h, h.page_reference as h_page, s
                ORDER BY h.text, s.text
                
                OPTIONAL MATCH (s)-[:HAS_VISUAL]->(v:VisualReference)
                WITH h, h_page, s, COLLECT({
                    image_caption: v.caption,
                    image_reference: v.reference,
                    page_reference: CASE WHEN v.page_reference IS NULL THEN null ELSE v.page_reference + 1 END
                }) as visuals
                
                WITH h, h_page, COLLECT({
                    id: s.id,
                    title: s.text,
                    context: s.context,
                    page_reference: CASE WHEN s.page_reference IS NULL THEN null ELSE s.page_reference + 1 END,
                    visual_references: [visual IN visuals WHERE visual.image_reference IS NOT NULL]
                }) as subheadings
                
                RETURN h.text as heading,
                       h_page + 1 as page_reference,
                       [subheading IN subheadings WHERE subheading.id IS NOT NULL] as subheadings
                ORDER BY h.text
                """,
                doc_id=document_id
            )
            
            structured_content = {
                "document_structure": []
            }
            
            for record in result:
                heading_entry = {
                    "heading": record["heading"],
                    "page_reference": record["page_reference"],
                    "subheadings": []
                }
                
                for subheading in record["subheadings"]:
                    # Skip null entries (happens when there are no subheadings)
                    if subheading["id"] is None:
                        continue
                        
                    subheading_entry = {
                        "title": subheading["title"],
                        "context": subheading["context"] or "",
                        "page_reference": subheading["page_reference"],
                        "visual_references": subheading["visual_references"]
                    }
                    
                    heading_entry["subheadings"].append(subheading_entry)
                
                structured_content["document_structure"].append(heading_entry)
            
            return structured_content
    
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
        