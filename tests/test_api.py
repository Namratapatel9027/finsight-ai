import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from access_control import can_access_department
import api
from conversation_store import ConversationStore


SESSION_ID = "8bd4b3e3-5e18-4a59-97cf-80298e09984e"


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.tokens = {
            "alice-demo-token": {"user_id": "alice", "role": "finance"},
            "bob-demo-token": {"user_id": "bob", "role": "employee"},
        }
        self.token_environment = patch.dict(
            os.environ,
            {"FINSOLVE_API_TOKENS": json.dumps(self.tokens)},
        )
        self.token_environment.start()
        self.addCleanup(self.token_environment.stop)
        self.sessions = ConversationStore()
        self.session_patch = patch.object(api, "_sessions", self.sessions)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.client = TestClient(api.app)

    def test_server_identity_controls_role_and_memory_is_isolated(self):
        observed_turns = []

        def fake_rag(question, role, history_messages):
            observed_turns.append((role, list(history_messages)))
            if (
                question == "Q3 revenue"
                and not can_access_department(role, "finance")
            ):
                return {
                    "answer": "Not authorized.",
                    "standalone_question": question,
                    "intent": "finance_information",
                    "results": [],
                    "access_denied": True,
                }

            history_messages.extend([
                {"role": "user", "content": question},
                {"role": "assistant", "content": "Demo answer"},
            ])
            return {
                "answer": "Demo answer",
                "standalone_question": question,
                "intent": "finance_information",
                "results": [],
                "access_denied": False,
            }

        with patch.object(api, "run_rag_question", side_effect=fake_rag):
            alice_headers = {"Authorization": "Bearer alice-demo-token"}
            bob_headers = {"Authorization": "Bearer bob-demo-token"}

            first = self.client.post(
                "/chat",
                headers=alice_headers,
                json={"session_id": SESSION_ID, "question": "Q3 revenue"},
            )
            second = self.client.post(
                "/chat",
                headers=alice_headers,
                json={
                    "session_id": SESSION_ID,
                    "question": "Follow up",
                    "role": "executive",
                },
            )
            bob = self.client.post(
                "/chat",
                headers=bob_headers,
                json={"session_id": SESSION_ID, "question": "Separate user"},
            )
            bob_finance = self.client.post(
                "/chat",
                headers=bob_headers,
                json={"session_id": SESSION_ID, "question": "Q3 revenue"},
            )

        self.assertEqual(
            [first.status_code, second.status_code, bob.status_code, bob_finance.status_code],
            [200, 200, 200, 403],
        )
        self.assertEqual(observed_turns[0][0], "finance")
        self.assertEqual(observed_turns[1][0], "finance")
        self.assertEqual(len(observed_turns[1][1]), 2)
        self.assertEqual(observed_turns[2][0], "employee")
        self.assertEqual(observed_turns[2][1], [])
        self.assertEqual(observed_turns[3][0], "employee")
        self.assertEqual(bob_finance.json()["detail"], "Not authorized.")

    def test_missing_or_invalid_credentials_do_not_call_rag(self):
        with patch.object(api, "run_rag_question") as rag_call:
            missing = self.client.post(
                "/chat",
                json={"session_id": SESSION_ID, "question": "Q3 revenue"},
            )
            invalid = self.client.post(
                "/chat",
                headers={"Authorization": "Bearer not-a-token"},
                json={"session_id": SESSION_ID, "question": "Q3 revenue"},
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        rag_call.assert_not_called()

    def test_rag_access_denial_becomes_http_403(self):
        with patch.object(
            api,
            "run_rag_question",
            return_value={"access_denied": True, "answer": "Not authorized."},
        ) as rag_call:
            response = self.client.post(
                "/chat",
                headers={"Authorization": "Bearer bob-demo-token"},
                json={"session_id": SESSION_ID, "question": "Q3 revenue"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Not authorized.")
        self.assertEqual(rag_call.call_args.kwargs["role"], "employee")

    def test_health_does_not_require_rag_or_authentication(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
