const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let data = null;
let currentQuestion = null;
let currentNode = null;
let diagnosticTarget = null;
let questionStarted = 0;
let timerHandle = null;
let sessionStarted = 0;
let finishingSession = false;
let submitting = false;
let currentAttemptId = null;

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}
const post = (path, body) => api(path, {method: "POST", body: JSON.stringify(body)});
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const media = (path) => `/media?path=${encodeURIComponent(path)}`;
function toast(message) {
  const target = $("#toast");
  target.textContent = message;
  target.classList.add("show");
  setTimeout(() => target.classList.remove("show"), 3200);
}
const metric = (label, value) => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
const item = (title, meta = "") => `<div class="item"><strong>${esc(title)}</strong>${meta ? `<div class="meta">${esc(meta)}</div>` : ""}</div>`;

async function boot() {
  data = await api("/api/bootstrap");
  const profiles = data.catalog?.profiles || {};
  document.title = data.catalog?.title || "Learning Cockpit";
  $("#cockpitTitle").textContent = data.catalog?.title || "Learning Cockpit";
  const currentCourse = $("#courseFilter").value;
  $("#courseFilter").innerHTML = `<option value="">All courses</option>` + Object.entries(profiles).map(([key, profile]) => `<option value="${esc(key)}">${esc(profile.label)}</option>`).join("");
  if (profiles[currentCourse]) $("#courseFilter").value = currentCourse;
  $("#courseSettings").innerHTML = Object.entries(profiles).map(([key, profile]) => `<label><input type="checkbox" data-active-course="${esc(key)}"> ${esc(profile.label)}</label>`).join("");
  $("#routeSettings").innerHTML = Object.entries(profiles).filter(([, profile]) => Object.keys(profile.routes || {}).length).map(([course, profile]) => `<label>${esc(profile.label)} route<select data-route-course="${esc(course)}">${Object.entries(profile.routes).map(([key, route]) => `<option value="${esc(key)}">${esc(route.label || key)}</option>`).join("")}</select></label>`).join("");
  renderToday(data.today);
  loadSettings(data.settings);
  if (data.today.active_session) {
    showSession(data.today.active_session);
    switchView("study");
  } else {
    switchView("today");
  }
}

function renderToday(today) {
  const p = today.progress;
  $("#deadline").innerHTML = `<span class="muted">Mastery deadline</span><br>${p.days_left} days · ${esc(p.pace)}`;
  $("#metrics").innerHTML = metric("Target proficient", `${p.proficient_pct}%`) +
    metric("Target mastered", `${p.mastered_pct}%`) + metric("FSRS due", today.due.length) +
    metric("Timed rolling", `${p.timed_rolling_pct}%`) + metric("Needed / week", p.weekly_nodes_needed);
  $("#due").innerHTML = today.due.length ? today.due.slice(0, 6).map((x) => item(x.label, `Node ${x.node ?? "?"}`)).join("") : `<p class="muted">No compressed reviews due.</p>`;
  $("#learn").innerHTML = today.learn.length ? today.learn.slice(0, 7).map((x) => item(`#${x.node} ${x.name}`, `${x.domain} · ${Math.round(x.progress.pct * 100)}% · ${x.question_count} questions · unlocks ${x.unlock_count}`)).join("") : `<p class="muted">No reachable target nodes.</p>`;
  $("#remediation").innerHTML = today.remediation.length ? today.remediation.map((r) => `<div class="item"><span class="pill">Support #${r.support}</span><strong> ${esc(r.support_name)}</strong><div class="meta">Unblocks #${r.target} ${esc(r.target_name)} · ${r.estimated_minutes} min</div><div>${esc(r.reason)}</div></div>`).join("") : `<p class="muted">No prerequisite intervention has enough evidence yet.</p>`;
  renderProgress(p);
}

function renderProgress(p) {
  const domains = Object.entries(p.domain_scores).sort((a, b) => a[1] - b[1]).map(([name, value]) => `<div class="domainRow"><div>${esc(name)}<div class="bar"><i style="width:${value}%"></i></div></div><strong>${value}%</strong></div>`).join("");
  const gate = data.catalog?.mastery_gate || {};
  $("#progressContent").innerHTML = `<div class="progressGrid"><article><h2>${esc(p.deadline)} mastery gate</h2>${item(`${gate.target_proficient_pct ?? 100}% target proficient`, `${p.proficient_pct}%`)}${item(`${gate.target_mastered_pct ?? 95}% target mastered`, `${p.mastered_pct}%`)}${item(`Latest 3 timed sets ≥${gate.timed_average_pct ?? 85}%`, `${p.timed_rolling_pct}%`)}${item("High-severity gaps cleared", String(p.high_errors))}<p class="${p.gate_pass ? "" : "warn"}">${p.gate_pass ? "Gate passed" : "Evidence gate not yet passed"}</p></article><article><h2>Domain proficiency</h2>${domains || "<p class=muted>No mapped domains.</p>"}</article></div>`;
}

function switchView(id) {
  $$("nav button").forEach((button) => button.classList.toggle("active", button.dataset.view === id));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === id));
  if (id === "courses") loadNodes();
}
$$('nav button').forEach((button) => button.onclick = () => switchView(button.dataset.view));

$$('[data-start]').forEach((button) => button.onclick = async () => {
  try {
    const session = await post("/api/session/start", {kind: button.dataset.start, course: $("#courseFilter").value || "", minutes: Number(data.settings.session_minutes)});
    showSession(session);
    switchView("study");
  } catch (error) { toast(error.message); }
});

function formatTime(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function showSession(session) {
  $("#sessionEmpty").hidden = true;
  $("#session").hidden = false;
  $("#sessionKind").textContent = session.kind;
  $("#sessionPhase").textContent = session.phase;
  sessionStarted = Date.parse(session.started_at) || Date.now();
  clearInterval(timerHandle);
  timerHandle = setInterval(() => {
    const elapsed = (Date.now() - sessionStarted) / 1000;
    if (session.kind === "timed") {
      const remaining = session.minutes * 60 - elapsed;
      $("#timer").textContent = formatTime(remaining);
      if (remaining <= 0) $("#finishSession").click();
    } else $("#timer").textContent = formatTime(elapsed);
  }, 1000);
  const reviewed = new Set(session.reviewed_keys || []);
  const pendingKey = (session.review_keys || []).find((key) => !reviewed.has(key));
  const pendingReview = pendingKey && (data.today.due.find((item) => item.key === pendingKey) || {key: pendingKey, label: pendingKey});
  if (session.kind === "guided" && pendingReview && !session.remediation) showReview(pendingReview);
  else loadSessionQuestion(session);
}

function showReview(review) {
  $("#reviewCard").hidden = false;
  $("#questionCard").hidden = true;
  $("#reviewPrompt").textContent = review.label;
  $("#reviewCard").dataset.key = review.key;
}

$$('[data-rating]').forEach((button) => button.onclick = async () => {
  try {
    const session = await api("/api/session");
    await post("/api/review", {key: $("#reviewCard").dataset.key, rating: Number(button.dataset.rating), session_id: session.id});
    $("#reviewCard").hidden = true;
    showSession(await api("/api/session"));
  } catch (error) { toast(error.message); }
});

async function loadSessionQuestion(session) {
  let question = null;
  let nodeHint = null;
  diagnosticTarget = null;
  const remediation = session.remediation;
  if (remediation?.status === "testing") {
    const done = new Set((remediation.attempts || []).map((x) => x.id));
    const id = (remediation.question_ids || []).find((x) => !done.has(x));
    if (id) {
      question = await api(`/api/question?id=${encodeURIComponent(id)}`);
      nodeHint = remediation.support;
      diagnosticTarget = remediation.target;
    }
  } else if (remediation?.status === "passed") {
    question = await api(`/api/question?node=${remediation.target}`);
    nodeHint = remediation.target;
  } else if (remediation?.status === "repair") {
    showRepairPause(remediation);
    return;
  } else {
    const retry = (session.retry_queue || []).find((x) => x.after <= (session.sequence || []).length);
    if (retry) question = await api(`/api/question?id=${encodeURIComponent(retry.id)}`);
    if (!question && session.question_ids?.length) {
      const attempted = new Set(session.attempt_ids || []);
      const id = session.question_ids.find((x) => !attempted.has(x));
      if (id) question = await api(`/api/question?id=${encodeURIComponent(id)}`);
    }
    if (!question) question = await api(`/api/question?course=${encodeURIComponent(session.course || "")}`);
  }
  if (!question?.id) { toast("Session queue complete"); return; }
  renderQuestion(question, session, nodeHint);
}

function renderQuestion(question, session, nodeOverride = null) {
  currentQuestion = question;
  currentNode = Number(nodeOverride || question.topic_node_ids?.[0]);
  questionStarted = Date.now();
  currentAttemptId = crypto.randomUUID();
  submitting = false;
  setAttemptControls(false);
  $("#questionCard").hidden = false;
  $("#reviewCard").hidden = true;
  $("#answer").hidden = true;
  $("#gradePanel").hidden = true;
  $("#errorFields").hidden = true;
  $("#causalResult").innerHTML = "";
  $("#questionMeta").textContent = `${question.code || question.course} · ${question.difficulty || "?"} · ${question.marks || 1} mark(s) · node ${currentNode}`;
  $("#questionTitle").textContent = question.id;
  $("#questionImages").innerHTML = question.question_images?.length ? question.question_images.map((path) => `<img src="${media(path)}" alt="Question">`).join("") : `<pre>${esc(question.question || "Question image missing")}</pre>`;
  $("#answerTex").textContent = (question.answers_tex || []).join("  ·  ");
  $("#markschemeImages").innerHTML = (question.markscheme_images || []).map((path) => `<img src="${media(path)}" alt="Mark scheme">`).join("");
  $("#reveal").hidden = false;
  $("#errorNote").value = "";
  $("#errorType").value = "unknown";
}

function setAttemptControls(disabled) {
  $$('[data-grade]').forEach((button) => { button.disabled = disabled; });
  $("#skipQuestion").disabled = disabled;
}

function focusNode(node) {
  $("#nodeSearch").value = String(node);
  switchView("courses");
  loadNodes();
}

function showRepairPause(remediation) {
  $("#questionCard").hidden = true;
  $("#causalResult").innerHTML = `<article><span class="pill">Confirmed support gap</span><h2>${esc(remediation.support_name)}</h2><p>Spend 10–20 focused minutes learning only this gap. Mark subskills you can now demonstrate, then retest before returning to ${esc(remediation.target_name)}.</p><div class="actions"><button id="viewRepairNode">View skill checklist</button><button class="primary" id="retestSupport">Retest support skill</button></div></article>`;
  $("#viewRepairNode").onclick = () => focusNode(remediation.support);
  $("#retestSupport").onclick = async () => {
    try { showSession(await post("/api/remediation/retest", {})); }
    catch (error) { toast(error.message); }
  };
}

function showLearningPause(attempt) {
  $("#causalResult").innerHTML = `<article><span class="pill">Learning pause</span><h2>Repair target #${attempt.node}</h2><p>Spend 10–20 minutes learning the specific missing idea, mark only subskills you can demonstrate, then continue. The question is already queued for a delayed retry.</p><div class="actions"><button id="viewTargetNode">View skill checklist</button><button class="primary" id="continueSession">Continue session</button></div></article>`;
  $("#viewTargetNode").onclick = () => focusNode(attempt.node);
  $("#continueSession").onclick = async () => loadSessionQuestion(await api("/api/session"));
}

$("#reveal").onclick = () => {
  $("#answer").hidden = false;
  $("#gradePanel").hidden = false;
  $("#reveal").hidden = true;
};
$$('[data-grade]').forEach((button) => button.onclick = () => gradeQuestion(button.dataset.grade));

async function gradeQuestion(grade) {
  if (!currentQuestion || submitting) return;
  if ((grade === "wrong" || grade === "partial") && $("#errorFields").hidden) {
    $("#errorFields").hidden = false;
    $("#errorNote").focus();
    $("#errorFields").dataset.grade = grade;
    return;
  }
  if (grade === "wrong" || grade === "partial") {
    if ($("#errorType").value === "unknown") { toast("Choose the main error type"); $("#errorType").focus(); return; }
    if (!$("#errorNote").value.trim()) { toast("Write one short sentence about what went wrong"); $("#errorNote").focus(); return; }
  }
  submitting = true;
  setAttemptControls(true);
  try {
    const session = await api("/api/session");
    const result = await post("/api/attempt", {
      id: currentQuestion.id, node: currentNode, course: currentQuestion.course || currentQuestion.code,
      grade, error_type: $("#errorType").value, note: $("#errorNote").value,
      duration_seconds: Math.round((Date.now() - questionStarted) / 1000),
      session_id: session.id, attempt_id: currentAttemptId, diagnostic_for: diagnosticTarget,
    });
    if (result.duplicate) { toast("Attempt already saved"); setTimeout(async () => loadSessionQuestion(await api("/api/session")), 250); return; }
    if (result.causal) {
      $("#causalResult").innerHTML = `<article><span class="pill">Causal check</span><h2>${esc(result.causal.support_name)}</h2><p>${esc(result.causal.reason)}</p><p><strong>${result.causal.estimated_minutes} minutes.</strong> ${esc(result.causal.return_condition)}</p><button class="primary" id="startRemediation">Test ${esc(result.causal.support_name)}</button></article>`;
      $("#startRemediation").onclick = async () => showSession(await post("/api/remediation/start", {target: result.causal.target}));
      return;
    }
    if (result.remediation) {
      if (result.remediation.status === "passed") {
        toast("Support diagnostic passed — return to the target");
        setTimeout(async () => loadSessionQuestion(await api("/api/session")), 500);
      } else {
        toast("Support gap confirmed — begin a short repair block");
        showRepairPause(result.remediation);
      }
    } else if ((grade === "wrong" || grade === "partial") && ["concept", "prerequisite", "strategy"].includes($("#errorType").value)) {
      showLearningPause(result.attempt);
    } else {
      toast(result.fsrs_graded ? `${result.fsrs_graded} FSRS card(s) updated` : "Attempt saved");
      setTimeout(async () => loadSessionQuestion(await api("/api/session")), 300);
    }
  } catch (error) { submitting = false; setAttemptControls(false); toast(error.message); }
}

$("#errorNote").addEventListener("keydown", (event) => { if (event.key === "Enter") gradeQuestion($("#errorFields").dataset.grade); });
$("#skipQuestion").onclick = () => gradeQuestion("skip");
$("#finishSession").onclick = async () => {
  if (finishingSession) return;
  finishingSession = true;
  const button = $("#finishSession");
  button.disabled = true;
  button.textContent = "Syncing Obsidian…";
  try {
    const result = await post("/api/session/finish", {});
    clearInterval(timerHandle);
    $("#session").hidden = true;
    $("#sessionEmpty").hidden = false;
    if (result.status === "discarded") toast("Empty session discarded — progress unchanged");
    else if (result.visual_sync?.ok) toast(`Session complete: ${result.correct || 0}/${result.questions_seen || 0} · Obsidian refreshed`);
    else toast("Session saved, but Obsidian refresh needs retry (run python evening.py)");
    await boot();
  } catch (error) {
    toast(error.message);
  } finally {
    finishingSession = false;
    button.disabled = false;
    button.textContent = "Finish";
  }
};

async function loadNodes() {
  const query = encodeURIComponent($("#nodeSearch").value);
  const nodes = await api(`/api/nodes?q=${query}&layer=${$("#layerFilter").value}&course=${$("#courseFilter").value}`);
  $("#nodeList").innerHTML = nodes.map((node) => `<div class="node layer-${node.layer}"><strong>#${node.id}</strong><div><h3>${esc(node.name)}</h3><div class="meta">${esc(node.domain)} · ${node.layer} · ${(node.courses || []).join(", ") || "support only"}</div><div class="bar"><i style="width:${Math.round(node.progress.pct * 100)}%"></i></div></div><button data-practice="${node.id}">Practice</button><details class="subskills"><summary>${node.progress.done}/${node.progress.total} subskills · prerequisites ${(node.prerequisites || []).join(", ") || "none"}</summary>${(node.subskills || []).map((s) => `<label><input type="checkbox" data-node="${node.id}" data-subskill="${esc(s.id)}" ${s.done ? "checked" : ""}> ${esc(s.id)}: ${esc(s.description)}</label>`).join("")}</details></div>`).join("") || `<div class="empty">No nodes match.</div>`;
  $$('[data-practice]').forEach((button) => button.onclick = async () => {
    const session = await post("/api/session/start", {kind: "guided", course: "", minutes: Number(data.settings.session_minutes)});
    showSession(session);
    const question = await api(`/api/question?node=${button.dataset.practice}`);
    if (question.id) renderQuestion(question, session, Number(button.dataset.practice));
    switchView("study");
  });
  $$('[data-subskill]').forEach((box) => box.onchange = async () => {
    try {
      await post("/api/subskill", {node: Number(box.dataset.node), subskill: box.dataset.subskill, done: box.checked});
      toast("Subskill updated");
    } catch (error) { box.checked = !box.checked; toast(error.message); }
  });
}

let searchTimer;
["nodeSearch", "layerFilter", "courseFilter"].forEach((id) => $("#" + id).addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadNodes, 180);
}));

function loadSettings(settings) {
  $("#settingDeadline").value = settings.deadline;
  $("#settingHours").value = settings.weekly_hours;
  $("#settingMinutes").value = settings.session_minutes;
  const active = new Set(settings.courses || []);
  $$('[data-active-course]').forEach((box) => { box.checked = active.has(box.dataset.activeCourse); });
  $$('[data-route-course]').forEach((select) => { select.value = settings[`route_${select.dataset.routeCourse}`] || select.value; });
}
$("#saveSettings").onclick = async () => {
  try {
    const courses = $$('[data-active-course]:checked').map((box) => box.dataset.activeCourse);
    if (!courses.length) throw new Error("Select at least one active course");
    const changes = {deadline: $("#settingDeadline").value, weekly_hours: Number($("#settingHours").value), session_minutes: Number($("#settingMinutes").value), courses};
    $$('[data-route-course]').forEach((select) => { changes[`route_${select.dataset.routeCourse}`] = select.value; });
    data.settings = await post("/api/settings", changes);
    toast("Settings saved");
    await boot();
  } catch (error) { toast(error.message); }
};

document.addEventListener("keydown", (event) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (event.key === " " && !$("#reveal").hidden) { event.preventDefault(); $("#reveal").click(); }
  if (!$("#reviewCard").hidden && ["1", "2", "3", "4"].includes(event.key)) $(`[data-rating="${event.key}"]`).click();
  if (!$("#gradePanel").hidden) {
    if (event.key.toLowerCase() === "c") gradeQuestion("correct");
    if (event.key.toLowerCase() === "p") gradeQuestion("partial");
    if (event.key.toLowerCase() === "w") gradeQuestion("wrong");
  }
});

boot().catch((error) => toast(error.message));
