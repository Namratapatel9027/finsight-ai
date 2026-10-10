import pandas as pd

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

from config import (
    DATA_DIR,
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    SUPPORTED_EXTENSIONS,
)


def get_department(path):
    relative_path = path.relative_to(DATA_DIR)

    if len(relative_path.parts) >= 2:
        return relative_path.parts[0]

    return "general"


def base_metadata(path):
    return {
        "department": get_department(path),
        "source": path.name,
        "file_path": str(
            path.relative_to(DATA_DIR.parent)
        ),
        "file_type": path.suffix.lower().replace(".", ""),
    }


def load_markdown(path):
    return Document(
        page_content=path.read_text(
            encoding="utf-8",
            errors="ignore",
        ),
        metadata=base_metadata(path),
    )


def load_text(path):
    return Document(
        page_content=path.read_text(
            encoding="utf-8",
            errors="ignore",
        ),
        metadata=base_metadata(path),
    )


def load_csv(path):
    dataframe = pd.read_csv(path)

    documents = []

    for row_number, row in dataframe.iterrows():

        content = "\n".join(
            f"{column}: {row[column]}"
            for column in dataframe.columns
        )

        metadata = base_metadata(path)
        metadata["row_number"] = int(row_number)

        documents.append(
            Document(
                page_content=content,
                metadata=metadata,
            )
        )

    return documents


def load_documents():

    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"Data directory does not exist: {DATA_DIR}"
        )

    documents = []

    for path in sorted(DATA_DIR.rglob("*")):

        if not path.is_file():
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        extension = path.suffix.lower()

        if extension == ".md":
            documents.append(load_markdown(path))

        elif extension == ".txt":
            documents.append(load_text(path))

        elif extension == ".csv":
            documents.extend(load_csv(path))

    return documents


def split_markdown(document):

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
            ("####", "h4"),
        ],
        strip_headers=False,
    )

    sections = splitter.split_text(
        document.page_content
    )

    result = []

    for section in sections:

        metadata = document.metadata.copy()
        metadata.update(section.metadata)

        result.append(
            Document(
                page_content=section.page_content,
                metadata=metadata,
            )
        )

    return result


def create_chunks(documents):

    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],
    )

    chunks = []

    for document in documents:

        file_type = document.metadata["file_type"]

        if file_type == "md":

            sections = split_markdown(document)

            for section in sections:

                if len(section.page_content) <= CHUNK_SIZE:
                    chunks.append(section)
                else:
                    chunks.extend(
                        recursive_splitter.split_documents(
                            [section]
                        )
                    )

        elif file_type == "txt":

            chunks.extend(
                recursive_splitter.split_documents(
                    [document]
                )
            )

        elif file_type == "csv":

            chunks.append(document)

    return chunks


def create_embeddings():

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={
            "normalize_embeddings": True
        },
    )


def create_vector_store(chunks):

    embeddings = create_embeddings()

    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
        collection_name=COLLECTION_NAME,
    )


def main():

    documents = load_documents()

    if not documents:
        raise RuntimeError(
            f"No supported documents found in {DATA_DIR}"
        )

    chunks = create_chunks(documents)

    print(
        f"Loaded {len(documents)} documents/records "
        f"→ created {len(chunks)} chunks."
    )

    create_vector_store(chunks)

    print(
        f"ChromaDB created at: {CHROMA_DIR}"
    )


if __name__ == "__main__":
    main()