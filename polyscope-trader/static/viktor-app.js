(function () {
  const API = window.VIKTOR_API_BASE;
  if (!API) {
    document.getElementById("root").textContent = "API base missing.";
    return;
  }

  const state = {
    app: null,
    tab: "decisions",
    selected: null,
    detail: null,
    tag: null,
    busy: false,
  };

  function esc(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function api(path, opts) {
    const r = await fetch(API + path, opts || {});
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function loadApp() {
    const q = state.tag ? "?tag=" + encodeURIComponent(state.tag) : "";
    state.app = await api("/app" + q);
  }

  function render() {
    const a = state.app;
    const root = document.getElementById("root");
    if (!a) {
      root.className = "boot";
      root.textContent = "Loading...";
      return;
    }
    root.className = "app";
    const bot = a.bot || {};
    const score = a.score || {};
    const tagButtons = (a.all_tags || [])
      .map(function (t) {
        const active = state.tag === t ? " active" : "";
        return '<button type="button" class="tag-btn' + active + '" data-tag="' + esc(t) + '">' + esc(t) + "</button>";
      })
      .join("");
    const list = listForTab(a);
    root.innerHTML =
      '<header class="top">' +
      '<div class="badges"><span class="b-paper">PAPER ONLY</span><span class="b-lock">LIVE LOCKED</span></div>' +
      "<h1 style=\"font-size:1.05rem;margin:0.5rem 0 0\">Paper bot</h1>" +
      '<div class="score">' +
      "<span>Open " + esc(score.open_positions) + "</span>" +
      "<span>W " + esc(score.wins) + "</span>" +
      "<span>L " + esc(score.losses) + "</span>" +
      "<span>PnL " + esc(score.total_realized_pnl) + "</span>" +
      "</div>" +
      '<div class="toolbar">' +
      '<button type="button" id="btnRun"' + (state.busy ? " disabled" : "") + ">Run once</button>" +
      '<button type="button" class="secondary" id="btnPause"' + (bot.paused ? " disabled" : "") + ">Pause loop</button>" +
      '<button type="button" class="secondary" id="btnResume"' + (!bot.paused ? " disabled" : "") + ">Resume loop</button>" +
      "</div>" +
      '<div class="status" id="statusLine">' +
      (bot.paused ? "Auto loop paused." : "Auto loop running every " + esc(bot.interval_seconds) + "s.") +
      "</div>" +
      "</header>" +
      '<div class="tags"><button type="button" class="tag-btn' + (!state.tag ? " active" : "") + '" data-tag="">All</button>' +
      tagButtons +
      "</div>" +
      '<div class="main">' +
      '<nav class="tabs">' +
      tabBtn("decisions", "Calls") +
      tabBtn("positions", "Positions") +
      tabBtn("lessons", "Lessons") +
      "</nav>" +
      '<div class="list" id="listPanel">' +
      list +
      "</div>" +
      '<div class="detail" id="detailPanel">' +
      renderDetail() +
      "</div>" +
      "</div>";

    bindUi();
  }

  function tabBtn(id, label) {
    return '<button type="button" data-tab="' + id + '"' + (state.tab === id ? ' class="active"' : "") + ">" + label + "</button>";
  }

  function listForTab(a) {
    let rows = [];
    if (state.tab === "decisions") rows = a.decisions || [];
    else if (state.tab === "positions") rows = a.positions || [];
    else rows = a.lessons || [];
    if (!rows.length) return '<p class="muted" style="padding:0.75rem">Nothing here yet.</p>';
    return rows
      .map(function (row) {
        const id = row.id;
        const sel = state.selected && state.selected.type === state.tab && state.selected.id === id ? " selected" : "";
        let title = row.market_title || row.lesson_id || row.call || "";
        let sub = row.call ? row.call + " · #" + row.id : row.status || row.validation_status || "";
        if (state.tab === "lessons") sub = (row.market_topic || "") + " · #" + row.id;
        return (
          '<div class="list-item' +
          sel +
          '" data-pick="' +
          esc(state.tab) +
          ":" +
          id +
          '"><strong>' +
          esc(title.slice(0, 48)) +
          "</strong><div class=\"sub\">" +
          esc(sub) +
          "</div></div>"
        );
      })
      .join("");
  }

  function renderDetail() {
    if (!state.detail) return '<p class="muted">Select an item to inspect server data.</p>';
    const d = state.detail;
    return "<h2>Detail</h2><pre>" + esc(JSON.stringify(d, null, 2)) + "</pre>";
  }

  function bindUi() {
    document.querySelectorAll("[data-tab]").forEach(function (btn) {
      btn.onclick = function () {
        state.tab = btn.getAttribute("data-tab");
        state.selected = null;
        state.detail = null;
        render();
      };
    });
    document.querySelectorAll(".tag-btn").forEach(function (btn) {
      btn.onclick = async function () {
        const t = btn.getAttribute("data-tag");
        state.tag = t || null;
        await refresh();
      };
    });
    document.querySelectorAll("[data-pick]").forEach(function (el) {
      el.onclick = async function () {
        const parts = el.getAttribute("data-pick").split(":");
        state.selected = { type: parts[0], id: parseInt(parts[1], 10) };
        await loadDetail();
        render();
      };
    });
    const run = document.getElementById("btnRun");
    if (run) run.onclick = function () {
      runOnce();
    };
    const pause = document.getElementById("btnPause");
    if (pause) pause.onclick = function () {
      botCtl("/bot/pause");
    };
    const resume = document.getElementById("btnResume");
    if (resume) resume.onclick = function () {
      botCtl("/bot/resume");
    };
  }

  async function loadDetail() {
    if (!state.selected) return;
    const s = state.selected;
    let path = "";
    if (s.type === "decisions") path = "/decisions/" + s.id;
    else if (s.type === "positions") path = "/positions/" + s.id;
    else path = "/lessons/" + s.id;
    state.detail = await api(path);
  }

  async function refresh() {
    await loadApp();
    render();
  }

  async function runOnce() {
    state.busy = true;
    render();
    setStatus("Running paper bot tick on server...");
    try {
      const res = await api("/bot/run-once", { method: "POST" });
      state.app = res.app;
      if (res.call) {
        state.selected = { type: "decisions", id: res.call.id };
        state.detail = res.call;
        if (res.position) {
          state.tab = "positions";
          state.selected = { type: "positions", id: res.position.id };
          state.detail = await api("/positions/" + res.position.id);
        }
      }
      setStatus("Stored call #" + (res.call && res.call.id) + " from server.");
    } catch (e) {
      setStatus("Run failed.");
    }
    state.busy = false;
    render();
  }

  async function botCtl(path) {
    setStatus("Updating bot state...");
    try {
      const res = await api(path, { method: "POST" });
      state.app = res.app;
      setStatus(path.indexOf("pause") >= 0 ? "Loop paused." : "Loop resumed.");
    } catch (e) {
      setStatus("Request failed.");
    }
    render();
  }

  function setStatus(msg) {
    const el = document.getElementById("statusLine");
    if (el) el.textContent = msg;
  }

  loadApp()
    .then(function () {
      render();
    })
    .catch(function () {
      document.getElementById("root").textContent = "Could not reach paper API.";
    });
})();
