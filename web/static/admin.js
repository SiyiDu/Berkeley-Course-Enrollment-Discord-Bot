const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const loginButton = document.getElementById("login");
const extractButton = document.getElementById("extract");
const refreshButton = document.getElementById("refresh");
const statusEl = document.getElementById("status");
const proposalsEl = document.getElementById("proposals");
const baseUrl = (window.ENGINE_BASE_URL || window.location.origin || "").replace(/\/$/, "");

let adminToken = localStorage.getItem("adminToken") || "";

function setStatus(message) {
  statusEl.textContent = message;
}

function setToken(token) {
  adminToken = token;
  if (token) {
    localStorage.setItem("adminToken", token);
  } else {
    localStorage.removeItem("adminToken");
  }
}

async function login() {
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    setStatus("Username and password required.");
    return;
  }
  setStatus("Signing in...");
  try {
    const response = await fetch(`${baseUrl}/api/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    setToken(payload.token || "");
    setStatus("Signed in.");
    await loadProposals();
  } catch (error) {
    setToken("");
    setStatus(error?.message || "Login failed.");
  }
}

function clearProposals() {
  proposalsEl.innerHTML = "";
}

function renderProposal(proposal) {
  const wrapper = document.createElement("div");
  wrapper.className = "proposal";

  const title = document.createElement("h3");
  title.textContent = proposal.title || "Untitled";

  const summary = document.createElement("p");
  summary.textContent = proposal.summary || "";

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `Type: ${proposal.type} | Confidence: ${proposal.confidence ?? 0}`;

  const actions = document.createElement("div");
  actions.className = "actions";

  const approve = document.createElement("button");
  approve.className = "approve";
  approve.textContent = "Approve";
  approve.addEventListener("click", () => handleAction(proposal.id, "approve"));

  const reject = document.createElement("button");
  reject.textContent = "Reject";
  reject.addEventListener("click", () => handleAction(proposal.id, "reject"));

  actions.append(approve, reject);
  wrapper.append(title, summary, meta, actions);
  proposalsEl.appendChild(wrapper);
}

async function handleAction(id, action) {
  if (!adminToken) {
    setStatus("Please sign in.");
    return;
  }
  try {
    const response = await fetch(`${baseUrl}/api/admin/proposals/${id}/${action}`, {
      method: "POST",
      headers: {
        "X-ADMIN-TOKEN": adminToken,
        "Content-Type": "application/json",
      },
      body: action === "approve" ? JSON.stringify({}) : undefined,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    setStatus(`${action} succeeded for ${id}.`);
    await loadProposals();
  } catch (error) {
    setStatus(error?.message || "Action failed.");
  }
}

async function loadProposals() {
  if (!adminToken) {
    setStatus("Please sign in.");
    return;
  }
  clearProposals();
  setStatus("Loading proposals...");
  try {
    const response = await fetch(`${baseUrl}/api/admin/proposals?status=proposed`, {
      headers: { "X-ADMIN-TOKEN": adminToken },
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    const proposals = payload.proposals || [];
    if (proposals.length === 0) {
      setStatus("No pending proposals.");
      return;
    }
    proposals.forEach(renderProposal);
    setStatus(`Loaded ${proposals.length} proposals.`);
  } catch (error) {
    setStatus(error?.message || "Failed to load proposals.");
  }
}

async function runExtraction() {
  if (!adminToken) {
    setStatus("Please sign in.");
    return;
  }
  setStatus("Starting extraction...");
  try {
    const response = await fetch(`${baseUrl}/api/admin/jobs/extract`, {
      method: "POST",
      headers: { "X-ADMIN-TOKEN": adminToken },
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    setStatus(`Extraction queued (job ${payload.job_id}).`);
  } catch (error) {
    setStatus(error?.message || "Failed to run extraction.");
  }
}

loginButton.addEventListener("click", login);
extractButton.addEventListener("click", runExtraction);
refreshButton.addEventListener("click", loadProposals);

if (adminToken) {
  setStatus("Signed in.");
}
