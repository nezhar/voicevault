# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VoiceVault is an enterprise voice intelligence platform for hackathon submission (RAISE2025 - Vultr Track). It transforms voice conversations into actionable insights using AI/ML with enterprise-grade security.

**Core Pipeline**: Audio Upload → Groq (Fast Transcription) → Llama (Intelligent Analysis) → VoiceVault Dashboard → Enterprise Integrations

## Architecture

### High-Level System Design
The application follows a microservices architecture with containerized components:

1. **Audio Processing Service**: Handles file uploads, format conversion, and validation
2. **Transcription Service**: Groq API integration for real-time speech-to-text
3. **Summarization Service**: Llama model integration for context-aware analysis
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
- **Groq API**: Fast inference engine for transcription (REQUIRED for hackathon)
- **Llama 3.2/3.3**: Advanced language model for dialogue understanding (REQUIRED for hackathon)
- **Vultr Cloud**: Container deployment, storage, and scaling infrastructure (REQUIRED for hackathon)

### Additional Technologies
- **FastAPI**: Python web framework for backend APIs
- **React**: Frontend framework for enterprise dashboard
- **PostgreSQL**: Database for user management and call history
- **Docker**: Containerization for scalable deployment

## API Keys & Environment Setup

### Required API Keys
- **Groq API key**: Get from console.groq.com
- **Hugging Face token**: For Llama model access
- **Vultr account**: $255 credits provided for hackathon

### Environment Configuration
```bash
# Set up environment variables
GROQ_API_KEY=your_groq_api_key
HUGGING_FACE_TOKEN=your_hf_token
VULTR_API_KEY=your_vultr_key
```

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
pip install fastapi uvicorn groq transformers torch pydantic python-multipart aiofiles

# Run development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
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
- Project is in planning/documentation phase
- No implementation code exists yet
- All architecture is conceptual based on hackathon requirements

### Next Steps for Implementation
1. Set up development environment with required APIs
2. Create FastAPI backend with Groq integration
3. Build React frontend for file upload and results display
4. Implement Llama model for summarization
5. Deploy to Vultr infrastructure
6. Add enterprise features and agentic workflows

### Budget Allocation
- **Development**: ~$68/month (Vultr compute + storage)
- **Scaling**: ~$63/month (additional instances + load balancer)
- **Total Budget**: $255 Vultr credits available

This is a hackathon project focusing on enterprise voice intelligence with agentic workflows for the future of work.