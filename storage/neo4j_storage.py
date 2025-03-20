import fitz  # PyMuPDF
import re
from PyPDF2 import PdfReader
from PIL import Image
import io
import base64
import os
import tempfile
import uuid
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase
from datetime import datetime

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
            
            # Process document structure
            structure = self._extract_document_structure(reader, doc)
            
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
            
            # Verify structure was created
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(n)
                    RETURN count(n) as node_count
                    """,
                    doc_id=document_id
                )
                node_count = result.single()["node_count"]
                print(f"Created {node_count} nodes connected to document {document_id}")
            
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
    
    def _extract_document_structure(self, reader: PdfReader, doc: fitz.Document) -> Dict[str, Any]:
        """
        Extract document structure including headings, subheadings, and page images.
        
        Args:
            reader: PyPDF2 PdfReader object
            doc: PyMuPDF document object
            
        Returns:
            Document structure dictionary
        """
        # Structure to store document hierarchy
        structure = {
            "headings": [],
            "hierarchy": {},
            "page_mapping": {},
            "page_images": {},
            "metadata": {}  # New metadata dictionary
        }
        
        # Extract filename as title
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
        
        # Extract document file size
        try:
            structure["metadata"]["file_size"] = os.path.getsize(doc.name)
            structure["metadata"]["file_size_kb"] = round(structure["metadata"]["file_size"] / 1024, 2)
        except Exception as e:
            print(f"Error extracting file size: {str(e)}")
            structure["metadata"]["file_size"] = 0
            structure["metadata"]["file_size_kb"] = 0
        
        # Extract metadata from PDF
        try:
            # Extract additional metadata
            if doc.metadata:
                # Author information
                structure["metadata"]["author"] = doc.metadata.get('author', 'Unknown')
                
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
                
                # Keywords or subject
                structure["metadata"]["keywords"] = doc.metadata.get('keywords', '')
                structure["metadata"]["subject"] = doc.metadata.get('subject', '')
                
                # Producer and creator applications
                structure["metadata"]["producer"] = doc.metadata.get('producer', '')
                structure["metadata"]["creator"] = doc.metadata.get('creator', '')
        except Exception as e:
            print(f"Error extracting document metadata: {str(e)}")
        
        # Store page count
        structure["metadata"]["page_count"] = len(reader.pages)
        
        # Pattern to identify headings (customize based on your documents)
        heading_patterns = [
            re.compile(r'^(Chapter|Section)\s+\d+\.?\s+(.*?)$', re.MULTILINE),
            re.compile(r'^(\d+\.)\s+([A-Z][^.]+)$', re.MULTILINE),  # 1. Heading
            re.compile(r'^([A-Z][^.]+)$', re.MULTILINE),  # Capitalized text
            re.compile(r'^([A-Z0-9][\w\s]+)$', re.MULTILINE),  # More flexible heading pattern
            re.compile(r'^([\d\.]+)\s+([A-Z][\w\s]+)$', re.MULTILINE)  # Numbered headings
        ]
        
        subheading_patterns = [
            re.compile(r'^(\d+\.\d+\.?)\s+([A-Z].*?)$', re.MULTILINE),  # 1.1 Subheading
            re.compile(r'^\s+([A-Z][^.]+)$', re.MULTILINE),  # Indented capitalized text
            re.compile(r'^(\d+\.\d+\.?\d*)\s+(.+)$', re.MULTILINE)  # Multi-level numbering
        ]
        
        # If no headings are found, create a fallback structure
        fallback_created = False
        
        last_heading = None
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text = page.extract_text()
            
            # Extract headings and subheadings from this page
            headings_found = []
            subheadings_found = []
            
            # Find headings using different patterns
            for pattern in heading_patterns:
                matches = pattern.findall(text)
                if matches:
                    for match in matches:
                        # Handle different pattern group structures
                        if len(match) == 2:
                            if isinstance(match[1], str) and match[1].strip():
                                heading_text = f"{match[0]} {match[1]}".strip()
                                headings_found.append(heading_text)
                        else:
                            heading_text = match[0].strip()
                            if heading_text:
                                headings_found.append(heading_text)
            
            # Find subheadings using different patterns
            for pattern in subheading_patterns:
                matches = pattern.findall(text)
                if matches:
                    for match in matches:
                        # Handle different pattern group structures
                        if len(match) == 2:
                            subheading_text = f"{match[0]} {match[1]}".strip()
                        else:
                            subheading_text = match[0].strip()
                        
                        if subheading_text and subheading_text not in headings_found:
                            subheadings_found.append(subheading_text)
            
            # Register headings in document structure
            for heading in headings_found:
                if heading not in structure["headings"]:
                    structure["headings"].append(heading)
                    structure["hierarchy"][heading] = []
                    structure["page_mapping"][heading] = page_num
                    last_heading = heading
            
            # Register subheadings under the most recently found heading
            if last_heading and subheadings_found:
                for subheading in subheadings_found:
                    if subheading not in structure["hierarchy"][last_heading]:
                        structure["hierarchy"][last_heading].append(subheading)
                        structure["page_mapping"][subheading] = page_num
            
            # Render the page as an image
            pix = doc.load_page(page_num).get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Resize image if too large (optional)
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
        
        # After processing all pages, check if we found any headings
        if not structure["headings"]:
            print("WARNING: No headings detected in document. Creating fallback structure.")
            # Create a fallback structure with document title and page numbers
            title = "Document"
            structure["headings"].append(title)
            structure["hierarchy"][title] = []
            structure["page_mapping"][title] = 0
            
            # Add page numbers as subheadings
            for page_num in range(len(reader.pages)):
                page_heading = f"Page {page_num + 1}"
                structure["hierarchy"][title].append(page_heading)
                structure["page_mapping"][page_heading] = page_num
            
            fallback_created = True
        
        print(f"Document structure extracted: {len(structure['headings'])} headings, " +
              f"{sum(len(subs) for subs in structure['hierarchy'].values())} subheadings, " +
              f"{len(structure['page_images'])} page images")
        
        if fallback_created:
            print("Note: Using fallback structure as no headings were detected")
        
        return structure
    
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
        