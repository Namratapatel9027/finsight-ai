// Configuration
// In the recommended setup FastAPI serves this page, so the website and API
// share an origin. A separate local static server can still talk to port 8000.
const API_URL = window.FINSOLVE_API_URL || (
  window.location.port === "8000"
    ? window.location.origin
    : `${window.location.protocol}//${window.location.hostname}:8000`
);

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("finsolve_user") || "null");
  } catch {
    localStorage.removeItem("finsolve_user");
    return null;
  }
}

function createSessionId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const random = Math.floor(Math.random() * 16);
    return (char === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

// Department Recommended Starter Prompts
const DEPARTMENT_PROMPTS = {
  finance: [
    "What was the company revenue in Q3 2024?",
    "Can you summarize our Q4 financial performance?",
    "What were the major operating expenses in 2024?",
    "What does the financial report say about cash flow?",
    "What are the major financial risks highlighted for 2024?",
  ],
  technology: [
    "What is FinSolve's software development lifecycle (SDLC)?",
    "What are the engineering team's core responsibilities?",
    "What are our security and data protection standards?",
    "What is our deployment and continuous integration policy?",
    "What are the technical architecture best practices?",
  ],
  marketing: [
    "What were our key marketing achievements in Q4 2024?",
    "What was the marketing campaign ROI in Q1 2024?",
    "What were the marketing targets versus actuals in Q3?",
    "Summarize the marketing strategy for the upcoming quarters.",
    "What are our primary customer acquisition channels?",
  ],
  hr: [
    "How many employees work at FinSolve Technologies?",
    "What is the average employee salary across departments?",
    "What is the employee referral reward policy?",
    "How do employees apply for annual and sick leave?",
    "What are the company code of conduct and ethics guidelines?",
  ],
  general: [
    "What is FinSolve Technologies' company vision and mission?",
    "What are the standard working hours and remote work policies?",
    "How does the employee performance review process work?",
    "What healthcare and wellness benefits are provided?",
    "What is the company policy on intellectual property?",
  ],
};

// Application State
const state = {
  token: (() => { try { return localStorage.getItem("finsolve_token"); } catch { return null; } })(),
  user: readStoredUser(),
  sessionId: createSessionId(),
  currentChatTitle: "New Topic",
  messages: [],
  chatSessions: {},
  activeNoteId: createSessionId(),
  notes: {},
  analytics: {
    lastLatency: 0,
    blockedCount: 0,
    intents: new Set(),
    sources: new Set(),
  },
  currentView: "chat",
};

// DOM Nodes
const authView = document.getElementById("authView");
const appView = document.getElementById("appView");
const landingShell = document.querySelector(".landing-shell");
if (landingShell && window.matchMedia("(pointer: fine)").matches) {
  landingShell.addEventListener("pointermove", (event) => {
    const bounds = landingShell.getBoundingClientRect();
    landingShell.style.setProperty("--pointer-x", `${event.clientX - bounds.left}px`);
    landingShell.style.setProperty("--pointer-y", `${event.clientY - bounds.top}px`);
  });
}
const loginForm = document.getElementById("loginForm");
const authAlert = document.getElementById("authAlert");

const userDept = document.getElementById("userDept");
const userRole = document.getElementById("userRole");
const userEmail = document.getElementById("userEmail");
const heroUserName = document.getElementById("heroUserName");
const signOutBtn = document.getElementById("signOutBtn");

const chatHistoryList = document.getElementById("chatHistoryList");
const notesHistoryList = document.getElementById("notesHistoryList");
const newChatBtn = document.getElementById("newChatBtn");
const newNoteBtn = document.getElementById("newNoteBtn");

const rbacScopeText = document.getElementById("rbacScopeText");
const lastLatencyText = document.getElementById("lastLatencyText");
const blockedCountText = document.getElementById("blockedCountText");
const intentsList = document.getElementById("intentsList");
const sourcesList = document.getElementById("sourcesList");

const tabChat = document.getElementById("tabChat");
const tabNotes = document.getElementById("tabNotes");
const navAnalytics = document.getElementById("navAnalytics");
const chatSection = document.getElementById("chatSection");
const notesSection = document.getElementById("notesSection");
const workspaceHero = document.getElementById("workspaceHero");
const analyticsSection = document.getElementById("analyticsSection");

const activeTopicLabel = document.getElementById("activeTopicLabel");
const recChipsList = document.getElementById("recChipsList");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");

const noteTitleInput = document.getElementById("noteTitleInput");
const noteTextArea = document.getElementById("noteTextArea");
const saveNoteBtn = document.getElementById("saveNoteBtn");
const downloadNoteBtn = document.getElementById("downloadNoteBtn");

// Helper Functions
function getRbacScope(dept = "General") {
  const d = dept.toLowerCase();
  if (d.includes("finan")) return "Finance, General";
  if (d.includes("tech") || d.includes("engineer")) return "Engineering, General";
  if (d.includes("market")) return "Marketing, General";
  if (d.includes("hr")) return "HR, General, HR Data";
  if (d.includes("exec") || d.includes("c-level")) return "All Departments (Executive)";
  return "General Handbook";
}

function getRecommendations(dept = "General") {
  const d = dept.toLowerCase();
  let base = DEPARTMENT_PROMPTS.general;
  if (d.includes("finan")) base = DEPARTMENT_PROMPTS.finance;
  else if (d.includes("tech") || d.includes("engineer")) base = DEPARTMENT_PROMPTS.technology;
  else if (d.includes("market")) base = DEPARTMENT_PROMPTS.marketing;
  else if (d.includes("hr")) base = DEPARTMENT_PROMPTS.hr;
  return [...base].sort(() => 0.5 - Math.random()).slice(0, 3);
}

function suggestSmartTopic(q) {
  const cleanQ = q.toLowerCase();
  if (cleanQ.includes("revenue")) return "Revenue of 2024";
  if (cleanQ.includes("salary") || cleanQ.includes("wage")) return "Employees Salary Details";
  if (cleanQ.includes("employee") && (cleanQ.includes("count") || cleanQ.includes("many"))) return "Total Headcount & Workforce";
  if (cleanQ.includes("sdlc") || cleanQ.includes("software development")) return "SDLC & Engineering Guidelines";
  if (cleanQ.includes("leave") || cleanQ.includes("vacation")) return "Company Leave Policy";
  if (cleanQ.includes("referral")) return "Employee Referral Program";
  if (cleanQ.includes("marketing") || cleanQ.includes("campaign")) return "Marketing Performance 2024";
  if (cleanQ.includes("vision") || cleanQ.includes("mission")) return "FinSolve Vision & Values";
  if (cleanQ.includes("expense") || cleanQ.includes("cost")) return "Financial Operating Expenses";
  const words = cleanQ.replace(/[^\w\s]/g, "").trim().split(/\s+/);
  return words.slice(0, 4).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ") || "Research Note";
}

// Authentication
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const loginButton = document.getElementById("loginBtn");
  const loginButtonText = loginButton.querySelector("span");
  const email = document.getElementById("emailInput").value.trim().toLowerCase();
  const password = document.getElementById("passwordInput").value;

  if (!email.endsWith("@fintechco.com")) {
    showAlert("⚠️ Invalid domain: Please enter your company email ending with @fintechco.com", "error");
    return;
  }

  loginButton.disabled = true;
  loginButtonText.textContent = "Signing in…";
  try {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json();
    if (res.ok) {
      state.token = data.access_token;
      state.user = {
        name: data.name,
        role: data.role,
        department: data.department,
        email: data.email,
      };
      try {
        localStorage.setItem("finsolve_token", state.token);
        localStorage.setItem("finsolve_user", JSON.stringify(state.user));
      } catch (storageError) {
        console.warn("Could not persist the sign-in session in this browser.", storageError);
      }
      initAppSession();
    } else {
      showAlert(`❌ ${data.detail || "Authentication failed."}`, "error");
    }
  } catch (error) {
    console.error("Login failed:", error);
    showAlert("❌ Cannot reach the API. Start the app with: uvicorn api:app --app-dir app --reload", "error");
  } finally {
    loginButton.disabled = false;
    loginButtonText.textContent = "Enter workspace";
  }
});

function showAlert(msg, type) {
  authAlert.textContent = msg;
  authAlert.className = `alert-box alert-${type}`;
  authAlert.classList.remove("hidden");
}

function returnToLoginForExpiredSession() {
  state.token = null;
  try {
    localStorage.removeItem("finsolve_token");
    localStorage.removeItem("finsolve_user");
  } catch (storageError) {
    console.warn("Could not clear the expired browser session.", storageError);
  }
  authView.classList.remove("hidden");
  appView.classList.add("hidden");
  showAlert("Your session expired because the API restarted. Please sign in again.", "error");
}

signOutBtn.addEventListener("click", () => {
  localStorage.removeItem("finsolve_token");
  localStorage.removeItem("finsolve_user");
  location.reload();
});

// App Session Management
function initAppSession() {
  authView.classList.add("hidden");
  appView.classList.remove("hidden");

  const employeeName = state.user.name?.trim() || state.user.full_name?.trim() ||
    state.user.email?.split("@")[0].replace(/[._-]+/g, " ").replace(/\b\p{L}/gu, (letter) => letter.toUpperCase()) ||
    "Employee";
  heroUserName.textContent = employeeName;
  userDept.textContent = state.user.department || "General";
  userRole.textContent = state.user.role || "Member";
  userEmail.textContent = state.user.email || "";

  rbacScopeText.textContent = getRbacScope(state.user.department);
  renderChips();
  renderHistory();
  renderNotesHistory();
}

function renderChips() {
  const chips = getRecommendations(state.user.department);
  recChipsList.innerHTML = "";
  chips.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = "chip-btn";
    btn.textContent = `📌 ${c}`;
    btn.onclick = () => {
      chatInput.value = c;
      chatForm.dispatchEvent(new Event("submit"));
    };
    recChipsList.appendChild(btn);
  });
}

// Chat Workflows
function saveCurrentChat() {
  persistActiveNote();
  const title = (state.currentChatTitle || "Saved Chat").trim();
  state.chatSessions[state.sessionId] = {
    title,
    messages: [...state.messages],
    noteId: state.activeNoteId,
    updated_at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  };
  renderHistory();
}

function loadActiveNote(noteId) {
  state.activeNoteId = noteId || createSessionId();
  const note = state.notes[state.activeNoteId] || {
    title: "Untitled Note",
    content: "",
  };
  noteTitleInput.value = note.title;
  noteTextArea.value = note.content;
  downloadNoteBtn.disabled = !note.content.trim();
  renderNotesHistory();
}

function persistActiveNote() {
  const existing = state.notes[state.activeNoteId];
  const title = noteTitleInput.value.trim();
  const content = noteTextArea.value;
  if (!existing && (!title || title === "Untitled Note") && !content.trim()) return;

  const savedNote = existing || {
    title: "Untitled Note",
    content: "",
  };
  state.notes[state.activeNoteId] = {
    ...savedNote,
    title: title || savedNote.title || "Untitled Note",
    content,
    updated_at: new Date().toLocaleTimeString(),
  };
  downloadNoteBtn.disabled = !content.trim();
  renderNotesHistory();
}

newChatBtn.addEventListener("click", () => {
  persistActiveNote();
  if (state.messages.length) saveCurrentChat();
  state.sessionId = createSessionId();
  state.messages = [];
  state.currentChatTitle = `Topic ${Object.keys(state.chatSessions).length + 1}`;
  activeTopicLabel.textContent = state.currentChatTitle;
  chatMessages.innerHTML = "";
  document.getElementById("recommendationContainer").classList.remove("hidden");
  loadActiveNote(createSessionId());
  saveCurrentChat();
  switchView("chat");
  renderChips();
});

function renderHistory() {
  chatHistoryList.innerHTML = "";
  Object.entries(state.chatSessions).reverse().forEach(([sid, sdata]) => {
    const item = document.createElement("div");
    item.className = `history-item ${sid === state.sessionId ? "active" : ""}`;
    const title = document.createElement("span");
    title.className = "item-title";
    title.textContent = `${sid === state.sessionId ? "🟢" : "📄"} ${sdata.title}`;
    const renameButton = document.createElement("button");
    renameButton.className = "rename-btn";
    renameButton.type = "button";
    renameButton.title = "Rename chat";
    renameButton.textContent = "✏️";
    item.append(title, renameButton);

    title.onclick = () => {
      persistActiveNote();
      if (state.messages.length) saveCurrentChat();
      const selectedChat = state.chatSessions[sid] || sdata;
      state.sessionId = sid;
      state.messages = [...selectedChat.messages];
      state.currentChatTitle = selectedChat.title;
      loadActiveNote(selectedChat.noteId);
      activeTopicLabel.textContent = selectedChat.title;
      renderChatMessages();
      switchView("chat");
      chatSection.scrollIntoView({ behavior: "smooth", block: "start" });
      renderHistory();
    };
    renameButton.onclick = (e) => {
      e.stopPropagation();
      const newTitle = prompt("Enter new title:", sdata.title);
      if (newTitle && newTitle.trim()) {
        sdata.title = newTitle.trim();
        state.chatSessions[sid].title = sdata.title;
        if (sid === state.sessionId) {
          state.currentChatTitle = sdata.title;
          activeTopicLabel.textContent = sdata.title;
        }
        renderHistory();
      }
    };
    chatHistoryList.appendChild(item);
  });
}

function renderChatMessages() {
  chatMessages.innerHTML = "";
  document.getElementById("recommendationContainer").classList.toggle("hidden", state.messages.length > 0);
  state.messages.forEach((msg) => {
    appendBubble(msg.role, msg.content);
  });
}

function appendInlineMarkdown(parent, text) {
  const tokenPattern = /(\*\*.+?\*\*|`[^`]+`|\*[^*\n]+\*)/g;
  let lastIndex = 0;
  for (const match of text.matchAll(tokenPattern)) {
    if (match.index > lastIndex) {
      parent.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
    }
    const token = match[0];
    let element;
    let value;
    if (token.startsWith("**")) {
      element = document.createElement("strong");
      value = token.slice(2, -2);
    } else if (token.startsWith("`")) {
      element = document.createElement("code");
      value = token.slice(1, -1);
    } else {
      element = document.createElement("em");
      value = token.slice(1, -1);
    }
    element.textContent = value;
    parent.appendChild(element);
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    parent.appendChild(document.createTextNode(text.slice(lastIndex)));
  }
}

function getTableCells(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function isTableSeparator(line) {
  const cells = getTableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function renderMarkdown(container, markdown) {
  const lines = String(markdown).replace(/\r/g, "").split("\n");
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = codeLines.join("\n");
      pre.appendChild(code);
      container.appendChild(pre);
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const element = document.createElement(`h${Math.min(heading[1].length, 4)}`);
      appendInlineMarkdown(element, heading[2]);
      container.appendChild(element);
      index += 1;
      continue;
    }

    if (index + 1 < lines.length && line.includes("|") && isTableSeparator(lines[index + 1])) {
      const headerCells = getTableCells(line);
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      headerCells.forEach((cell) => {
        const th = document.createElement("th");
        appendInlineMarkdown(th, cell);
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      index += 2;
      while (index < lines.length && lines[index].trim().includes("|")) {
        const cells = getTableCells(lines[index]);
        const row = document.createElement("tr");
        headerCells.forEach((_, cellIndex) => {
          const td = document.createElement("td");
          appendInlineMarkdown(td, cells[cellIndex] || "");
          row.appendChild(td);
        });
        tbody.appendChild(row);
        index += 1;
      }
      table.appendChild(tbody);
      const wrapper = document.createElement("div");
      wrapper.className = "markdown-table-wrap";
      wrapper.appendChild(table);
      container.appendChild(wrapper);
      continue;
    }

    const unordered = line.match(/^[-*+•]\s+(.+)$/);
    const ordered = line.match(/^\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      const list = document.createElement(unordered ? "ul" : "ol");
      while (index < lines.length) {
        const itemLine = lines[index].trim();
        const itemMatch = itemLine.match(unordered ? /^[-*+•]\s+(.+)$/ : /^\d+[.)]\s+(.+)$/);
        if (!itemMatch) break;
        const item = document.createElement("li");
        appendInlineMarkdown(item, itemMatch[1]);
        list.appendChild(item);
        index += 1;
      }
      container.appendChild(list);
      continue;
    }

    if (/^(---+|___+|\*\*\*+)$/.test(line)) {
      container.appendChild(document.createElement("hr"));
      index += 1;
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() &&
      !/^(#{1,6})\s+/.test(lines[index].trim()) &&
      !/^[-*+•]\s+/.test(lines[index].trim()) &&
      !/^\d+[.)]\s+/.test(lines[index].trim()) &&
      !(lines[index].trim().includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, paragraphLines.join(" "));
    container.appendChild(paragraph);
  }
}

function appendBubble(role, content) {
  const b = document.createElement("div");
  b.className = `chat-bubble ${role}`;
  if (role === "assistant") {
    b.classList.add("markdown-body");
    renderMarkdown(b, content);
  } else {
    b.textContent = content;
  }
  chatMessages.appendChild(b);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return b;
}

// Chat API Communication
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = chatInput.value.trim();
  if (!q) return;

  if (state.messages.length === 0 || state.currentChatTitle.startsWith("New Topic") || state.currentChatTitle.startsWith("Topic ")) {
    const smart = suggestSmartTopic(q);
    state.currentChatTitle = smart;
    activeTopicLabel.textContent = smart;
    if (!state.notes[state.activeNoteId]) {
      state.notes[state.activeNoteId] = {
        title: smart,
        content: `# Notes: ${smart}\n\n`,
        updated_at: new Date().toLocaleTimeString(),
      };
      noteTitleInput.value = smart;
      noteTextArea.value = state.notes[state.activeNoteId].content;
      renderNotesHistory();
    }
  }

  state.messages.push({ role: "user", content: q });
  appendBubble("user", q);
  chatInput.value = "";
  document.getElementById("recommendationContainer").classList.add("hidden");
  saveCurrentChat();

  const loader = appendBubble("assistant loading", "Searching company documents...");
  const startTime = performance.now();

  try {
    const res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({
        session_id: state.sessionId,
        question: q,
      }),
    });

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
    state.analytics.lastLatency = `${elapsed}s`;
    lastLatencyText.textContent = state.analytics.lastLatency;

    if (res.status === 401) {
      loader.remove();
      returnToLoginForExpiredSession();
      return;
    }

    if (res.status === 403) {
      state.analytics.blockedCount++;
      blockedCountText.textContent = state.analytics.blockedCount;
      const err = await res.json();
      loader.remove();
      const errorMessage = `🔒 Access Denied: ${err.detail}`;
      appendBubble("assistant", errorMessage);
      state.messages.push({ role: "assistant", content: errorMessage });
      saveCurrentChat();
      return;
    }

    if (!res.ok) {
      let detail = `The server returned an error (${res.status}).`;
      try {
        const errorData = await res.json();
        if (errorData.detail) detail = errorData.detail;
      } catch {
        // Keep the status message when the server response is not JSON.
      }
      loader.remove();
      const errorMessage = `The API could not answer this request: ${detail}`;
      appendBubble("assistant", errorMessage);
      state.messages.push({ role: "assistant", content: errorMessage });
      saveCurrentChat();
      return;
    }

    const data = await res.json();
    loader.remove();
    appendBubble("assistant", data.answer);
    state.messages.push({ role: "assistant", content: data.answer });

    if (data.sources) {
      data.sources.forEach((s) => state.analytics.sources.add(s));
      updateAnalyticsSources();
    }
    if (data.intent) {
      state.analytics.intents.add(data.intent);
      updateAnalyticsIntents();
    }

    saveCurrentChat();
  } catch (error) {
    loader.remove();
    const errorMessage = `Cannot reach the API at ${API_URL}. Check http://127.0.0.1:8000/health, then start the server with: python -m uvicorn api:app --app-dir app --reload --port 8000`;
    console.error("Chat request failed:", error);
    appendBubble("assistant", errorMessage);
    state.messages.push({ role: "assistant", content: errorMessage });
    saveCurrentChat();
  }
});

function updateAnalyticsSources() {
  sourcesList.innerHTML = "";
  state.analytics.sources.forEach((s) => {
    const li = document.createElement("li");
    li.textContent = `• ${s}`;
    sourcesList.appendChild(li);
  });
}

function updateAnalyticsIntents() {
  intentsList.innerHTML = "";
  state.analytics.intents.forEach((it) => {
    const li = document.createElement("li");
    li.textContent = `• ${it}`;
    intentsList.appendChild(li);
  });
}

// Scratchpad & Notes
newNoteBtn.addEventListener("click", () => {
  persistActiveNote();
  const nid = createSessionId();
  state.activeNoteId = nid;
  state.notes[nid] = {
    title: "Untitled Note",
    content: "",
    updated_at: new Date().toLocaleTimeString(),
  };
  if (state.chatSessions[state.sessionId]) {
    state.chatSessions[state.sessionId].noteId = nid;
  }
  noteTitleInput.value = state.notes[nid].title;
  noteTextArea.value = "";
  downloadNoteBtn.disabled = true;
  switchView("notes");
  renderNotesHistory();
});

noteTextArea.addEventListener("input", (e) => {
  const nid = state.activeNoteId;
  const content = e.target.value;
  const existing = state.notes[nid] || { title: "Untitled Note" };
  const title = noteTitleInput.value.trim() || existing.title;

  state.notes[nid] = {
    ...existing,
    title,
    content,
    updated_at: new Date().toLocaleTimeString(),
  };

  downloadNoteBtn.disabled = !content.trim();
  renderNotesHistory();
});

noteTitleInput.addEventListener("input", () => {
  const nid = state.activeNoteId;
  const existing = state.notes[nid] || { title: "Untitled Note", content: "" };
  state.notes[nid] = {
    ...existing,
    title: noteTitleInput.value.trim() || "Untitled Note",
    content: noteTextArea.value,
    updated_at: new Date().toLocaleTimeString(),
  };
  renderNotesHistory();
});

saveNoteBtn.addEventListener("click", () => {
  persistActiveNote();
  if (state.messages.length) saveCurrentChat();
  renderNotesHistory();
  alert("Note saved. Chat and note titles are managed separately.");
});

function renderNotesHistory() {
  notesHistoryList.innerHTML = "";
  Object.entries(state.notes).forEach(([nid, ndata]) => {
    const item = document.createElement("div");
    item.className = `history-item ${nid === state.activeNoteId ? "active" : ""}`;
    const title = document.createElement("span");
    title.className = "item-title";
    title.textContent = `${nid === state.activeNoteId ? "📌" : "📝"} ${ndata.title}`;
    item.appendChild(title);
    title.onclick = () => {
      state.activeNoteId = nid;
      noteTitleInput.value = ndata.title;
      noteTextArea.value = ndata.content;
      downloadNoteBtn.disabled = !ndata.content.trim();
      const linkedChat = Object.entries(state.chatSessions).find(([, chat]) => chat.noteId === nid);
      if (linkedChat) {
        const [sid, chat] = linkedChat;
        state.sessionId = sid;
        state.messages = [...chat.messages];
        state.currentChatTitle = chat.title;
        activeTopicLabel.textContent = chat.title;
        renderChatMessages();
        renderHistory();
      }
      switchView("notes");
      notesSection.scrollIntoView({ behavior: "smooth", block: "start" });
      renderNotesHistory();
    };
    notesHistoryList.appendChild(item);
  });
}

downloadNoteBtn.addEventListener("click", () => {
  const note = state.notes[state.activeNoteId];
  if (!note || !note.content.trim()) return;

  const blob = new Blob([note.content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${note.title.toLowerCase().replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.txt`;
  a.click();
  URL.revokeObjectURL(url);
});

// View Switching
function switchView(target) {
  state.currentView = target;
  if (target === "chat") {
    tabChat.classList.add("active");
    tabNotes.classList.remove("active");
    navAnalytics.classList.remove("active");
    workspaceHero.classList.remove("hidden");
    chatSection.classList.remove("hidden");
    notesSection.classList.add("hidden");
  } else {
    tabNotes.classList.add("active");
    tabChat.classList.remove("active");
    navAnalytics.classList.remove("active");
    workspaceHero.classList.add("hidden");
    notesSection.classList.remove("hidden");
    chatSection.classList.add("hidden");
  }
}

tabChat.addEventListener("click", () => {
  switchView("chat");
  chatSection.scrollIntoView({ behavior: "smooth", block: "start" });
});
tabNotes.addEventListener("click", () => {
  switchView("notes");
  notesSection.scrollIntoView({ behavior: "smooth", block: "start" });
});
navAnalytics.addEventListener("click", () => {
  tabChat.classList.remove("active");
  tabNotes.classList.remove("active");
  navAnalytics.classList.add("active");
  analyticsSection.scrollIntoView({ behavior: "smooth", block: "start" });
});
document.getElementById("heroNewChatBtn").addEventListener("click", () => {
  newChatBtn.click();
  chatSection.scrollIntoView({ behavior: "smooth", block: "start" });
});

if ("IntersectionObserver" in window) {
  const sectionObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      if (entry.target === analyticsSection) {
        navAnalytics.classList.add("active");
        tabChat.classList.remove("active");
        tabNotes.classList.remove("active");
      } else if (entry.target === chatSection && state.currentView === "chat") {
        navAnalytics.classList.remove("active");
        tabChat.classList.add("active");
      }
    });
  }, { threshold: 0.22 });
  sectionObserver.observe(analyticsSection);
  sectionObserver.observe(chatSection);
  sectionObserver.observe(notesSection);
}

// Initialize from existing local token
if (state.token && state.user) {
  initAppSession();
}
