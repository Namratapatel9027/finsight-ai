import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from config import (
    ENV_FILE,
    GROQ_MODEL,
    TEMPERATURE,
    MAX_TOKENS,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(ENV_FILE)


# ============================================================
# LLM
# ============================================================

def create_llm():

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing from .env"
        )

    return ChatGroq(
        model=GROQ_MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )


# ============================================================
# PROMPT
# ============================================================

def create_prompt():

    return ChatPromptTemplate.from_template(
        """
You are an internal assistant for FinSolve Technologies.

Answer the user's question using only the provided
company context.

RULES:

1. Use only information supported by the context.
2. Do not invent facts, numbers, people, dates, or events.
3. Read ALL provided sources before answering.
4. If relevant evidence exists, answer directly.
5. Do not refuse simply because one source is insufficient.
6. If only partial information is available, provide the
   supported information and clearly state what is unavailable.
7. Distinguish actual results from targets, projections,
   benchmarks, and plans.
8. Do not infer facts from employee titles or filenames.
9. For numerical questions, preserve the exact values from
   the source.
10. When the source identifies a reporting period or year,
    include it in the answer, especially for quarterly data.
11. Keep the answer concise and useful.
12. At the end, provide the source file names used.

If the context genuinely does not contain enough information,
say:

"The available company documents do not contain enough
information to answer this."

CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
"""
    )


# ============================================================
# CONTEXT BUILDER
# ============================================================

def build_context(results):

    if not results:
        return "No relevant company information was retrieved."

    context_parts = []

    for index, result in enumerate(
        results,
        start=1,
    ):

        metadata = result.get("metadata", {})

        source = metadata.get(
            "source",
            "unknown",
        )

        department = metadata.get(
            "department",
            "unknown",
        )

        sections = []

        for key in (
            "h1",
            "h2",
            "h3",
            "h4",
        ):

            value = metadata.get(key)

            if value:
                sections.append(value)

        section = " | ".join(sections)

        context_parts.append(
            f"""
SOURCE {index}

Department:
{department}

File:
{source}

Section:
{section}

Content:
{result["document"]}
"""
        )

    return "\n".join(context_parts)


# ============================================================
# GENERATE ANSWER
# ============================================================

def generate_answer(
    llm,
    prompt,
    question,
    results,
):

    context = build_context(results)

    messages = prompt.format_messages(
        context=context,
        question=question,
    )

    response = llm.invoke(messages)

    return response.content.strip()


# ============================================================
# COMPLETE GENERATOR
# ============================================================

def create_generator():

    llm = create_llm()
    prompt = create_prompt()

    return llm, prompt
