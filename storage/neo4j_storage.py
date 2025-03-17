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
    
    def process_document(self, pdf_path: str) -> str:
        """
        Process a PDF document and store its structure in Neo4j.
        
        Args:
            pdf_path: Path to the PDF file
            
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
            
            # Process document structure
            structure = self._extract_document_structure(reader, doc)
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
            "page_images": {}
        }
        
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
            # Create document node
            session.run(
                "CREATE (d:Document {id: $id})",
                id=document_id
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
            # Get all headings and their subheadings
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:HAS_HEADING]->(h:Heading {type: 'main'})
                OPTIONAL MATCH (h)-[:HAS_SUBHEADING]->(s:Heading)
                RETURN h.text as heading, collect(s.text) as subheadings
                ORDER BY h.text
                """,
                doc_id=document_id
            )
            
            structure = {
                "headings": [],
                "hierarchy": {}
            }
            
            for record in result:
                heading = record["heading"]
                subheadings = record["subheadings"]
                
                structure["headings"].append(heading)
                structure["hierarchy"][heading] = [s for s in subheadings if s is not None]
            
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
                
            # Delete all related nodes and relationships
            session.run(
                """
                MATCH (d:Document {id: $doc_id})
                OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
                OPTIONAL MATCH (d)-[:HAS_HEADING]->(h:Heading)
                DETACH DELETE d, p, h
                """,
                doc_id=document_id
            )
            
            return True