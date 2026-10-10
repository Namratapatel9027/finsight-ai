import unittest
from unittest.mock import Mock, patch

from frontend_client import ApiRequestError, send_chat_request


class FrontendClientTests(unittest.TestCase):
    @patch("frontend_client.requests.post")
    def test_sends_bearer_token_session_and_question(self, post_request):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "answer": "Demo answer",
            "standalone_question": "Q3 revenue",
            "intent": "finance_information",
            "sources": ["quarterly_financial_report.md"],
        }
        post_request.return_value = response

        result = send_chat_request(
            "http://127.0.0.1:8000/",
            "finance-demo-token",
            "0fe0c4f0-d341-4c5b-86b3-6836491aadcf",
            "Q3 revenue",
        )

        post_request.assert_called_once_with(
            "http://127.0.0.1:8000/chat",
            headers={"Authorization": "Bearer finance-demo-token"},
            json={
                "session_id": "0fe0c4f0-d341-4c5b-86b3-6836491aadcf",
                "question": "Q3 revenue",
            },
            timeout=(5, 180),
        )
        self.assertEqual(result["answer"], "Demo answer")

    @patch("frontend_client.requests.post")
    def test_preserves_fastapi_authorization_denial(self, post_request):
        response = Mock()
        response.status_code = 403
        response.json.return_value = {"detail": "Not authorized."}
        post_request.return_value = response

        with self.assertRaises(ApiRequestError) as raised_error:
            send_chat_request(
                "http://127.0.0.1:8000",
                "employee-demo-token",
                "0fe0c4f0-d341-4c5b-86b3-6836491aadcf",
                "Q3 revenue",
            )

        self.assertEqual(raised_error.exception.status_code, 403)
        self.assertEqual(raised_error.exception.detail, "Not authorized.")


if __name__ == "__main__":
    unittest.main()