"""Interactive terminal interface for the FinSolve RAG service."""

import os

from access_control import normalize_role

ACCESS_PROFILE_CHOICES = {
    "1": "employee",
    "2": "finance",
    "3": "marketing",
    "4": "hr",
    "5": "engineering",
    "6": "executive",
}


def choose_access_profile():
    configured_role = os.getenv("FINSOLVE_USER_ROLE")
    if configured_role:
        role = normalize_role(configured_role)
        print(f"Using configured demo profile: {role}")
        return role

    print("\nChoose your department/access profile:")
    print("1. General / Employee")
    print("2. Finance")
    print("3. Marketing")
    print("4. HR")
    print("5. Engineering")
    print("6. Executive / C-Level")

    while True:
        choice = input("Department (number or name): ").strip().lower()
        role = ACCESS_PROFILE_CHOICES.get(choice, choice)

        if role == "general":
            role = "employee"

        try:
            return normalize_role(role)
        except ValueError:
            print("Please choose one of the listed departments.")


def _print_result(result):
    print("\nAssistant:")
    print(result["answer"])
    print("\nStandalone question:")
    print(result["standalone_question"])

    if result["search_query"]:
        print("\nSearch query:")
        print(result["search_query"])

    if result["results"]:
        print("\nSources:")
        seen_sources = set()

        for item in result["results"]:
            source = item["metadata"].get("source", "unknown")
            if source not in seen_sources:
                print(f"- {source}")
                seen_sources.add(source)

    print()


def main(answer_question):
    print("\n" + "=" * 70)
    print("FinSolve RAG Assistant")
    print("=" * 70)

    role = choose_access_profile()
    print(f"Conversation started with profile: {role}")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("You: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Exiting...")
            break

        if not question:
            continue

        try:
            result = answer_question(question, role=role)
            _print_result(result)
        except Exception as error:
            print("\nERROR:")
            print(error)
            print()


if __name__ == "__main__":
    from rag import answer_question

    main(answer_question)