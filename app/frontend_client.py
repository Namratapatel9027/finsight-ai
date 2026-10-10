"""HTTP client helpers used by the Streamlit chat interface."""

import requests


class ApiRequestError(Exception):
    """A readable error returned by the FastAPI service."""

    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def send_chat_request(api_url, token, session_id, question):
    """Send one authenticated chat turn to FastAPI and return its JSON body."""

    response = requests.post(
        f"{api_url.rstrip('/')}/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "session_id": session_id,
            "question": question,
        },
        timeout=(5, 180),
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        detail = payload.get("detail", "The API request failed.")
        raise ApiRequestError(response.status_code, detail)

    return payload