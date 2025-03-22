# Enhanced Document Structure API - Frontend Integration Guide

This guide explains how to integrate the enhanced document structure API with your Next.js frontend application.

## Available Endpoints

### 1. Basic Document Structure Endpoints

- **Get Document Structure**: `GET /api/structure/document/{document_id}/structured`

  - Returns the basic document structure
  - Add `?enhanced=true` to get the enhanced version if available

- **Get Document Page Image**: `GET /api/structure/document/{document_id}/page/{page_number}`

  - Returns the image for a specific page (1-indexed)

- **Get Visual Reference**: `GET /api/structure/document/{document_id}/visual/{reference}`
  - Returns a specific visual element (figure, table, etc.) with its page image

### 2. Enhanced Structure Endpoints

- **Check if Enhanced Structure is Available**: `GET /api/structure/document/{document_id}/enhanced-available`

  - Returns status of enhanced structure availability and timestamp

- **Generate Enhanced Structure**: `GET /api/structure/document/{document_id}/enhanced`
  - By default, returns existing enhanced structure if available
  - Add `?force=true` to force regeneration with Claude 3.5 Sonnet
  - This is a processing-intensive operation that may take some time

## Integration Examples

### Checking and Using Enhanced Structure

```javascript
import { useState, useEffect } from "react";

export default function DocumentViewer({ documentId }) {
  const [documentStructure, setDocumentStructure] = useState(null);
  const [isEnhancedAvailable, setIsEnhancedAvailable] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [useEnhanced, setUseEnhanced] = useState(false);

  // Check if enhanced structure is available
  useEffect(() => {
    async function checkEnhancedAvailability() {
      try {
        const response = await fetch(
          `/api/structure/document/${documentId}/enhanced-available`
        );
        if (!response.ok)
          throw new Error("Failed to check enhanced availability");

        const data = await response.json();
        setIsEnhancedAvailable(data.available);

        // Auto-use enhanced structure if available
        if (data.available) {
          setUseEnhanced(true);
        }
      } catch (err) {
        console.error("Error checking enhanced structure:", err);
        // Continue with regular structure if check fails
      }
    }

    if (documentId) {
      checkEnhancedAvailability();
    }
  }, [documentId]);

  // Fetch document structure (regular or enhanced)
  useEffect(() => {
    async function fetchDocumentStructure() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `/api/structure/document/${documentId}/structured?enhanced=${useEnhanced}`
        );

        if (!response.ok) {
          throw new Error(
            `Error fetching document structure: ${response.statusText}`
          );
        }

        const data = await response.json();
        setDocumentStructure(data);
      } catch (err) {
        setError(err.message);
        console.error("Error fetching document structure:", err);
      } finally {
        setIsLoading(false);
      }
    }

    if (documentId) {
      fetchDocumentStructure();
    }
  }, [documentId, useEnhanced]);

  // Toggle between regular and enhanced structure
  const toggleEnhancedStructure = () => {
    if (!isEnhancedAvailable && !useEnhanced) {
      // If enhanced not available, generate it
      generateEnhancedStructure();
    } else {
      // Otherwise just toggle
      setUseEnhanced(!useEnhanced);
    }
  };

  // Generate enhanced structure
  const generateEnhancedStructure = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/structure/document/${documentId}/enhanced?force=true`
      );

      if (!response.ok) {
        throw new Error(
          `Error generating enhanced structure: ${response.statusText}`
        );
      }

      const data = await response.json();
      setDocumentStructure(data);
      setIsEnhancedAvailable(true);
      setUseEnhanced(true);
    } catch (err) {
      setError(err.message);
      console.error("Error generating enhanced structure:", err);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) return <div>Loading document structure...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!documentStructure) return <div>No document structure available</div>;

  return (
    <div>
      <div className="controls">
        <button onClick={toggleEnhancedStructure} disabled={isLoading}>
          {useEnhanced
            ? "Switch to Regular Structure"
            : isEnhancedAvailable
            ? "Switch to Enhanced Structure"
            : "Generate Enhanced Structure"}
        </button>

        {useEnhanced && (
          <span className="badge">Enhanced Structure Active</span>
        )}
      </div>

      <h1>{documentStructure.document_id}</h1>

      <div className="document-structure">
        {documentStructure.document_structure.map((section, index) => (
          <div key={index} className="section">
            <h2>{section.heading}</h2>
            <p>Page {section.page_reference}</p>

            {section.subheadings.map((subheading, subIndex) => (
              <div key={subIndex} className="subheading">
                <h3>{subheading.title}</h3>
                <p>Page {subheading.page_reference}</p>

                {/* Display visual references if available */}
                {subheading.visual_references &&
                  subheading.visual_references.length > 0 && (
                    <div className="visuals">
                      <h4>Visual Elements</h4>
                      {subheading.visual_references.map((visual, visIndex) => (
                        <div key={visIndex} className="visual">
                          <p>{visual.image_caption}</p>
                          <p>Page {visual.page_reference}</p>
                          <button
                            onClick={() =>
                              viewVisual(documentId, visual.image_reference)
                            }
                          >
                            View Visual
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// Function to view a visual element
function viewVisual(documentId, reference) {
  // This would open a modal or navigate to a page displaying the visual
  window.open(
    `/api/structure/document/${documentId}/visual/${reference}`,
    "_blank"
  );
}
```

### Using the Document in a Document Viewer

```javascript
import { useState } from "react";
import DocumentViewer from "../components/DocumentViewer";
import DocumentList from "../components/DocumentList";

export default function DocumentsPage() {
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);

  return (
    <div className="documents-page">
      <div className="sidebar">
        <h2>Your Documents</h2>
        <DocumentList onSelectDocument={setSelectedDocumentId} />
      </div>

      <div className="main-content">
        {selectedDocumentId ? (
          <DocumentViewer documentId={selectedDocumentId} />
        ) : (
          <div className="no-selection">Select a document to view</div>
        )}
      </div>
    </div>
  );
}
```

## Error Handling

When integrating with the API, it's important to handle potential errors:

1. **Document not found** (404): Check if the document ID is valid
2. **PDF data not available** (404): Some documents might not have stored PDF data
3. **Processing errors** (500): If Claude 3.5 Sonnet encounters issues processing the document

For the enhanced structure generation, consider implementing:

1. **Loading states**: Enhanced processing can take time
2. **Fallback to regular structure**: If enhanced generation fails
3. **Error reporting**: Log details for debugging

## Best Practices

1. **Caching**: Cache document structure responses to reduce API calls
2. **Lazy Loading**: Load page images only when needed
3. **User Experience**: Show loading indicators during enhanced structure generation
4. **Progressive Enhancement**: First show regular structure, then enhance if requested
5. **Error Handling**: Provide graceful fallbacks if enhanced structure fails
6. **Pagination**: For large documents, paginate through sections

## Advanced Use Cases

### 1. Document Structure Comparison

Allow users to compare regular vs. enhanced structure side by side:

```javascript
function ComparisonView({ documentId }) {
  const [regularStructure, setRegularStructure] = useState(null);
  const [enhancedStructure, setEnhancedStructure] = useState(null);

  // Fetch both structures and display side by side
  // ...
}
```

### 2. Analytics Integration

Track which structure users prefer and identify documents that benefit most from enhancement:

```javascript
function trackStructureSelection(documentId, isEnhanced) {
  analytics.track("structure_selection", {
    document_id: documentId,
    structure_type: isEnhanced ? "enhanced" : "regular",
  });
}
```

### 3. Document Search

The enhanced structure provides better context for search functionality:

```javascript
async function searchInDocument(documentId, searchTerm, useEnhanced = true) {
  const response = await fetch(
    `/api/structure/document/${documentId}/structured?enhanced=${useEnhanced}`
  );
  const data = await response.json();

  const results = [];
  data.document_structure.forEach((section) => {
    section.subheadings.forEach((subheading) => {
      if (subheading.context.includes(searchTerm)) {
        results.push({
          heading: section.heading,
          subheading: subheading.title,
          page: subheading.page_reference,
          context: subheading.context,
        });
      }
    });
  });

  return results;
}
```
