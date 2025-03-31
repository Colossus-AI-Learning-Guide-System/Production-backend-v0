# 🚀 Colossus Backend - Document Processing and RAG System

## 📖 Overview
Colossus Backend is a sophisticated document processing and Retrieval-Augmented Generation (RAG) system built with Flask. The system provides powerful capabilities for document processing, querying, and structure visualization with GPU acceleration support.

## ✨ Key Features
- 📄 Document Processing and Management
- 🤖 RAG (Retrieval-Augmented Generation) Querying
- 🎯 Document Structure Visualization
- ⚡ GPU-Accelerated Processing (when available)
- 🗄️ Neo4j Database Integration
- 📝 PDF Processing and Text Extraction
- 🌐 RESTful API Interface
- 🔄 CORS Support
- 🔍 Health Monitoring

## 🛠️ Tech Stack
- **🔧 Backend Framework**: Flask
- **💾 Database**: Neo4j
- **🧠 Machine Learning**: PyTorch, Transformers, Sentence-Transformers
- **📑 Document Processing**: PyMuPDF, pdf2image, PyPDF2
- **🔌 API**: RESTful with Flask-CORS
- **🤖 ML Models**: Custom RAG implementation

## 💻 System Requirements
- 🐍 Python 3.8+
- 🎮 CUDA-compatible GPU (optional, for GPU acceleration)
- 🗃️ Neo4j Database
- 💪 16GB+ RAM recommended
- 💾 Storage space for document processing

## 🚀 Quick Start Guide

### 1️⃣ Installation

```bash
# Clone the repository
git clone <repository-url>
cd Production-backend-v0

# Create virtual environment
python -m venv venv

# Activate virtual environment
# For Windows:
venv\Scripts\activate
# For Unix/MacOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2️⃣ Configuration
Create a `.env` file in the root directory:
```env
HOST=localhost
PORT=5000
RAG_MODEL_NAME=your_model_name
NEO4J_URI=your_neo4j_uri
NEO4J_USER=your_neo4j_user
NEO4J_PASSWORD=your_neo4j_password
USE_LOCAL_PIXTRAL=true  # Set to false if not using GPU
```

## 📁 Project Structure
```
Production-backend-v0/
├── 📂 api/                 # API route definitions
├── 📂 config/             # Configuration files
├── 📂 models/             # ML model implementations
├── 📂 services/           # Business logic services
├── 📂 storage/            # Document storage
├── 📂 utils/             # Utility functions
├── 📂 integrations/       # External integrations
├── 📜 app.py             # Main application file
├── 📜 RAGModel.py        # RAG implementation
├── 📜 requirements.txt    # Project dependencies
└── 📜 pyproject.toml     # Project metadata
```

## 🔌 API Reference

### 📄 Document Management
```http
POST /api/document/unified-upload
POST /api/document/upload
GET  /api/document/documents
GET  /api/document/document/{document_id}/original-pdf
GET  /api/document/indexing-status/{document_id}
```

### 🔍 Query System
```http
POST /api/query/query
```

### 🎯 Structure Management
```http
POST   /api/structure/upload
GET    /api/structure/documents
GET    /api/structure/document/{document_id}
DELETE /api/structure/document/{document_id}
GET    /api/structure/document/{document_id}/heading
```

### 🔧 System
```http
GET /health
```

## 🛠️ Development Setup

### 1️⃣ Neo4j Database Setup
1. 📥 Download and install Neo4j
2. 🔧 Create a new database
3. ⚙️ Configure credentials in `.env`
4. ✅ Run `test_neo4j_connection.py`

### 2️⃣ Model Configuration
1. 🤖 Configure RAG model settings
2. 🎮 Set up GPU environment (if available)
3. ⚙️ Configure memory management
4. ✅ Verify model loading

### 3️⃣ Launch Development Server
```bash
python app.py
```

## 🎮 GPU Support
The system automatically detects and utilizes CUDA-compatible GPUs. Monitor GPU usage through the `/health` endpoint.

## 🧪 Testing
1. 🔍 Run API tests:
```bash
python example_client.py
```

2. 🔌 Test database connection:
```bash
python test_neo4j_connection.py
```

## 📚 Documentation
- 📘 API Guide: `frontend_guide.md`
- 📗 Document Processing: `README_document_extraction.md`

## ✅ Best Practices
1. 🔒 Always use virtual environment
2. 🔄 Keep dependencies updated
3. 📊 Monitor GPU memory usage
4. 💾 Regular database backups
5. 📈 Follow API versioning
6. ⚠️ Implement proper error handling

## ❗ Troubleshooting Guide

### 🎮 GPU Issues
- ✔️ Verify CUDA installation
- 📊 Check memory usage
- 🔄 Confirm model compatibility

### 🗄️ Database Issues
- 🔌 Check Neo4j connection
- 🔑 Verify credentials
- 📑 Ensure proper indexing

### 📄 Document Processing Issues
- 🔒 Check file permissions
- 📋 Verify supported formats
- 💾 Monitor storage space

## 📝 Step-by-Step Guide for New Developers

### 1️⃣ Initial Setup (Day 1)
- [ ] Clone repository
- [ ] Set up virtual environment
- [ ] Install dependencies
- [ ] Configure environment variables

### 2️⃣ Database Configuration (Day 1-2)
- [ ] Install Neo4j
- [ ] Create and configure database
- [ ] Set up connection
- [ ] Run connection tests

### 3️⃣ Model Setup (Day 2)
- [ ] Configure GPU environment
- [ ] Set up RAG model
- [ ] Test model loading
- [ ] Verify memory management

### 4️⃣ API Learning (Day 3)
- [ ] Study API documentation
- [ ] Test each endpoint
- [ ] Understand request/response formats
- [ ] Test CORS functionality

### 5️⃣ Document Processing (Day 4)
- [ ] Learn supported formats
- [ ] Test upload functionality
- [ ] Verify processing pipeline
- [ ] Check storage system

### 6️⃣ Query System (Day 5)
- [ ] Study RAG implementation
- [ ] Test query system
- [ ] Optimize response formats
- [ ] Benchmark performance

### 7️⃣ Structure Management (Day 6)
- [ ] Test structure endpoints
- [ ] Implement heading extraction
- [ ] Verify PDF processing
- [ ] Test visualization

### 8️⃣ System Monitoring (Day 7)
- [ ] Set up logging
- [ ] Configure health checks
- [ ] Monitor GPU usage
- [ ] Implement storage management

### 9️⃣ Testing & Deployment (Day 8)
- [ ] Run comprehensive tests
- [ ] Check security settings
- [ ] Verify performance
- [ ] Prepare deployment

### 🔟 Optimization (Day 9-10)
- [ ] Profile application
- [ ] Optimize database queries
- [ ] Enhance GPU utilization
- [ ] Improve response times

## 🤝 Contributing
1. 🔀 Fork repository
2. 🌿 Create feature branch
3. 💻 Make changes
4. 🔄 Push changes
5. 📬 Create Pull Request

## 📄 License
[Add License Information]

## 📞 Contact & Support
[Add Contact Information]

## 🙏 Acknowledgments
- 🏆 Contributors
- 🚀 Open Source Community
- 📚 Documentation Team

---
⭐ Star us on GitHub | 📧 Report Issues | �� Read Documentation 
