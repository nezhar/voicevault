# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VoiceVault is an enterprise voice intelligence platform for hackathon submission (RAISE2025 - Vultr Track). It transforms voice conversations into actionable insights using AI/ML with enterprise-grade security.

**Core Pipeline**: Audio Upload → ASR Provider (Fast Transcription) → LLM Provider (Intelligent Analysis) → VoiceVault Dashboard → Enterprise Integrations

## Architecture

### High-Level System Design
The application follows a microservices architecture with containerized components:

1. **Audio Processing Service**: Handles file uploads, format conversion, and validation
2. **Transcription Service**: Configurable ASR provider integration (Groq) for real-time speech-to-text
3. **Summarization Service**: Configurable LLM provider integration (Groq, Cerebras) for context-aware analysis
4. **Web Interface**: React frontend for enterprise dashboard
5. **Routing Service**: Agentic workflows for automated call classification and routing

### Key Components
- **Backend**: Python FastAPI with async processing
- **Frontend**: React.js enterprise dashboard
- **Database**: PostgreSQL for user management and call history
- **Storage**: Object storage for audio files and processed data
- **Deployment**: Docker containers on Vultr cloud infrastructure

## Required Technologies

### Core Stack
- **ASR Providers**: 
  - **Groq API**: Fast inference engine for transcription (REQUIRED for hackathon)
- **LLM Providers**:
  - **Groq API**: Llama 3.2/3.3 models for dialogue understanding (REQUIRED for hackathon)  
  - **Cerebras API**: High-performance LLM inference with Llama models (OPTIONAL)
- **Vultr Cloud**: Container deployment, storage, and scaling infrastructure (REQUIRED for hackathon)

### Additional Technologies
- **FastAPI**: Python web framework for backend APIs
- **React**: Frontend framework for enterprise dashboard
- **PostgreSQL**: Database for user management and call history
- **Docker**: Containerization for scalable deployment

## API Keys & Environment Setup

### Required API Keys
- **Groq API key**: Get from console.groq.com (REQUIRED)
- **Cerebras API key**: Get from inference.cerebras.ai (OPTIONAL - for LLM provider choice)
- **Hugging Face token**: For Llama model access (if needed)
- **Vultr account**: $255 credits provided for hackathon

### Environment Configuration
```bash
# Set up environment variables

# ASR Configuration
ASR_PROVIDER=groq  # Options: groq
ASR_MODEL=whisper-large-v3-turbo  # Groq models: whisper-large-v3, whisper-large-v3-turbo

# LLM Configuration  
LLM_PROVIDER=groq  # Options: groq, cerebras
LLM_MODEL=llama-3.3-70b-versatile  # Groq: llama-3.3-70b-versatile, llama-3.1-70b-versatile | Cerebras: llama-3.3-70b, llama3.1-8b

# API Keys
GROQ_API_KEY=your_groq_api_key
CEREBRAS_API_KEY=your_cerebras_api_key  # Optional - only needed if using Cerebras LLM provider
HUGGING_FACE_TOKEN=your_hf_token
VULTR_API_KEY=your_vultr_key
```

## Provider Configuration

VoiceVault supports configurable ASR (Automatic Speech Recognition) and LLM (Large Language Model) providers for flexibility and performance optimization. The system has been implemented with full provider abstraction and configuration support.

### ASR Providers

**Groq** (Default - Implemented)
- **Models**: `whisper-large-v3`, `whisper-large-v3-turbo` 
- **API**: Fast inference engine optimized for real-time transcription
- **Configuration**: Set `ASR_PROVIDER=groq` and `ASR_MODEL=whisper-large-v3-turbo`
- **Status**: ✅ Fully implemented with automatic MP3 conversion for compatibility

### LLM Providers

**Groq** (Default - Implemented)
- **Models**: `llama-3.3-70b-versatile`, `llama-3.1-70b-versatile`
- **API**: Fast inference with Llama models for dialogue understanding
- **Configuration**: Set `LLM_PROVIDER=groq` and `LLM_MODEL=llama-3.3-70b-versatile`
- **Status**: ✅ Fully implemented in chat service

**Cerebras** (Alternative - Implemented)
- **Models**: `llama-3.3-70b`, `llama3.1-8b`, `qwen-3-32b`
- **API**: High-performance inference engine with OpenAI-compatible interface
- **Configuration**: Set `LLM_PROVIDER=cerebras` and `LLM_MODEL=llama-3.3-70b`
- **Requirements**: Requires `CEREBRAS_API_KEY` environment variable
- **Status**: ✅ Fully implemented with dynamic client initialization

### Provider Selection Strategy
- **Groq**: Best for hackathon requirements, fast inference, cost-effective
- **Cerebras**: Alternative for high-performance workloads, enterprise use cases  
- **Future**: Easily extensible to support OpenAI, Anthropic, Deepgram providers

### Implementation Details
- **Dynamic Client Initialization**: Both ASR and LLM services now initialize clients based on configured provider
- **Environment Configuration**: All providers configurable via environment variables
- **Graceful Fallback**: System validates provider configuration at startup
- **OpenAI Compatibility**: Added OpenAI client dependency for Cerebras integration

## Development Commands

### Project Setup
```bash
# Create project structure
mkdir -p {backend,frontend,containers,deployment,docs}
mkdir -p backend/{api,services,models,utils}
mkdir -p frontend/{src,components,pages}
mkdir -p containers/{audio-extraction,transcription,summarization}
mkdir -p deployment/vultr

# Initialize git repository
git init
```

### Backend Development
```bash
# Install Python dependencies
pip install fastapi uvicorn groq openai transformers torch pydantic python-multipart aiofiles

# Run development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run with Docker Compose (recommended)
docker-compose up --build
```

### Frontend Development
```bash
# Install Node.js dependencies
npm install react react-dom axios

# Start development server
npm start
```

### Docker Commands
```bash
# Build Docker image
docker build -t voicevault-api .

# Run container
docker run -p 8000:8000 voicevault-api

# Build and run with docker-compose
docker-compose up --build
```

### Deployment Commands
```bash
# Deploy to Vultr
./deployment/vultr/deploy.sh

# Build and push to Vultr registry
docker tag voicevault-api registry.vultr.com/voicevault/api:latest
docker push registry.vultr.com/voicevault/api:latest

# Deploy with Kubernetes
kubectl apply -f deployment/vultr/kubernetes/
```

## Project Structure

```
VoiceVault/
├── docs/                    # Project documentation
│   ├── concept.md          # Project overview and requirements
│   ├── task.md             # Hackathon track requirements
│   ├── implementation.md   # Technical implementation plan
│   └── contraint.md        # Track constraints and requirements
├── backend/                # Python FastAPI backend
│   ├── api/               # API endpoints
│   ├── services/          # Core business logic
│   ├── models/            # Data models
│   └── utils/             # Utility functions
├── frontend/              # React frontend
│   ├── src/               # Source code
│   ├── components/        # React components
│   └── pages/             # Page components
├── containers/            # Docker containers
│   ├── audio-extraction/  # Audio processing container
│   ├── transcription/     # Groq API integration
│   └── summarization/     # Llama model integration
├── deployment/            # Deployment configurations
│   └── vultr/            # Vultr-specific deployment
└── CLAUDE.md             # This file
```

## Key Features to Implement

### Phase 1: Core MVP
- Groq API integration for transcription
- Llama model integration for summarization
- Basic web interface for file upload and results
- Vultr deployment infrastructure

### Phase 2: Enterprise Features
- User authentication and team management
- Multiple summary formats and templates
- Basic CRM integration (REST APIs)
- Action item tracking and notifications

### Phase 3: Advanced Agentic Workflows
- Automated routing and escalation
- Call type classification (sales, support, meeting)
- Priority assessment and stakeholder routing
- Advanced analytics and reporting

## Enterprise Use Cases

### Sales Team
- Lead qualification and CRM integration
- Next steps and follow-up scheduling
- Performance analytics and conversion metrics

### Customer Success
- Support call analysis and issue categorization
- Sentiment monitoring and escalation identification
- Knowledge base and team collaboration

### Human Resources
- Interview summaries and candidate evaluation
- Performance reviews and training sessions
- Compliance documentation

## Hackathon Constraints

### Required Integrations
- **Groq API**: Must be integrated for transcription
- **Llama Model**: Must use Meta's Llama 3.2 or 3.3
- **Vultr Track**: Must be deployed on Vultr infrastructure

### Success Metrics
- **Processing Speed**: Real-time transcription and sub-minute summarization
- **Accuracy**: >95% transcription accuracy with high-quality summaries
- **Scalability**: Handle multiple concurrent uploads and users
- **Enterprise Integration**: Seamless data flow to existing enterprise tools

## Bonus Prize Opportunities

### Additional Technology Integrations
- **Coral Protocol**: Decentralized voice data handling or privacy layers
- **Fetch AI**: Agent orchestration for automated workflow triggers
- **Snowflake**: Enterprise data warehouse integration for call analytics

## Development Notes

### Current Status
- ✅ **Core Infrastructure**: FastAPI backend with Docker containerization
- ✅ **Multi-Provider Support**: Groq and Cerebras LLM providers implemented
- ✅ **ASR Integration**: Groq Whisper models with automatic MP3 conversion  
- ✅ **File Processing**: Audio format conversion and chunking for large files
- ✅ **Authentication System**: Token-based access control
- ✅ **Production Ready**: Docker Compose with PostgreSQL and file storage
- 🚧 **Frontend**: React interface in development 
- 🚧 **Enterprise Features**: CRM integrations and analytics dashboard

### Recent Implementations (Latest Commits)
1. **Multiple LLM Provider Support**: Dynamic configuration for Groq and Cerebras
2. **ASR Provider Configuration**: Configurable Whisper model selection
3. **File Processing Optimization**: Improved audio conversion and validation
4. **Security Enhancements**: Token authentication and secure configuration
5. **Production Deployment**: Docker containerization with environment configuration

### Budget Allocation
- **Development**: ~$68/month (Vultr compute + storage)
- **Scaling**: ~$63/month (additional instances + load balancer)
- **Total Budget**: $255 Vultr credits available

This is a hackathon project focusing on enterprise voice intelligence with agentic workflows for the future of work.