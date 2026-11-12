# Spotify Personalized AI Memory System

An AI-powered memory system designed to understand, store, retrieve, and manage user preferences and contextual information to enable personalized music experiences.

The system combines Large Language Models (LLMs), Retrieval-Augmented Generation (RAG), vector search, graph-based memory representation, and a modular backend architecture to maintain and retrieve user-specific memories across conversations.

## Overview

Traditional recommendation systems primarily rely on listening history and explicit interactions. This project explores a more contextual approach by enabling an AI system to remember user preferences, understand relationships between entities, and retrieve relevant information from previously stored memories.

The application uses an LLM-powered interaction layer supported by a structured memory architecture. User inputs are processed, converted into structured memory representations, persisted across multiple storage systems, and retrieved when relevant to subsequent requests.

## Key Features

- **Personalized AI Memory:** Stores and retrieves user-specific preferences and contextual memories.
- **LLM Integration:** Uses an LLM to interpret natural-language requests and facilitate memory-related operations.
- **Retrieval-Augmented Generation (RAG):** Retrieves relevant stored information to provide context-aware responses.
- **Vector-Based Retrieval:** Uses Qdrant for embedding-based semantic similarity search.
- **Graph-Based Memory Representation:** Uses Neo4j to represent relationships between entities and memory information.
- **Entity Resolution:** Identifies and maps entities such as artists, tracks, and albums to canonical entity records.
- **External Music Metadata Integration:** Integrates MusicBrainz for music entity identification and metadata retrieval.
- **Memory Lifecycle Management:** Supports adding, retrieving, correcting, and deleting memories.
- **Consent Management:** Implements OPT_IN, OPT_OUT, and PAUSED consent states, with RESUME as an operation to transition from PAUSED to OPT_IN.
- **Modular Backend Architecture:** Separates API handling, memory processing, orchestration, retrieval, and persistence responsibilities.
- **Full-Stack Application:** Provides a React-based frontend integrated with a FastAPI backend.

## System Architecture

The application follows a modular architecture in which different backend components handle specific responsibilities.

### High-Level Architecture

```text
                 React Frontend
                       |
                       v
                 FastAPI API Layer
                       |
                       v
              Gemini MCP Agent
                       |
                       v
              MCP Tool Integration
                       |
                       v
              Backend Orchestration
                       |
          +------------+-------------+
          |            |             |
          v            v             v
     Memory         Retrieval     Entity Resolution
     Processing      Services        Services
          |            |             |
          +------------+-------------+
                       |
          +------------+-------------+
          |            |             |
          v            v             v
      PostgreSQL      Qdrant        Neo4j
      Structured      Vector        Graph
      Data            Storage       Storage
                       |
                       v
                 MusicBrainz
                Metadata Source
```

*The diagram illustrates the logical component flow. Actual execution paths may vary depending on the operation.*

### Backend Components

| Component | Responsibility |
|---|---|
| FastAPI API Layer | Receives frontend requests, invokes backend operations, and returns structured JSON responses. |
| Gemini MCP Agent | Interprets user requests and coordinates memory-related tool calls through the MCP interface. |
| MCP Integration | Exposes backend capabilities to the AI agent through structured tools. |
| Orchestration Layer | Coordinates memory processing, consent enforcement, and interactions between backend services. |
| Memory Processing | Handles memory extraction, creation, correction, and lifecycle operations. |
| Retrieval Services | Retrieves relevant memories using semantic and structured retrieval mechanisms. |
| Entity Resolution | Identifies canonical entities and manages external entity mappings. |
| MusicBrainz Integration | Retrieves music metadata and external identifiers. |

## Technology Stack

### Backend
- Python
- FastAPI
- REST APIs
- Model Context Protocol (MCP)

### AI and Retrieval
- Google Gemini
- Retrieval-Augmented Generation (RAG)
- Sentence Transformers
- all-MiniLM-L6-v2 embeddings

### Databases and Storage
- PostgreSQL – Structured and relational data storage
- Qdrant – Vector database for semantic retrieval
- Neo4j – Graph database for relationship-based memory representation

### Frontend
- React.js
- JavaScript
- CSS

### Infrastructure and Deployment
- Docker
- GitHub
- Publicly deployed frontend and backend

## Memory Management Workflow

The system supports memory operations throughout the memory lifecycle.

### 1. Memory Creation
- Receives user input through the application.
- Processes the request using the AI and backend processing components.
- Extracts relevant memory information.
- Resolves associated entities where applicable.
- Persists the resulting information in the appropriate storage systems.

### 2. Memory Retrieval
- Interprets the user's retrieval request.
- Searches relevant stored memories.
- Uses semantic retrieval and structured memory relationships.
- Returns relevant contextual information to the application.

### 3. Memory Correction
- Identifies the memory that needs modification.
- Updates the relevant memory information.
- Maintains consistency between associated records and representations.

### 4. Memory Deletion
- Identifies the target memory.
- Executes the deletion operation.
- Maintains consistency across associated memory and entity representations.

## Consent Management

The system incorporates consent-aware memory operations to control whether user information can be processed and retained.

| Consent State | Description |
|---|---|
| OPT_IN | Allows permitted memory operations. |
| OPT_OUT | Prevents memory processing and storage according to the consent policy. |
| PAUSED | Temporarily suspends memory operations. |

**RESUME** is an operation that transitions a user's consent state from PAUSED back to OPT_IN. It is not a separate persistent consent state.

Consent checks are incorporated into the memory-processing workflow to ensure that memory operations follow the user's consent preferences.

## Entity Resolution and Music Metadata

The system uses entity resolution to identify and maintain consistent representations of music-related entities.

Supported entity categories include:
- Artists
- Tracks
- Albums

MusicBrainz provides external metadata and identifiers that help associate extracted entities with canonical music records.

The entity-resolution process helps avoid duplicate entity creation and maintain consistent external mappings.

## Project Structure

The following is an illustrative structure. Adjust the paths to match the actual repository.

```text
spotify-ai-memory-system/
│
├── backend_memory_pipeline/
│   ├── api/
│   ├── agents/
│   ├── auth/
│   ├── context_composition/
│   ├── embedding/
│   ├── entity_resolution/
│   ├── event_validation/
│   ├── graph_memory/
│   ├── ingestion/
│   ├── integration/
│   ├── language_detection/
│   ├── mcp/
│   ├── memory_extraction/
│   ├── memory_lifecycle/
│   ├── orchestration/
│   ├── persistence/
│   ├── policy_consent/
│   ├── response_generation/
│   └── retrieval/
│   ├── session_management/
│   ├── spotify/
│   └── tests/
│
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
│   
├── docker-compose.neo4j.yml
├──  docker-compose.postgres.yml
├──  docker-compose.qdrant.yml
├── .gitignore
├── requirements.txt
└── README.md
```

## Installation and Setup

### Prerequisites

Ensure the following are installed:

- Python
- Node.js and npm
- Docker Desktop
- PostgreSQL
- Qdrant
- Neo4j

### 1. Clone the Repository

```bash
git clone <repository-url>
cd spotify-ai-memory-system
```

### 2. Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the required environment variables using the provided `.env.example` file.

Start the backend using the actual application entry point:

```bash
uvicorn app.main:app --reload
```

### 3. Frontend Setup

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Configure the frontend API base URL to point to the running backend.

### 4. Database and Infrastructure Setup

Configure PostgreSQL, Qdrant, and Neo4j using the project's Docker Compose configuration or the corresponding service configurations.

Start the configured services:

```bash
docker compose up -d
```

Verify the running containers:

```bash
docker ps
```

Ensure the backend environment variables contain the correct database connection details.

> The commands and paths above are setup templates. Follow the actual repository configuration and environment variable names when running the project.

## Environment Variables

Create a `.env` file in the backend directory and configure the required credentials and service URLs.

Typical configuration categories include:

```env
GEMINI_API_KEY=your_gemini_api_key

DATABASE_URL=your_postgresql_connection_url

QDRANT_URL=your_qdrant_url
QDRANT_API_KEY=your_qdrant_api_key

NEO4J_URI=your_neo4j_uri
NEO4J_USERNAME=your_neo4j_username
NEO4J_PASSWORD=your_neo4j_password

FRONTEND_URL=your_frontend_url
```

Use the exact environment variable names expected by the application. Never commit `.env` files, API keys, database passwords, or other credentials to GitHub.

## Deployment

The application includes separately deployed frontend and backend components.

- Frontend: React application deployed publicly.
- Backend: FastAPI application deployed as a separate service.
- Database services: PostgreSQL, Qdrant, and Neo4j configured as backend dependencies.

The frontend communicates with the backend through API requests, while the backend coordinates the required memory operations and database interactions.

## Future Enhancements

- Knowledge graph-assisted entity resolution.
- Graph-based contextual music recommendations.
- Personalized recommendation ranking.
- Explainable recommendations based on user preferences.
- Improved feedback-driven preference learning.
- Enhanced memory consistency and synchronization.
- Expanded automated testing and monitoring.

## Project Objective

The primary objective is to explore how AI-powered memory systems can move beyond isolated conversational interactions by maintaining persistent, structured, and contextual user information.

By combining LLMs, vector retrieval, graph-based relationships, structured storage, and modular backend orchestration, the project provides a foundation for building more personalized and context-aware music experiences.

## License

Specify the appropriate license for this repository before making the project publicly available.
