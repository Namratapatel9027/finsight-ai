from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
ENV_FILE = PROJECT_ROOT / ".env"


# ============================================================
# CHROMA
# ============================================================

COLLECTION_NAME = "finsolve_documents"


# ============================================================
# EMBEDDINGS
# ============================================================

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


# ============================================================
# LLM
# ============================================================

GROQ_MODEL = "openai/gpt-oss-20b"

TEMPERATURE = 0.1
MAX_TOKENS = 800


# ============================================================
# CHUNKING
# ============================================================

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


# ============================================================
# RETRIEVAL
# ============================================================

RETRIEVAL_K = 5

DENSE_K = 10
BM25_K = 10

# Reciprocal Rank Fusion constant
RRF_K = 60


# ============================================================
# AUGMENTATION
# ============================================================

# Number of candidates passed into augmentation
AUGMENTATION_K = 10

# Number of final chunks passed to the LLM
FINAL_CONTEXT_K = 5


# ============================================================
# DATA
# ============================================================

SUPPORTED_EXTENSIONS = {
    ".md",
    ".txt",
    ".csv",
}
