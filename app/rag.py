import json
import re

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate

from access_control import (
    can_access_department,
    can_access_hr_data,
    get_allowed_departments,
    normalize_role,
    required_department_for_intent,
)
from config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    DENSE_K,
    BM25_K,
    RRF_K,
    AUGMENTATION_K,
    FINAL_CONTEXT_K,
)

from retriever import HybridRetriever
from generator import (
    create_generator,
    generate_answer,
)


# ============================================================
# INITIALIZE RAG COMPONENTS
# ============================================================

embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL
)

vector_store = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    persist_directory=str(CHROMA_DIR),
)

retriever = HybridRetriever(
    vector_store=vector_store,
    dense_k=DENSE_K,
    bm25_k=BM25_K,
    rrf_k=RRF_K,
)

llm, generation_prompt = create_generator()


# ============================================================
# SHORT-TERM CONVERSATION MEMORY
# ============================================================

# Keep the 25 most recent user/assistant turns (50 messages).
MAX_HISTORY_TURNS = 25

# Safety limit so the router prompt does not grow indefinitely.
MAX_HISTORY_CHARS = 6000

conversation_history = []


def get_conversation_history(history_messages=None):
    """
    Return recent conversation history within the configured limits.
    """

    messages = (
        conversation_history
        if history_messages is None
        else history_messages
    )
    recent_history = messages[
        -(MAX_HISTORY_TURNS * 2):
    ]

    if not recent_history:
        return "No previous conversation."

    history_text = []

    for message in recent_history:

        role = message["role"]
        content = message["content"]

        if role == "user":
            history_text.append(
                f"User: {content}"
            )

        elif role == "assistant":
            history_text.append(
                f"Assistant: {content}"
            )

    history = "\n".join(history_text)

    # Keep the newest complete turns within the prompt-size limit.
    while (
        len(history) > MAX_HISTORY_CHARS
        and len(recent_history) > 2
    ):
        recent_history = recent_history[2:]
        history_text = [
            f"{'User' if message['role'] == 'user' else 'Assistant'}: "
            f"{message['content']}"
            for message in recent_history
        ]
        history = "\n".join(history_text)

    # A single unusually long turn must still respect the hard limit.
    if len(history) > MAX_HISTORY_CHARS:
        history = history[-MAX_HISTORY_CHARS:]

    return history


def store_conversation_turn(
    question,
    answer,
    history_messages=None,
):
    """
    Store one user/assistant turn in short-term memory.
    """

    messages = (
        conversation_history
        if history_messages is None
        else history_messages
    )
    messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    messages.append(
        {
            "role": "assistant",
            "content": answer,
        }
    )

    # Keep the newest complete user/assistant turns in memory.
    max_history_messages = MAX_HISTORY_TURNS * 2
    if len(messages) > max_history_messages:

        del messages[
            :-max_history_messages
        ]


def clear_conversation_history():
    """
    Clear the current conversation session.
    """

    conversation_history.clear()


# ============================================================
# QUERY UNDERSTANDING + QUERY REWRITING
# ============================================================

ROUTER_PROMPT = ChatPromptTemplate.from_template(
    """
You are the query understanding component of an internal
assistant for FinSolve Technologies.

You receive the recent conversation history and the user's
current question.

Your task is to:

1. Understand the current question.
2. Use conversation history when the current question refers
   to previous information.
3. Resolve pronouns and references such as:
   "it", "they", "their", "that", "this", "what about it",
   "what about Q3", etc.
4. Produce a standalone question that can be understood
   without the conversation history.
5. Produce a concise retrieval-friendly search query.
6. Classify the user's intent.

IMPORTANT:

- If the current question is already standalone, do not
  unnecessarily change its meaning.
- Do not add information that is not supported by the
  conversation.
- Treat conversation history only as context for resolving
    references and preserving the user's intent. It is not a
    source of verified company facts.
- Build company search queries from the current question and
    the minimum prior context needed to resolve its references.
    Company facts must come from retrieved documents.
- For time-based questions, include the resolved period and
    year when available, plus the relevant document category
    (for example, "Q3 2024 quarterly financial revenue").
- Prefer informative topic terms over generic company-name
    filler in the search query.
- Preserve the user's actual intent.
- Do not answer the question.
- For company-related questions, make the search query
  specific enough for document retrieval.
- For structured HR questions, preserve the employee/HR
  meaning in the standalone question and search query.
- For conversational questions, no company document search
  is required.

Return ONLY valid JSON:

{{
    "intent": "...",
    "standalone_question": "...",
    "search_query": "..."
}}

Possible intents:

conversation
company_information
engineering_information
marketing_information
finance_information
employee_count
salary_information
hr_information
unknown

Rules:

- conversation:
  greetings, casual conversation, "who are you",
  "how are you", "what can you do"

- employee_count:
  questions asking how many employees/people work here

- salary_information:
  questions asking about employee salary/pay

- hr_information:
  other employee/HR questions

- engineering_information:
  engineering responsibilities, SDLC, technical processes

- marketing_information:
  marketing activities, campaigns, marketing results

- finance_information:
  revenue, profit, financial performance, financial reports

- company_information:
  company identity, business, purpose, what the company does

- unknown:
  questions outside available company information


RECENT CONVERSATION HISTORY:
{history}


CURRENT USER QUESTION:
{question}
"""
)


# ============================================================
# ROUTER
# ============================================================

def understand_query(
    question,
    history,
):
    """
    Understand, rewrite, and route the current question
    using recent conversation history.
    """

    messages = ROUTER_PROMPT.format_messages(
        history=history,
        question=question,
    )

    response = llm.invoke(messages)

    text = response.content.strip()

    # Remove accidental markdown fences.
    text = re.sub(
        r"```json|```",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    try:

        data = json.loads(text)

        return {
            "intent": data.get(
                "intent",
                "unknown",
            ),
            "standalone_question": data.get(
                "standalone_question",
                question,
            ),
            "search_query": data.get(
                "search_query",
                question,
            ),
        }

    except Exception:

        # Safe fallback.
        return {
            "intent": "unknown",
            "standalone_question": question,
            "search_query": question,
        }


# ============================================================
# CONVERSATION RESPONSE
# ============================================================

def conversation_response(question):

    prompt = """
You are the internal assistant for FinSolve Technologies.

Respond naturally and briefly to the user's conversational
question.

Do not invent company facts.

Question:
{question}
"""

    response = llm.invoke(
        prompt.format(
            question=question
        )
    )

    return response.content.strip()


# ============================================================
# AUGMENTATION
# ============================================================

def augment_results(
    results,
    final_k=FINAL_CONTEXT_K,
):

    if not results:
        return []

    # --------------------------------------------------------
    # Step 1: Remove duplicate content
    # --------------------------------------------------------

    unique = []

    seen = set()

    for result in results:

        document = result["document"].strip()

        key = (
            result["metadata"].get(
                "source",
                "",
            ),
            document[:500],
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(result)

    # --------------------------------------------------------
    # Step 2: Source diversity
    # --------------------------------------------------------

    selected = []

    source_counts = {}

    # First pass:
    # Prefer different sources.
    for result in unique:

        source = result["metadata"].get(
            "source",
            "unknown",
        )

        count = source_counts.get(
            source,
            0,
        )

        if count == 0:

            selected.append(result)
            source_counts[source] = 1

            if len(selected) >= final_k:
                return selected

    # Second pass:
    # Fill remaining slots by retrieval rank.
    for result in unique:

        if result in selected:
            continue

        selected.append(result)

        if len(selected) >= final_k:
            break

    return selected


# ============================================================
# MAIN RAG PIPELINE
# ============================================================

def _access_denied_result(
    question,
    standalone_question,
    intent,
    role,
    history_messages=None,
):

    answer = (
        "You are not authorized to access that "
        "department's information."
    )

    store_conversation_turn(
        question=question,
        answer=answer,
        history_messages=history_messages,
    )

    return {
        "question": question,
        "standalone_question": standalone_question,
        "intent": intent,
        "search_query": "",
        "results": [],
        "answer": answer,
        "role": role,
        "access_denied": True,
    }


def answer_question(
    question,
    role="employee",
    history_messages=None,
):

    role = normalize_role(role)
    allowed_departments = get_allowed_departments(role)

    # --------------------------------------------------------
    # 1. Get recent conversation history
    # --------------------------------------------------------

    history = get_conversation_history(history_messages)

    # --------------------------------------------------------
    # 2. Understand + rewrite question
    # --------------------------------------------------------

    route = understand_query(
        question=question,
        history=history,
    )

    intent = route["intent"]

    standalone_question = route[
        "standalone_question"
    ]

    search_query = route[
        "search_query"
    ]

    required_department = required_department_for_intent(intent)

    if (
        required_department is not None
        and not can_access_department(role, required_department)
    ):

        return _access_denied_result(
            question=question,
            standalone_question=standalone_question,
            intent=intent,
            role=role,
            history_messages=history_messages,
        )

    # --------------------------------------------------------
    # 3. Conversation
    # --------------------------------------------------------

    if intent == "conversation":

        answer = conversation_response(
            standalone_question
        )

        store_conversation_turn(
            question=question,
            answer=answer,
            history_messages=history_messages,
        )

        return {
            "question": question,
            "standalone_question": standalone_question,
            "intent": intent,
            "search_query": "",
            "results": [],
            "answer": answer,
            "role": role,
            "access_denied": False,
        }

    # --------------------------------------------------------
    # 4. Structured HR
    # --------------------------------------------------------

    if intent in {
        "employee_count",
        "salary_information",
    }:

        if not can_access_hr_data(role):

            return _access_denied_result(
                question=question,
                standalone_question=standalone_question,
                intent=intent,
                role=role,
                history_messages=history_messages,
            )

        answer = _structured_hr_answer(
            intent
        )

        store_conversation_turn(
            question=question,
            answer=answer,
            history_messages=history_messages,
        )

        return {
            "question": question,
            "standalone_question": standalone_question,
            "intent": intent,
            "search_query": "",
            "results": [],
            "answer": answer,
            "role": role,
            "access_denied": False,
        }

    # --------------------------------------------------------
    # 5. Company RAG
    # --------------------------------------------------------

    results = retriever.retrieve(
        search_query,
        k=AUGMENTATION_K,
        departments=allowed_departments,
    )

    # --------------------------------------------------------
    # 6. Metadata-aware augmentation
    # --------------------------------------------------------

    if intent == "marketing_information":

        marketing_results = [
            result
            for result in results
            if result["metadata"].get(
                "department"
            ) == "marketing"
        ]

        if marketing_results:
            results = marketing_results

    elif intent == "engineering_information":

        engineering_results = [
            result
            for result in results
            if result["metadata"].get(
                "department"
            ) == "engineering"
        ]

        if engineering_results:
            results = engineering_results

    elif intent == "finance_information":

        finance_results = [
            result
            for result in results
            if result["metadata"].get(
                "department"
            ) == "finance"
        ]

        if finance_results:
            results = finance_results

    # --------------------------------------------------------
    # 7. Final augmentation
    # --------------------------------------------------------

    results = augment_results(
        results,
        final_k=FINAL_CONTEXT_K,
    )

    # --------------------------------------------------------
    # 8. Generate grounded answer
    # --------------------------------------------------------

    answer = generate_answer(
        llm=llm,
        prompt=generation_prompt,
        question=standalone_question,
        results=results,
    )

    # --------------------------------------------------------
    # 9. Store conversation turn
    # --------------------------------------------------------

    store_conversation_turn(
        question=question,
        answer=answer,
        history_messages=history_messages,
    )

    # --------------------------------------------------------
    # 10. Return complete pipeline result
    # --------------------------------------------------------

    return {
        "question": question,
        "standalone_question": standalone_question,
        "intent": intent,
        "search_query": search_query,
        "results": results,
        "answer": answer,
        "role": role,
        "access_denied": False,
    }


# ============================================================
# STRUCTURED HR
# ============================================================

def _structured_hr_answer(intent):

    import pandas as pd

    from config import PROJECT_ROOT

    hr_file = (
        PROJECT_ROOT
        / "data"
        / "hr"
        / "hr_data.csv"
    )

    df = pd.read_csv(hr_file)

    if intent == "employee_count":

        count = df["employee_id"].nunique()

        return (
            f"FinSolve Technologies has "
            f"{count} employees."
        )

    if intent == "salary_information":

        average_salary = df["salary"].mean()

        return (
            "The average employee salary is "
            f"{average_salary:,.2f}."
        )

    return (
        "The available company documents do not "
        "contain enough information to answer this."
    )


if __name__ == "__main__":
    from cli import main

    main(answer_question)
