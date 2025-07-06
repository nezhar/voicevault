# VoiceVault

**Enterprise voice intelligence platform for the future of work**

VoiceVault transforms voice conversations into actionable insights using cutting-edge AI/ML with enterprise-grade security. Built for hackathon submission (RAISE2025 - Vultr Track).

## 🚀 Project Overview

VoiceVault addresses the critical workflow bottleneck of manual voice conversation processing in enterprise environments. From sales calls to customer support interactions, we're creating agentic workflows that turn every conversation into a competitive advantage.

### Core Pipeline
```
Audio Upload → Groq (Fast Transcription) → Llama (Intelligent Analysis) → 
VoiceVault Dashboard → Enterprise Integrations
```

### Key Features
- **Fast Processing**: Real-time transcription with Groq API
- **Intelligent Analysis**: Context-aware summarization using Llama models
- **Enterprise Ready**: Secure, scalable, and integration-friendly
- **Agentic Workflows**: Automated routing, action items, and follow-ups
- **Multi-format Support**: Audio and video files, plus URL imports

## 🏗️ Architecture

### Current Components

#### 1. API Service (`/api`)
- **Framework**: FastAPI with async support
- **Database**: PostgreSQL 17 with SQLAlchemy ORM
- **Features**: 
  - File upload handling (audio/video)
  - URL-based entry creation
  - Entry status workflow (NEW → IN_PROGRESS → READY → COMPLETE)
  - RESTful API with automatic documentation

#### 2. Database
- **PostgreSQL 17**: Production-ready database (matches Vultr offering)
- **Migrations**: Alembic for schema management
- **Models**: Entry model with status tracking and metadata

#### 3. Infrastructure
- **Docker Compose**: Local development environment
- **Vultr Ready**: Optimized for Vultr cloud deployment
- **Environment Config**: Flexible configuration management

### Planned Components
- **UI Service**: React TypeScript frontend
- **ASR Service**: Groq API integration for transcription
- **LLM Service**: Llama model integration for summarization
- **Background Workers**: Async processing pipeline

## 📋 API Endpoints

### Entry Management
- `POST /api/entries/upload` - Upload audio/video file
- `POST /api/entries/url` - Create entry from URL
- `GET /api/entries` - List all entries (paginated)
- `GET /api/entries/{id}` - Get specific entry
- `PUT /api/entries/{id}/status` - Update entry status
- `DELETE /api/entries/{id}` - Delete entry

### System
- `GET /` - API information
- `GET /health` - Health check
- `GET /docs` - Interactive API documentation

## 🛠️ Setup & Installation

### Prerequisites
- Docker and Docker Compose
- Git

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/voicevault.git
   cd voicevault
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start services**
   ```bash
   docker compose up --build
   ```

4. **Run database migrations**
   ```bash
   # In a new terminal
   cd api
   docker compose exec api alembic upgrade head
   ```

5. **Access the API**
   - API: http://localhost:8000
   - Documentation: http://localhost:8000/docs
   - Database: localhost:5432

### Environment Configuration

#### Required Variables
```env
# Database
POSTGRES_HOST=your_database_host  # For production (e.g., managed database)
POSTGRES_PORT=5432
POSTGRES_DB=voicevault
POSTGRES_USER=voicevault_user
POSTGRES_PASSWORD=your_secure_password

# API Keys (for production)
GROQ_API_KEY=your_groq_api_key_here
HUGGINGFACE_TOKEN=your_huggingface_token_here
```

#### S3 Storage Configuration

**Production (S3-Compatible Storage)**
```env
# Vultr Object Storage
S3_ENDPOINT_URL=https://ewr1.vultrobjects.com
S3_ACCESS_KEY=your_s3_access_key
S3_SECRET_KEY=your_s3_secret_key
S3_BUCKET_NAME=voicevault-prod

# AWS S3 (alternative)
# S3_ENDPOINT_URL=https://s3.amazonaws.com
# S3_ACCESS_KEY=your_aws_access_key
# S3_SECRET_KEY=your_aws_secret_key
```

**Local Development (MinIO)**
```env
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=voicevault
```

#### Container Registry Configuration
```env
# Leave empty for local builds
REGISTRY=
VERSION=latest

# For Vultr Container Registry
REGISTRY=https://fra.vultrcr.com/raise2025/
VERSION=v1.0.0
```

#### Optional Variables
```env
# Ports
API_PORT=8000
POSTGRES_PORT=5432

# File Storage
UPLOAD_DIR=uploads
MAX_FILE_SIZE=524288000  # 500MB

# Processing
PROCESSING_TIMEOUT=3600  # 1 hour
```

## 🚀 Deployment

### Local Development
```bash
# Use local database and MinIO for S3 storage
cp .env.local.example .env
docker-compose up --build
```

### Production (External Services)
```bash
# Use external database and S3 storage
cp .env.example .env
# Edit .env with your database host and S3 credentials
docker-compose -f compose.yml -f compose.prod.yml up
```

**Production Environment Variables:**
- `POSTGRES_HOST`: Your managed database host (e.g., Vultr Managed Database)
- `S3_ENDPOINT_URL`: Your S3 provider endpoint
- Container registry credentials for image deployment

## 🎯 Hackathon Requirements

### ✅ Implemented
- **Vultr Track**: Enterprise-ready web application architecture
- **FastAPI Backend**: RESTful API with async support
- **PostgreSQL 17**: Production database (Vultr compatible)
- **Docker Containerization**: Scalable deployment ready
- **File Upload System**: Multi-format audio/video support

### 🔄 In Progress
- **Groq API Integration**: Fast transcription service
- **Llama Model Integration**: Intelligent summarization
- **React Frontend**: Enterprise dashboard UI
- **Background Processing**: Async ASR pipeline

### 📋 Planned
- **Vultr Deployment**: Cloud infrastructure setup
- **Agentic Workflows**: Automated routing and actions
- **Enterprise Integrations**: CRM, Slack, email notifications
- **Advanced Analytics**: Call insights and reporting

## 🎨 Technology Stack

### Backend
- **FastAPI**: High-performance async web framework
- **SQLAlchemy**: ORM with PostgreSQL support
- **Alembic**: Database migration management
- **Pydantic**: Data validation and serialization
- **Groq**: Fast AI inference for transcription
- **Transformers**: Hugging Face for Llama models

### Database
- **PostgreSQL 17**: Production-ready relational database
- **pgAdmin**: Database administration (optional)

### Infrastructure
- **Docker**: Containerization
- **Docker Compose**: Multi-service orchestration
- **Vultr**: Cloud deployment platform
- **Nginx**: Reverse proxy and load balancer (planned)

### Frontend (Planned)
- **React**: Modern UI framework
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first styling
- **Axios**: HTTP client for API communication

## 📊 Entry Status Workflow

```
NEW → IN_PROGRESS → READY → COMPLETE
 ↓         ↓          ↓         ↓
Upload   ASR       LLM       User
       Running   Analysis   Marked
```

- **NEW**: Just uploaded, queued for processing
- **IN_PROGRESS**: ASR (Automatic Speech Recognition) running
- **READY**: Transcript ready, available for LLM interaction
- **COMPLETE**: Processing finished, marked complete by user

## 🔧 Development

### Project Structure
```
voicevault/
├── api/                    # FastAPI backend
│   ├── app/               # Application code
│   │   ├── api/          # API routes
│   │   ├── core/         # Configuration
│   │   ├── db/           # Database setup
│   │   ├── models/       # Data models
│   │   └── services/     # Business logic
│   ├── alembic/          # Database migrations
│   ├── requirements.txt  # Python dependencies
│   └── Dockerfile       # Container definition
├── ui/                    # React frontend (planned)
├── docs/                  # Project documentation
├── compose.yml           # Docker Compose configuration
├── .env.example          # Environment template
└── README.md            # This file
```

### Running Tests
```bash
# Backend tests
cd api
python -m pytest

# Integration tests
docker compose run api python -m pytest tests/
```

### Database Operations
```bash
# Create new migration
cd api
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## 🚀 Deployment

### Local Development
```bash
docker compose up --build
```

### Vultr Production
```bash
# Build for production
docker compose -f compose.prod.yml build

# Deploy to Vultr
./deploy/vultr-deploy.sh
```

## 📈 Roadmap

### Phase 1: Core MVP ✅
- [x] FastAPI backend with PostgreSQL
- [x] Docker containerization
- [x] File upload system
- [x] Entry management API
- [x] Database migrations

### Phase 2: AI Integration 🔄
- [ ] Groq API integration for transcription
- [ ] Llama model integration for summarization
- [ ] Background processing pipeline
- [ ] Error handling and retry logic

### Phase 3: Frontend & UX 📋
- [ ] React TypeScript frontend
- [ ] Enterprise dashboard UI
- [ ] File upload interface
- [ ] Results visualization

### Phase 4: Enterprise Features 📋
- [ ] User authentication and teams
- [ ] CRM integrations
- [ ] Slack/Teams notifications
- [ ] Advanced analytics

### Phase 5: Agentic Workflows 📋
- [ ] Automated call routing
- [ ] Action item extraction
- [ ] Follow-up scheduling
- [ ] Sentiment analysis

## 🏆 Success Metrics

### Technical
- **Processing Speed**: Real-time transcription, <30s summarization
- **Accuracy**: >95% transcription accuracy
- **Scalability**: Handle 100+ concurrent uploads
- **Reliability**: 99.9% uptime

### Business
- **Enterprise Adoption**: Active team usage
- **Time Savings**: Quantifiable documentation reduction
- **Integration Success**: Seamless CRM/tool integration
- **Customer Satisfaction**: Positive feedback on summary quality

## 🤝 Contributing

This is a hackathon project for RAISE2025. Development is currently focused on meeting hackathon requirements and demonstrating enterprise voice intelligence capabilities.

### Development Guidelines
1. Follow existing code patterns
2. Add tests for new features
3. Update documentation
4. Use conventional commits

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🎯 Hackathon Context

**RAISE2025 - Vultr Track: Agentic Workflows for the Future of Work**

Building a web-based enterprise agent that transforms voice conversations into actionable insights, deployed on Vultr infrastructure and optimized for real-world business use cases.

---

*VoiceVault - Transforming Enterprise Conversations into Competitive Advantage*