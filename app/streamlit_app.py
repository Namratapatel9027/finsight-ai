"""Streamlit user interface for the FinSolve FastAPI RAG service."""

import os
import random
import re
import time
from datetime import datetime
from uuid import uuid4

import requests
import streamlit as st
from dotenv import load_dotenv

from config import ENV_FILE
from frontend_client import ApiRequestError, send_chat_request


# ---------------- Department-Specific Recommended Prompts ----------------
DEPARTMENT_PROMPTS = {
    "finance": [
        "What was the company revenue in Q3 2024?",
        "Can you summarize our Q4 financial performance?",
        "What were the major operating expenses in 2024?",
        "What does the financial report say about cash flow?",
        "What are the major financial risks highlighted for 2024?",
    ],
    "technology": [
        "What is FinSolve's software development lifecycle (SDLC)?",
        "What are the engineering team's core responsibilities?",
        "What are our security and data protection standards?",
        "What is our deployment and continuous integration policy?",
        "What are the technical architecture best practices?",
    ],
    "marketing": [
        "What were our key marketing achievements in Q4 2024?",
        "What was the marketing campaign ROI in Q1 2024?",
        "What were the marketing targets versus actuals in Q3?",
        "Summarize the marketing strategy for the upcoming quarters.",
        "What are our primary customer acquisition channels?",
    ],
    "hr": [
        "How many employees work at FinSolve Technologies?",
        "What is the average employee salary across departments?",
        "What is the employee referral reward policy?",
        "How do employees apply for annual and sick leave?",
        "What are the company code of conduct and ethics guidelines?",
    ],
    "general": [
        "What is FinSolve Technologies' company vision and mission?",
        "What are the standard working hours and remote work policies?",
        "How does the employee performance review process work?",
        "What healthcare and wellness benefits are provided?",
        "What is the company policy on intellectual property?",
    ],
}


def _get_department_recommendations(department: str) -> list[str]:
    dept_lower = department.lower()
    if "finan" in dept_lower:
        base = DEPARTMENT_PROMPTS["finance"]
    elif "tech" in dept_lower or "engineer" in dept_lower:
        base = DEPARTMENT_PROMPTS["technology"]
    elif "market" in dept_lower:
        base = DEPARTMENT_PROMPTS["marketing"]
    elif "hr" in dept_lower:
        base = DEPARTMENT_PROMPTS["hr"]
    else:
        base = DEPARTMENT_PROMPTS["general"]

    sample_size = min(3, len(base))
    return random.sample(base, sample_size)


def _get_rbac_scope(department: str) -> str:
    dept_lower = department.lower()
    if "finan" in dept_lower:
        return "Finance, General"
    elif "tech" in dept_lower or "engineer" in dept_lower:
        return "Engineering, General"
    elif "market" in dept_lower:
        return "Marketing, General"
    elif "hr" in dept_lower:
        return "HR, General, HR Data"
    elif "exec" in dept_lower or "c-level" in dept_lower:
        return "All Departments (Executive)"
    return "General Handbook"


def _suggest_smart_topic(question: str) -> str:
    q = question.lower()
    if "revenue" in q:
        return "Revenue of 2024"
    elif "salary" in q or "wage" in q:
        return "Employees Salary Details"
    elif "employee" in q and ("count" in q or "many" in q):
        return "Total Headcount & Workforce"
    elif "sdlc" in q or "software development" in q:
        return "SDLC & Engineering Guidelines"
    elif "leave" in q or "vacation" in q:
        return "Company Leave Policy"
    elif "referral" in q:
        return "Employee Referral Program"
    elif "marketing" in q or "campaign" in q:
        return "Marketing Performance 2024"
    elif "vision" in q or "mission" in q:
        return "FinSolve Vision & Values"
    elif "expense" in q or "cost" in q:
        return "Financial Operating Expenses"
    else:
        clean = re.sub(r"[^\w\s]", "", question).strip().title()
        words = clean.split()
        return " ".join(words[:4]) if words else "Research Note"


def _init_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_profile" not in st.session_state:
        st.session_state.user_profile = {}
    if "api_token" not in st.session_state:
        st.session_state.api_token = ""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid4())
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}
    if "current_chat_title" not in st.session_state:
        st.session_state.current_chat_title = "New Topic"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "renaming_session_id" not in st.session_state:
        st.session_state.renaming_session_id = None

    if "selected_view" not in st.session_state:
        st.session_state.selected_view = "💬 Knowledge Chatbot"

    if "active_note_id" not in st.session_state:
        st.session_state.active_note_id = str(uuid4())
    if "notes_dict" not in st.session_state:
        st.session_state.notes_dict = {}

    # Real-Time Advanced Analytics States
    if "last_query_latency" not in st.session_state:
        st.session_state.last_query_latency = 0.0
    if "last_sources" not in st.session_state:
        st.session_state.last_sources = []
    if "all_sources_used" not in st.session_state:
        st.session_state.all_sources_used = set()
    if "all_intents_detected" not in st.session_state:
        st.session_state.all_intents_detected = set()
    if "blocked_requests_count" not in st.session_state:
        st.session_state.blocked_requests_count = 0

    if "recommended_prompts" not in st.session_state:
        st.session_state.recommended_prompts = []
    if "prefill_question" not in st.session_state:
        st.session_state.prefill_question = ""


def _save_current_chat(custom_title: str | None = None):
    sid = st.session_state.session_id
    title = (custom_title or st.session_state.current_chat_title or "Saved Chat").strip()
    st.session_state.current_chat_title = title
    st.session_state.chat_sessions[sid] = {
        "title": title,
        "messages": list(st.session_state.messages),
        "updated_at": datetime.now().strftime("%d %b, %H:%M"),
    }


def _create_new_chat():
    if st.session_state.messages:
        _save_current_chat()

    new_sid = str(uuid4())
    st.session_state.session_id = new_sid
    st.session_state.messages = []
    st.session_state.current_chat_title = f"Topic {len(st.session_state.chat_sessions) + 1}"
    st.session_state.renaming_session_id = None
    st.session_state.selected_view = "💬 Knowledge Chatbot"
    st.session_state.last_sources = []

    new_nid = str(uuid4())
    st.session_state.active_note_id = new_nid

    dept = st.session_state.user_profile.get("department", "General")
    st.session_state.recommended_prompts = _get_department_recommendations(dept)


def _switch_to_chat(target_sid: str):
    if st.session_state.messages:
        _save_current_chat()

    saved_data = st.session_state.chat_sessions.get(target_sid)
    if saved_data:
        st.session_state.session_id = target_sid
        st.session_state.messages = list(saved_data["messages"])
        st.session_state.current_chat_title = saved_data["title"]
        st.session_state.renaming_session_id = None
        st.session_state.selected_view = "💬 Knowledge Chatbot"


def _create_new_note():
    new_nid = str(uuid4())
    st.session_state.active_note_id = new_nid
    st.session_state.selected_view = "📝 Scratchpad & Notes"


def _switch_to_note(target_nid: str):
    if target_nid in st.session_state.notes_dict:
        st.session_state.active_note_id = target_nid
        st.session_state.selected_view = "📝 Scratchpad & Notes"


def _check_api_health(api_url: str) -> bool:
    try:
        res = requests.get(f"{api_url}/health", timeout=2)
        return res.status_code == 200
    except requests.RequestException:
        return False


def _login_user(api_url: str, email: str, password: str):
    clean_email = email.strip().lower()

    if not clean_email.endswith("@fintechco.com"):
        st.error("⚠️ Invalid domain: Please enter your company email ending with @fintechco.com")
        return

    try:
        response = requests.post(
            f"{api_url}/auth/login",
            json={"email": clean_email, "password": password},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.authenticated = True
            st.session_state.api_token = data["access_token"]
            st.session_state.user_profile = {
                "name": data["name"],
                "role": data["role"],
                "department": data["department"],
                "email": data["email"],
            }
            st.session_state.recommended_prompts = _get_department_recommendations(data["department"])
            _create_new_chat()
            st.success("Authentication successful! Redirecting...")
            st.rerun()
        elif response.status_code in (400, 401):
            detail_msg = response.json().get("detail", "Authentication failed.")
            st.error(f"❌ {detail_msg}")
        else:
            st.error(f"❌ Authentication error (Status: {response.status_code})")
    except requests.ConnectionError:
        st.error("❌ Cannot reach FastAPI backend. Make sure the API server is running on port 8000.")
    except Exception as e:
        st.error(f"❌ An unexpected error occurred: {e}")


def _render_login_view(api_url: str):
    st.markdown("<h2 style='text-align: center; margin-bottom: 0px;'>🔐 FinSolve Enterprise Portal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sign in with your company credentials to access internal documents.</p>", unsafe_allow_html=True)
    st.write("---")

    if not _check_api_health(api_url):
        st.warning("⚠️ **Backend Offline**: FastAPI server is not responding at `127.0.0.1:8000`. Please start Terminal 1 before logging in.")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form", clear_on_submit=False):
            email_input = st.text_input("Company Email", placeholder="your.name@fintechco.com")
            pwd_input = st.text_input("Password", type="password", placeholder="Enter your password")
            submit_btn = st.form_submit_button("Sign In", use_container_width=True)

            if submit_btn:
                if not email_input or not pwd_input:
                    st.warning("Please enter both email address and password.")
                else:
                    _login_user(api_url, email_input, pwd_input)

        st.caption("🔒 Secured with FinSolve RBAC authentication.")


def main():
    load_dotenv(ENV_FILE)
    st.set_page_config(
        page_title="FinSolve Knowledge Assistant",
        page_icon="🏢",
        layout="wide",
    )

    _init_session()
    api_url = os.getenv("FINSOLVE_API_URL", "http://127.0.0.1:8000").rstrip("/")

    if not st.session_state.authenticated:
        _render_login_view(api_url)
        return

    # ---------------- HEADER PROFILE BADGE ----------------
    profile = st.session_state.user_profile
    header_col1, header_col2 = st.columns([4, 1])

    with header_col1:
        st.markdown(
            f"### 👤 Welcome, **{profile.get('name', 'Employee')}**!  \n"
            f"🏢 Department: **{profile.get('department', 'General')}** &nbsp;|&nbsp; "
            f"💼 Role: **{profile.get('role', 'Member')}**"
        )
        st.caption(f"Authenticated Account: `{profile.get('email', '')}`")

    with header_col2:
        if st.button("🚪 Sign Out", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_profile = {}
            st.session_state.api_token = ""
            st.session_state.chat_sessions = {}
            st.session_state.notes_dict = {}
            st.session_state.messages = []
            st.session_state.all_sources_used = set()
            st.session_state.all_intents_detected = set()
            st.rerun()

    st.write("---")

    # ---------------- SIDEBAR: CHAT, NOTES & REAL-TIME ANALYTICS ----------------
    with st.sidebar:
        if st.button("➕ New Chat", use_container_width=True, type="primary"):
            _create_new_chat()
            st.rerun()

        st.write("---")
        st.subheader("💬 Chat History")

        if st.session_state.chat_sessions:
            for sid, sdata in list(st.session_state.chat_sessions.items()):
                is_active = (sid == st.session_state.session_id)
                col_btn, col_edit = st.columns([4, 1])

                with col_btn:
                    icon = "🟢 " if is_active else "📄 "
                    if st.button(f"{icon}{sdata['title']}", key=f"select_{sid}", use_container_width=True):
                        _switch_to_chat(sid)
                        st.rerun()

                with col_edit:
                    if st.button("✏️", key=f"edit_trigger_{sid}", help="Rename chat"):
                        st.session_state.renaming_session_id = sid
                        st.rerun()

                if st.session_state.renaming_session_id == sid:
                    with st.container():
                        new_name = st.text_input("New Name", value=sdata["title"], key=f"rename_input_{sid}")
                        r_col1, r_col2 = st.columns(2)
                        with r_col1:
                            if st.button("✔️ Save", key=f"save_name_{sid}", use_container_width=True):
                                if new_name.strip():
                                    st.session_state.chat_sessions[sid]["title"] = new_name.strip()
                                    if is_active:
                                        st.session_state.current_chat_title = new_name.strip()
                                st.session_state.renaming_session_id = None
                                st.rerun()
                        with r_col2:
                            if st.button("❌", key=f"cancel_name_{sid}", use_container_width=True):
                                st.session_state.renaming_session_id = None
                                st.rerun()

                st.caption(f"Updated: {sdata.get('updated_at', '')}")
        else:
            st.caption("No saved chats yet.")

        st.write("---")
        # Clickable Notes History
        col_note_head, col_note_add = st.columns([3, 1])
        with col_note_head:
            st.subheader("📑 Saved Notes")
        with col_note_add:
            if st.button("➕", help="Create fresh blank note", key="add_new_note_btn"):
                _create_new_note()
                st.rerun()

        if st.session_state.notes_dict:
            for nid, ndata in list(st.session_state.notes_dict.items()):
                is_active_note = (nid == st.session_state.active_note_id)
                n_icon = "📌 " if is_active_note else "📝 "
                if st.button(f"{n_icon}{ndata['title']}", key=f"note_btn_{nid}", use_container_width=True):
                    _switch_to_note(nid)
                    st.rerun()
                st.caption(f"Last modified: {ndata.get('updated_at', '')}")
        else:
            st.caption("Auto-saved notes will appear here.")

        st.write("---")
        # ---------------- REAL-TIME SYSTEM & SECURITY ANALYTICS ----------------
        st.subheader("📊 Session & Security Analytics")

        # 1. RBAC Scope
        rbac_scope = _get_rbac_scope(profile.get("department", "General"))
        st.markdown(f"**🛡️ Permitted Scope:**  \n`{rbac_scope}`")

        # 2. Query Latency
        lat_text = f"{st.session_state.last_query_latency:.2f}s" if st.session_state.last_query_latency > 0 else "N/A"
        st.markdown(f"**⏱️ Last Query Time:** `{lat_text}`")

        # 3. Blocked / Denied Requests
        st.markdown(f"**🔒 Blocked Requests:** `{st.session_state.blocked_requests_count}`")

        # 4. Detected Intents (All unique detected in this session)
        st.markdown("**🎯 Detected Intent(s):**")
        if st.session_state.all_intents_detected:
            for it in sorted(st.session_state.all_intents_detected):
                st.caption(f"• `{it}`")
        else:
            st.caption("*None detected yet*")

        # 5. All Sources Used (Cumulative list)
        st.markdown("**📁 Sources Used (All):**")
        if st.session_state.all_sources_used:
            for src in sorted(st.session_state.all_sources_used):
                st.caption(f"• `{src}`")
        else:
            st.caption("*No sources queried yet*")

    # ---------------- VIEW SWITCHER ----------------
    view_options = ["💬 Knowledge Chatbot", "📝 Scratchpad & Notes"]
    current_index = 1 if st.session_state.selected_view == "📝 Scratchpad & Notes" else 0
    selected_tab = st.radio(
        "Navigation",
        options=view_options,
        index=current_index,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.selected_view = selected_tab

    # ---------------- TAB 1: KNOWLEDGE CHATBOT ----------------
    if st.session_state.selected_view == "💬 Knowledge Chatbot":
        st.markdown(f"#### 🗨️ Active Topic: *{st.session_state.current_chat_title}*")

        # Starter recommendation chips
        if not st.session_state.messages:
            st.info("💡 **Recommended for your department:** Click any starter prompt below or type your question:")
            chip_cols = st.columns(len(st.session_state.recommended_prompts))
            for i, prompt in enumerate(st.session_state.recommended_prompts):
                with chip_cols[i]:
                    if st.button(f"📌 {prompt}", key=f"chip_{i}", use_container_width=True):
                        st.session_state.prefill_question = prompt
                        st.rerun()

        # Render messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        typed_question = st.chat_input("Ask a question about your department or company policies...", max_chars=2000)
        active_question = None

        if st.session_state.prefill_question:
            active_question = st.session_state.prefill_question
            st.session_state.prefill_question = ""
        elif typed_question:
            active_question = typed_question

        if active_question:
            # Smart topic generation for new conversations
            if not st.session_state.messages or st.session_state.current_chat_title.startswith("New Topic") or st.session_state.current_chat_title.startswith("Topic "):
                smart_title = _suggest_smart_topic(active_question)
                st.session_state.current_chat_title = smart_title

                curr_nid = st.session_state.active_note_id
                if curr_nid not in st.session_state.notes_dict:
                    st.session_state.notes_dict[curr_nid] = {
                        "title": smart_title,
                        "content": f"# Notes: {smart_title}\n\n",
                        "updated_at": datetime.now().strftime("%H:%M:%S"),
                    }

            st.session_state.messages.append({"role": "user", "content": active_question})
            with st.chat_message("user"):
                st.markdown(active_question)

            # Start Latency Timer
            start_time = time.time()
            try:
                with st.spinner("Searching company documents..."):
                    result = send_chat_request(
                        api_url=api_url,
                        token=st.session_state.api_token,
                        session_id=st.session_state.session_id,
                        question=active_question,
                    )
                st.session_state.last_query_latency = time.time() - start_time

                # Update Analytics with Sources & Intent
                sources_list = result.get("sources", [])
                st.session_state.last_sources = sources_list
                for s in sources_list:
                    st.session_state.all_sources_used.add(s)

                intent_found = result.get("intent", "")
                if intent_found:
                    st.session_state.all_intents_detected.add(intent_found)

                assistant_message = {
                    "role": "assistant",
                    "content": result["answer"],
                }
            except ApiRequestError as error:
                st.session_state.last_query_latency = time.time() - start_time
                if error.status_code == 401:
                    detail = "Session expired or unauthorized token. Please sign in again."
                elif error.status_code == 403:
                    st.session_state.blocked_requests_count += 1
                    detail = f"🔒 Access Denied: {error.detail}"
                else:
                    detail = f"FastAPI returned HTTP {error.status_code}: {error.detail}"
                assistant_message = {"role": "assistant", "content": detail}
            except requests.ConnectionError:
                st.session_state.last_query_latency = time.time() - start_time
                assistant_message = {
                    "role": "assistant",
                    "content": "Cannot reach FastAPI backend. Make sure the server is running on port 8000.",
                }
            except Exception as e:
                st.session_state.last_query_latency = time.time() - start_time
                assistant_message = {
                    "role": "assistant",
                    "content": f"An error occurred: {e}",
                }

            st.session_state.messages.append(assistant_message)
            _save_current_chat()
            st.rerun()

    # ---------------- TAB 2: SCRATCHPAD & NOTES ----------------
    else:
        active_nid = st.session_state.active_note_id
        active_note = st.session_state.notes_dict.get(active_nid, {
            "title": st.session_state.current_chat_title or "Untitled Note",
            "content": "",
            "updated_at": datetime.now().strftime("%H:%M:%S"),
        })

        st.subheader(f"📝 Scratchpad: *{active_note['title']}*")

        c_title_col, c_btn_col = st.columns([3, 1])
        with c_title_col:
            edit_note_title = st.text_input("Note Title", value=active_note["title"], key=f"note_title_input_{active_nid}")
        with c_btn_col:
            if st.button("💾 Save Chat & Note", use_container_width=True, type="primary"):
                _save_current_chat(custom_title=edit_note_title)
                st.session_state.notes_dict[active_nid]["title"] = edit_note_title.strip()
                st.success("Chat & Note saved!")
                st.rerun()

        st.caption("Jo bhi likhoge woh bina kisi button ke apne-aap is note me auto-save hoga.")

        editor_key = f"note_text_area_{active_nid}"
        if editor_key not in st.session_state:
            st.session_state[editor_key] = active_note["content"]

        def _on_active_note_edit():
            content_val = st.session_state[editor_key]
            current_title = edit_note_title.strip() or active_note["title"]
            st.session_state.notes_dict[active_nid] = {
                "title": current_title,
                "content": content_val,
                "updated_at": datetime.now().strftime("%H:%M:%S"),
            }

        st.text_area(
            "Note Content",
            value=st.session_state[editor_key],
            height=260,
            placeholder="Type your notes here... Even a single character is auto-saved in this specific note.",
            key=editor_key,
            on_change=_on_active_note_edit,
            label_visibility="collapsed",
        )

        current_content = st.session_state[editor_key]

        st.download_button(
            label=f"📥 Download '{active_note['title']}' (.txt)",
            data=current_content if current_content.strip() else "Empty note.",
            file_name=f"{active_note['title'].lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
            disabled=not bool(current_content.strip()),
        )


if __name__ == "__main__":
    main()



#isha.chowdhury@fintechco.com
#Finance@123