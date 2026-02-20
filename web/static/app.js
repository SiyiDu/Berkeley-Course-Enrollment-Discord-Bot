const form = document.getElementById("ask-form");
const input = document.getElementById("query");
const result = document.getElementById("result");
const professorInput = document.getElementById("professor");
const suggestions = document.getElementById("professor-suggestions");
const courseDeptSelect = document.getElementById("course-dept");
const courseNumberInput = document.getElementById("course-number");
const courseSuggestions = document.getElementById("course-suggestions");
const clearScope = document.getElementById("clear-scope");
const baseUrl = (window.ENGINE_BASE_URL || window.location.origin || "").replace(/\/$/, "");
let professors = [];
let selectedProfessor = null;
let courses = [];
let selectedCourse = null;
let offerings = [];
let courseCodesByProfessor = new Map();
let professorsByCourse = new Map();

function setSuggestions(items) {
  suggestions.innerHTML = "";
  if (items.length === 0) {
    suggestions.classList.remove("visible");
    return;
  }
  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "suggestion-item";
    div.textContent = item.name;
    div.addEventListener("click", () => {
      selectedProfessor = item;
      professorInput.value = item.name;
      suggestions.classList.remove("visible");
      updateDepartmentOptions(getAllowedCourseCodesForProfessor());
      if (courseNumberInput.value.trim()) {
        courseNumberInput.dispatchEvent(new Event("input"));
      }
    });
    suggestions.appendChild(div);
  });
  suggestions.classList.add("visible");
}

function setCourseSuggestions(items) {
  courseSuggestions.innerHTML = "";
  if (items.length === 0) {
    courseSuggestions.classList.remove("visible");
    return;
  }
  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "suggestion-item";
    const title = item.title_optional ? ` - ${item.title_optional}` : "";
    div.textContent = `${item.code}${title}`;
    div.addEventListener("click", () => {
      selectedCourse = item;
      courseNumberInput.value = item.code;
      const dept = extractDepartment(item.code);
      if (dept) {
        courseDeptSelect.value = dept;
      }
      courseSuggestions.classList.remove("visible");
      refreshProfessorSuggestions();
    });
    courseSuggestions.appendChild(div);
  });
  courseSuggestions.classList.add("visible");
}

function normalizeCode(code) {
  return String(code || "").replace(/\s+/g, "").toUpperCase();
}

function normalizeName(name) {
  return String(name || "").trim().toLowerCase();
}

async function loadProfessors() {
  try {
    const response = await fetch(`${baseUrl}/api/catalog/professors`);
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    professors = payload.professors || [];
  } catch {
    professors = [];
  }
}

function extractDepartment(code) {
  const match = String(code || "").trim().match(/^[A-Za-z]+/);
  return match ? match[0].toUpperCase() : "";
}

function updateDepartmentOptions(allowedCodes) {
  const departments = new Set();
  const source = allowedCodes
    ? courses.filter((course) => allowedCodes.has(normalizeCode(course.code)))
    : courses;

  source.forEach((course) => {
    if (course.code) {
      const dept = extractDepartment(course.code);
      if (dept) {
        departments.add(dept);
      }
    }
  });

  const sorted = Array.from(departments).sort();
  courseDeptSelect.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = allowedCodes ? "All matching departments" : "All departments";
  courseDeptSelect.appendChild(allOption);
  sorted.forEach((dept) => {
    const option = document.createElement("option");
    option.value = dept;
    option.textContent = dept;
    courseDeptSelect.appendChild(option);
  });
}

async function loadCourses() {
  try {
    const response = await fetch(`${baseUrl}/api/catalog/courses`);
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    courses = payload.courses || [];
    updateDepartmentOptions(null);
  } catch {
    courses = [];
  }
}

async function loadOfferings() {
  try {
    const response = await fetch(`${baseUrl}/api/catalog/offerings`);
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    offerings = payload.offerings || [];
    courseCodesByProfessor = new Map();
    professorsByCourse = new Map();
    offerings.forEach((offering) => {
      const code = normalizeCode(offering.course_code);
      const professorName = normalizeName(offering.professor_name);
      if (!code || !professorName) {
        return;
      }
      if (!courseCodesByProfessor.has(professorName)) {
        courseCodesByProfessor.set(professorName, new Set());
      }
      courseCodesByProfessor.get(professorName).add(code);
      if (!professorsByCourse.has(code)) {
        professorsByCourse.set(code, new Set());
      }
      professorsByCourse.get(code).add(professorName);
    });
  } catch {
    offerings = [];
  }
}

function getMatchingProfessorNames() {
  if (selectedProfessor?.name) {
    return [selectedProfessor.name];
  }
  const value = professorInput.value.trim().toLowerCase();
  if (!value) {
    return [];
  }
  return professors
    .filter((prof) => prof.name && prof.name.toLowerCase().includes(value))
    .map((prof) => prof.name);
}

function getAllowedCourseCodesForProfessor() {
  if (offerings.length === 0) {
    return null;
  }
  const names = getMatchingProfessorNames();
  if (names.length === 0) {
    return null;
  }
  const codes = new Set();
  names.forEach((name) => {
    const set = courseCodesByProfessor.get(normalizeName(name));
    if (set) {
      set.forEach((code) => codes.add(code));
    }
  });
  return codes;
}

function getCourseCodeMatches() {
  if (selectedCourse?.code) {
    return [normalizeCode(selectedCourse.code)];
  }
  const value = courseNumberInput.value.trim().toUpperCase().replace(/\s+/g, "");
  if (!value) {
    return [];
  }
  const dept = courseDeptSelect.value;
  return courses
    .filter((course) => {
      if (!course.code) {
        return false;
      }
      const code = normalizeCode(course.code);
      if (dept && !code.startsWith(dept)) {
        return false;
      }
      if (dept && /^[0-9]/.test(value)) {
        return code.startsWith(`${dept}${value}`) || code.includes(value);
      }
      return code.includes(value);
    })
    .map((course) => normalizeCode(course.code));
}

function getAllowedProfessorNamesForCourse() {
  if (offerings.length === 0) {
    return null;
  }
  const codes = getCourseCodeMatches();
  if (codes.length === 0) {
    return null;
  }
  const allowed = new Set();
  codes.forEach((code) => {
    const set = professorsByCourse.get(code);
    if (set) {
      set.forEach((name) => allowed.add(name));
    }
  });
  return allowed;
}

function refreshProfessorSuggestions() {
  const value = professorInput.value.trim();
  const valueLower = value.toLowerCase();
  if (!valueLower) {
    selectedProfessor = null;
    setSuggestions([]);
    return;
  }
  if (!selectedProfessor || normalizeName(selectedProfessor.name) !== valueLower) {
    selectedProfessor = null;
  }
  const allowed = getAllowedProfessorNamesForCourse();
  const matches = professors
    .filter((prof) => prof.name && prof.name.toLowerCase().includes(valueLower))
    .filter((prof) => !allowed || allowed.has(normalizeName(prof.name)))
    .slice(0, 6);
  setSuggestions(matches);
}

professorInput.addEventListener("input", () => {
  refreshProfessorSuggestions();
  updateDepartmentOptions(getAllowedCourseCodesForProfessor());
  if (courseNumberInput.value.trim()) {
    courseNumberInput.dispatchEvent(new Event("input"));
  }
});

courseNumberInput.addEventListener("input", () => {
  selectedCourse = null;
  const value = courseNumberInput.value.trim().toUpperCase().replace(/\s+/g, "");
  if (!value) {
    setCourseSuggestions([]);
    refreshProfessorSuggestions();
    return;
  }
  const dept = courseDeptSelect.value;
  const allowed = getAllowedCourseCodesForProfessor();
  const matches = courses
    .filter((course) => {
      if (!course.code) {
        return false;
      }
      const code = course.code.toUpperCase().replace(/\s+/g, "");
      if (dept && !code.startsWith(dept)) {
        return false;
      }
      if (dept && /^[0-9]/.test(value)) {
        return code.startsWith(`${dept}${value}`) || code.includes(value);
      }
      return code.includes(value);
    })
    .filter((course) => !allowed || allowed.has(normalizeCode(course.code)))
    .slice(0, 6);
  setCourseSuggestions(matches);
  refreshProfessorSuggestions();
});

courseDeptSelect.addEventListener("change", () => {
  if (courseNumberInput.value.trim()) {
    courseNumberInput.dispatchEvent(new Event("input"));
  } else {
    setCourseSuggestions([]);
    refreshProfessorSuggestions();
  }
});

document.addEventListener("click", (event) => {
  if (!suggestions.contains(event.target) && event.target !== professorInput) {
    suggestions.classList.remove("visible");
  }
  if (!courseSuggestions.contains(event.target) && event.target !== courseNumberInput) {
    courseSuggestions.classList.remove("visible");
  }
});

clearScope.addEventListener("click", () => {
  resetProfessorScope();
  resetCourseScope();
  updateDepartmentOptions(null);
});

function resetProfessorScope() {
  selectedProfessor = null;
  professorInput.value = "";
  setSuggestions([]);
}

function resetCourseScope() {
  selectedCourse = null;
  courseNumberInput.value = "";
  if (courseDeptSelect.options.length > 0) {
    courseDeptSelect.value = "";
  }
  setCourseSuggestions([]);
}

function buildCourseCode() {
  if (selectedCourse?.code) {
    return selectedCourse.code;
  }
  const raw = courseNumberInput.value.trim();
  if (!raw) {
    return "";
  }
  const normalized = raw.replace(/\s+/g, "");
  if (/[a-zA-Z]/.test(normalized)) {
    return normalized.toUpperCase();
  }
  const dept = courseDeptSelect.value;
  return dept ? `${dept}${normalized}`.toUpperCase() : normalized.toUpperCase();
}

let pendingBubble = null;

function showResult() {
  result.classList.add("visible");
}

function appendMessage(role, text) {
  const message = document.createElement("div");
  message.className = `message ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  message.appendChild(bubble);
  result.appendChild(message);
  showResult();
  bubble.scrollIntoView({ behavior: "smooth", block: "end" });
  return bubble;
}

async function fetchContext(chunk) {
  const params = new URLSearchParams();
  params.set("chunk_id", chunk.chunk_id);
  if (chunk.context_token) {
    params.set("context_token", chunk.context_token);
  }
  if (chunk.guild_id) {
    params.set("guild_id", chunk.guild_id);
  }
  const response = await fetch(`${baseUrl}/api/messages/context?${params.toString()}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Unable to load context.");
  }
  return response.json();
}

function renderMemoryHits(bubble, chunks) {
  const wrapper = document.createElement("div");
  wrapper.className = "memory-hits";

  const title = document.createElement("div");
  title.className = "memory-title";
  title.textContent = `Memory hits (${chunks.length})`;
  wrapper.appendChild(title);

  chunks.forEach((chunk) => {
    const card = document.createElement("div");
    card.className = "memory-card";

    const meta = document.createElement("div");
    meta.className = "memory-meta";
    meta.textContent = `${chunk.scope_type || "scope"} - ${chunk.start_ts || ""}`;
    card.appendChild(meta);

    const preview = document.createElement("div");
    preview.className = "memory-preview";
    const lines = Array.isArray(chunk.preview) ? chunk.preview : [];
    lines.forEach((line) => {
      const row = document.createElement("div");
      row.className = "memory-line";
      const author = line.author ? `${line.author}: ` : "";
      row.textContent = `${author}${line.content || ""}`;
      preview.appendChild(row);
    });
    card.appendChild(preview);

    const actions = document.createElement("div");
    actions.className = "memory-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "memory-button";
    button.textContent = "View context (+/-1 day)";
    actions.appendChild(button);
    card.appendChild(actions);

    const context = document.createElement("div");
    context.className = "context-panel";
    card.appendChild(context);

    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Loading...";
      try {
        const payload = await fetchContext(chunk);
        context.innerHTML = "";
        const header = document.createElement("div");
        header.className = "context-header";
        header.textContent = `Context ${payload.range?.start || ""} -> ${payload.range?.end || ""}`;
        context.appendChild(header);

        const list = document.createElement("div");
        list.className = "context-messages";
        (payload.messages || []).forEach((msg) => {
          const item = document.createElement("div");
          item.className = "context-message";
          item.textContent = `${msg.author || "User"}: ${msg.content || ""}`;
          list.appendChild(item);
        });
        context.appendChild(list);

        if (payload.truncated) {
          const note = document.createElement("div");
          note.className = "context-note";
          note.textContent = "More messages exist in this +/-1 day window.";
          context.appendChild(note);
        }
      } catch (error) {
        context.innerHTML = "";
        const note = document.createElement("div");
        note.className = "context-note";
        note.textContent = error?.message || "Unable to load context.";
        context.appendChild(note);
      } finally {
        button.disabled = false;
        button.textContent = "View context (+/-1 day)";
      }
    });

    wrapper.appendChild(card);
  });

  bubble.appendChild(wrapper);
}

function renderAssistantBubble(bubble, payload) {
  const answer = payload?.answer || "No answer returned.";
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  const evidence = Array.isArray(payload?.evidence) ? payload.evidence : [];
  const strength = payload?.experience_strength || null;
  const chunks = Array.isArray(payload?.chunks) ? payload.chunks : [];

  bubble.classList.remove("pending", "error");
  bubble.textContent = "";

  const paragraph = document.createElement("p");
  paragraph.textContent = answer;
  bubble.appendChild(paragraph);

  if (chunks.length) {
    renderMemoryHits(bubble, chunks);
  }

  if (cards.length || evidence.length || strength) {
    const meta = document.createElement("div");
    meta.className = "meta-list";

    if (cards.length) {
      const line = document.createElement("div");
      line.className = "meta-item";
      line.innerHTML = `<span class="meta-label">Cards</span><span>${cards
        .map((card) => {
          if (typeof card === "string") {
            return card;
          }
          return card.title || card.name || card.id || "Untitled card";
        })
        .join(" · ")}</span>`;
      meta.appendChild(line);
    }

    if (evidence.length) {
      const line = document.createElement("div");
      line.className = "meta-item";
      line.innerHTML = `<span class="meta-label">Excerpts</span><span>${evidence
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }
          return item.excerpt || item.snippet || item.text || item.quote || "Excerpt";
        })
        .join(" · ")}</span>`;
      meta.appendChild(line);
    }

    if (strength) {
      const line = document.createElement("div");
      line.className = "meta-item";
      line.innerHTML = `<span class="meta-label">Signals</span><span>${strength.signal_count || 0} mentions · ${
        strength.unique_authors || 0
      } authors · ${strength.time_range_days || 0} days</span>`;
      meta.appendChild(line);
    }

    bubble.appendChild(meta);
  }
}

function renderError(message) {
  const bubble = pendingBubble || appendMessage("assistant", "");
  pendingBubble = null;
  bubble.classList.add("error");
  bubble.textContent = message;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (!query) {
    return;
  }

  appendMessage("user", query);
  pendingBubble = appendMessage("assistant", "Thinking...");
  pendingBubble.classList.add("pending");
  try {
    const scope = {};
    const professorName = professorInput.value.trim();
    const courseCodeInput = buildCourseCode();
    const allowedCourses = getAllowedCourseCodesForProfessor();
    const allowedProfessors = getAllowedProfessorNamesForCourse();

    if (professorName && courseCodeInput && allowedCourses && !allowedCourses.has(normalizeCode(courseCodeInput))) {
      renderError("Selected professor has not taught this course.");
      return;
    }

    if (professorName && courseCodeInput && allowedProfessors && !allowedProfessors.has(normalizeName(professorName))) {
      renderError("Selected course does not match this professor.");
      return;
    }

    if (selectedProfessor) {
      scope.type = "professor";
      scope.professor_id = String(selectedProfessor.id);
    } else if (professorName) {
      scope.type = "professor";
      scope.professor_name = professorName;
    }

    if (courseCodeInput) {
      scope.type = "course";
      scope.course_code = courseCodeInput;
    }

    const response = await fetch(`${baseUrl}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        override_mode: "auto",
        viewer_role: "student",
        scope,
        context: {
          platform: "web",
        },
      }),
    });

    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "Request failed.");
    }

    const payload = await response.json();
    if (pendingBubble) {
      renderAssistantBubble(pendingBubble, payload);
      pendingBubble = null;
    } else {
      const bubble = appendMessage("assistant", "");
      renderAssistantBubble(bubble, payload);
    }
  } catch (error) {
    renderError(error?.message || "Unable to reach the API.");
  }
});

window.addEventListener("load", () => {
  input.focus();
  loadProfessors();
  loadCourses();
  loadOfferings();
});
