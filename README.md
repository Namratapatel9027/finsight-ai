# FinSight AI

A role-aware retrieval-augmented generation (RAG) assistant for exploring FinSolve Technologies' internal reference documents. The project combines a Streamlit chat interface, a FastAPI service, hybrid search, conversational context, and role-based document filtering.

> **Data and security:** `data/hr/hr_data.csv` contains employee-like personal fields, including names, work email addresses, dates of birth, and salaries. Confirm that the file is synthetic or explicitly approved for publication before sharing or deploying this repository. The authentication flow is a demo implementation and is not suitable for production use with real credentials or employee records.

## Features

- Streamlit chat UI backed by a FastAPI service
- Dense vector search in Chroma and BM25 keyword search, combined with Reciprocal Rank Fusion
- LLM-based query understanding, conversational follow-ups, and grounded answers with source names
- Department-aware access filtering for finance, marketing, engineering, general, and HR content
- Structured HR question handling and an evaluation notebook

## Architecture

The high-level system architecture is shown below. The other diagrams cover retrieval, authorization, ingestion, and query routing.

![FinSight AI high-level system architecture](diagrams/Diagram%201%3A%20High-Level%20System%20Architecture%20Diagram.png)

<details>
<summary>View the other architecture diagrams</summary>

### RAG pipeline and retrieval

![RAG pipeline and retrieval flow](diagrams/Diagram%202%3A%20RAG%20Pipeline%20%26%20Retrieval%20Flowchart.png)

### Role-based access control and authentication

![RBAC and authentication sequence](diagrams/Diagram%203%3A%20RBAC%20%26%20Authentication%20Sequence%20Diagram.png)

### Data ingestion and indexing

![Data ingestion and indexing pipeline](diagrams/Diagram%204%3A%20Data%20Ingestion%20%26%20Indexing%20Pipeline.png)

### Query understanding and routing

![Dual-route query understanding and routing](diagrams/Diagram%205%3A%20Dual-Route%20Query%20Understanding%20%26%20Routing%20Decision%20Flowchart.png)

</details>

## Repository layout

```text
app/          FastAPI API, Streamlit UI, retrieval, generation, ingestion, and access control
data/         Knowledge documents and HR CSV used by the demo
diagrams/     Architecture and flow diagrams
evaluation/   RAG evaluation notebook
 tests/       API and frontend-client tests
```

## Requirements

- Python 3.10 or newer
- A Groq API key for LLM responses
- Internet access on the first ingestion run to download the embedding model

## Setup

From the repository root, create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a `.env` file in the repository root and add your Groq key:

```dotenv
GROQ_API_KEY=your_groq_api_key
# Optional; defaults to http://127.0.0.1:8000
FINSOLVE_API_URL=http://127.0.0.1:8000
```

Keep `.env` private; it is ignored by Git. Never commit API keys or real employee data.

## Build the local search index

The Chroma database is generated locally and is not stored in Git. Build it from the files under `data/`:

```bash
python app/ingestion.py
```

This creates `chroma_db/`. Run ingestion again after changing the source documents.

## Run the application

Start the API in one terminal:

```bash
uvicorn api:app --app-dir app --reload
```

Start the Streamlit interface in a second terminal:

```bash
streamlit run app/streamlit_app.py
```

Open the local URL printed by Streamlit (usually <http://localhost:8501>). The interface calls the API at `http://127.0.0.1:8000` by default; set `FINSOLVE_API_URL` in `.env` if your API runs elsewhere.

The API health endpoint is available at <http://127.0.0.1:8000/health>, and FastAPI's interactive API documentation is at <http://127.0.0.1:8000/docs>.

## Run the tests

```bash
PYTHONPATH=app python -m unittest discover -s tests
```

## Notes

- The first model download and index build can take a while.
- `chroma_db/`, `.env`, virtual environments, and local tool configuration are intentionally excluded from Git.
- This repository demonstrates a RAG workflow; review the authentication, data handling, and deployment setup before any production use.
