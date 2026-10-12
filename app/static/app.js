/* BOTLAB Auditor - UI. Vanilla JS, no build step, no dependencies. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var picked = null;           // demo name, when a demo button is armed
  var es = null;               // the open EventSource
  var gatesSeen = null;

  /* ---------------------------------------------------------------- theme */
  var root = document.documentElement;
  try {
    var saved = localStorage.getItem("auditor-theme");
    if (saved) { root.setAttribute("data-theme", saved); }
  } catch (e) { /* private mode: stay on the system theme */ }
  $("theme").addEventListener("click", function () {
    var now = root.getAttribute("data-theme");
    var dark = now === "dark" || (now !== "light" &&
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    var next = dark ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("auditor-theme", next); } catch (e) { /* ignore */ }
  });

  /* ------------------------------------------------------------- runtime */
  fetch("/api/health").then(function (r) { return r.json(); }).then(function (h) {
    $("runtime").textContent = "Sandbox backend: " + h.sandbox_backend +
      "  -  Reasoning: " + (h.inference === "vultr-serverless"
        ? "Vultr Serverless Inference" : "deterministic offline planner (no inference key set)");
  }).catch(function () { $("runtime").textContent = ""; });

  /* --------------------------------------------------------------- demos */
  var DEMO_NAMES = ["honest", "overfit", "lookahead", "malicious"];
  var box = $("demos");
  DEMO_NAMES.forEach(function (name) {
    fetch("/api/demo/" + name).then(function (r) { return r.json(); }).then(function (d) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "demo";
      b.setAttribute("aria-pressed", "false");
      b.dataset.name = name;
      b.dataset.trials = d.n_trials;
      b.innerHTML = "<b></b><span></span><em></em>";
      b.querySelector("b").textContent = d.title;
      b.querySelector("span").textContent = d.blurb;
      b.querySelector("em").textContent = "expected: " + d.expected;
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(box.querySelectorAll(".demo"), function (o) {
          o.setAttribute("aria-pressed", String(o === b));
        });
        picked = name;
        $("trials").value = d.n_trials;
        $("strategy").value = "";
        $("picked").textContent = "demo armed: " + d.title;
        var src = $("demosrc");
        src.hidden = false;
        src.textContent = d.source;
      });
      box.appendChild(b);
    }).catch(function () { /* a missing demo just does not appear */ });
  });

  $("strategy").addEventListener("change", function () {
    if (this.files && this.files.length) {
      picked = null;
      Array.prototype.forEach.call(box.querySelectorAll(".demo"), function (o) {
        o.setAttribute("aria-pressed", "false");
      });
      $("picked").textContent = "file selected: " + this.files[0].name;
      $("demosrc").hidden = true;
    }
  });

  /* ---------------------------------------------------------- the run */
  $("run").addEventListener("click", function () {
    var fd = new FormData();
    var sf = $("strategy").files, tf = $("tradelog").files;
    if (sf && sf.length) { fd.append("strategy", sf[0]); }
    if (tf && tf.length) { fd.append("trade_log", tf[0]); }
    if (picked && !(sf && sf.length)) { fd.append("demo_name", picked); }
    fd.append("n_trials", $("trials").value || "1");

    if (!(sf && sf.length) && !(tf && tf.length) && !picked) {
      $("picked").textContent = "pick a strategy file, a trade log, or a demo first.";
      return;
    }
    reset();
    $("run").disabled = true;
    $("run").textContent = "Auditing...";

    fetch("/api/audit", { method: "POST", body: fd }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) { throw new Error(j.detail || ("HTTP " + r.status)); }
        return j;
      });
    }).then(function (j) {
      listen(j.stream);
    }).catch(function (err) {
      addTrace("message", "Could not start the audit", String(err.message || err));
      finish();
    });
  });

  function reset() {
    if (es) { es.close(); es = null; }
    gatesSeen = null;
    $("results").hidden = false;
    $("trace").innerHTML = "";
    $("events").innerHTML = "";
    $("sbempty").hidden = false;
    $("verdictcard").hidden = true;
    $("gatebody").innerHTML = "";
    $("gatereportwrap").hidden = true;
    $("voverride").hidden = true;
  }

  function finish() {
    $("run").disabled = false;
    $("run").textContent = "Run the audit";
  }

  function listen(url) {
    es = new EventSource(url);
    es.onmessage = function (m) {
      var ev;
      try { ev = JSON.parse(m.data); } catch (e) { return; }
      handle(ev);
      if (ev.type === "done") { es.close(); es = null; finish(); }
    };
    es.onerror = function () {
      if (es) { es.close(); es = null; }
      addTrace("message", "Connection lost", "The event stream closed before the audit finished.");
      finish();
    };
  }

  /* ----------------------------------------------------------- rendering */
  var TOOL_LABEL = {
    inspect_inputs: "Inspect the upload",
    run_strategy_in_sandbox: "Run the strategy in the sandbox",
    lookahead_audit: "Look-ahead audit (re-run on truncated history)",
    apply_costs: "Apply fees, slippage and funding",
    compute_stats: "Sharpe, PSR and Deflated Sharpe",
    run_gates: "Score the readiness gates",
    write_report: "Write the verdict"
  };

  /* Which containment rule refused an action. Mirrors sandbox/runner.py. */
  function ruleFor(name) {
    var n = String(name || "");
    if (/^socket\.|^urllib|^http\.client|^ftplib|^smtplib|^poplib|^imaplib|^telnetlib|^webbrowser/.test(n)) {
      return "Rule: no network. The sandbox container also runs with --network none.";
    }
    if (/^os\.(system|exec|spawn|posix_spawn|fork|forkpty|startfile|kill|killpg)|^subprocess|^pty\.spawn|^_winapi\./.test(n)) {
      return "Rule: no process spawning and no shell. The container drops all capabilities.";
    }
    if (/^ctypes\.|^cffi\./.test(n)) {
      return "Rule: no native code (ctypes / cffi), which would bypass the Python-level hook.";
    }
    if (/^gc\.|^object\.__delattr__|^sys\.remote_exec/.test(n)) {
      return "Rule: no interpreter introspection or patching.";
    }
    if (n === "import") {
      return "Rule: blocked module. ctypes, mmap, multiprocessing, pty and _winapi are refused at import.";
    }
    if (n === "open") {
      return "Rule: writes are confined to one scratch directory; the root filesystem is read-only.";
    }
    if (n === "wall_clock_timeout") {
      return "Rule: wall-clock watchdog. A strategy that never returns is killed.";
    }
    if (n === "lookahead re-run") {
      return "Same policy, enforced again on the second sandbox run. Each run is a fresh container.";
    }
    return "Rule: filesystem writes and deletes outside the scratch directory are refused.";
  }

  function addTrace(kind, title, body, cls) {
    var li = document.createElement("li");
    li.className = cls || "";
    var k = document.createElement("span");
    k.className = "k";
    k.textContent = kind;
    var t = document.createElement("span");
    t.className = "t";
    t.textContent = title;
    li.appendChild(k);
    li.appendChild(t);
    if (body) {
      var pre = document.createElement("pre");
      pre.textContent = body;
      li.appendChild(pre);
    }
    var ol = $("trace");
    ol.appendChild(li);
    ol.scrollTop = ol.scrollHeight;
    return li;
  }

  function addEvents(list) {
    if (!list || !list.length) { return; }
    $("sbempty").hidden = true;
    var ul = $("events");
    list.forEach(function (e) {
      var li = document.createElement("li");
      var badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "blocked";
      var ev = document.createElement("span");
      ev.className = "ev";
      ev.textContent = e.event || "unknown";
      var why = document.createElement("span");
      why.className = "why";
      why.textContent = e.detail || "";
      var rule = document.createElement("span");
      rule.className = "rule";
      rule.textContent = ruleFor(e.event);
      li.appendChild(badge);
      li.appendChild(ev);
      li.appendChild(why);
      li.appendChild(rule);
      ul.appendChild(li);
    });
    $("sbhint").textContent = ul.children.length +
      " unsafe action(s) refused. The host was never at risk and the audit carried on.";
  }

  function summarise(tool, r) {
    if (!r || typeof r !== "object") { return String(r); }
    var keep = {};
    Object.keys(r).forEach(function (k) {
      if (k === "blocked" || k === "gate_report") { return; }
      keep[k] = r[k];
    });
    return JSON.stringify(keep, null, 2);
  }

  function handle(ev) {
    if (ev.type === "plan") {
      addTrace("plan", "Audit plan", ev.text, "msg");
    } else if (ev.type === "message") {
      addTrace("note", ev.text || "", null, "msg");
    } else if (ev.type === "tool_call") {
      addTrace("tool call", TOOL_LABEL[ev.tool] || ev.tool, null, "tc");
    } else if (ev.type === "tool_result") {
      addTrace("result", TOOL_LABEL[ev.tool] || ev.tool, summarise(ev.tool, ev.result));
      if (ev.result && ev.result.blocked) { addEvents(ev.result.blocked); }
      if (ev.tool === "run_gates" && ev.result && ev.result.gates) {
        gatesSeen = ev.result.gates;
        renderGates(ev.result.gates);
      }
      if (ev.tool === "lookahead_audit" && ev.result && ev.result.checked === false &&
          ev.result.contained) {
        addEvents([{ event: "lookahead re-run",
                     detail: "the strategy was contained again while it was re-run on truncated " +
                             "history; the look-ahead check could not complete" }]);
      }
    } else if (ev.type === "done") {
      renderVerdict(ev.report);
    }
  }

  function renderGates(gates) {
    var body = $("gatebody");
    body.innerHTML = "";
    Object.keys(gates).forEach(function (g) {
      var row = document.createElement("tr");
      var a = document.createElement("td");
      a.textContent = g;
      var b = document.createElement("td");
      b.textContent = gates[g].pass ? "PASS" : "FAIL";
      b.className = gates[g].pass ? "pass" : "fail";
      var c = document.createElement("td");
      c.textContent = gates[g].why || "";
      row.appendChild(a);
      row.appendChild(b);
      row.appendChild(c);
      body.appendChild(row);
    });
  }

  function statusClass(s) {
    if (s === "READY_FOR_MICRO_LIVE") { return "ok"; }
    if (s === "WATCH") { return "warn"; }
    return "bad";
  }

  function renderVerdict(rep) {
    var card = $("verdictcard");
    card.hidden = false;
    if (!rep) {
      $("vstatus").textContent = "NO VERDICT";
      $("vstatus").className = "status bad";
      $("vtext").textContent = "The run ended without producing a verdict.";
      return;
    }
    var s = rep.status || "UNKNOWN";
    $("vstatus").textContent = s;
    $("vstatus").className = "status " + statusClass(s);
    var meta = [];
    if (rep.gate_status && rep.gate_status !== s && rep.gate_status !== "UNKNOWN") {
      meta.push("gate status would have been " + rep.gate_status);
    }
    meta.push(rep.sandbox_blocked_events + " sandbox block(s)");
    if (rep.gate_status === "UNKNOWN") { meta.push("no gate score: the code never produced trades"); }
    $("vmeta").textContent = meta.join("  -  ");
    if (rep.sandbox_blocked_events) {
      $("sbempty").hidden = true;
      $("sbhint").textContent = rep.sandbox_blocked_events +
        " unsafe action(s) refused in total. The host was never at risk and the audit carried on.";
    }
    $("vtext").textContent = rep.verdict || "";
    if (rep.override_reason) {
      $("voverride").hidden = false;
      $("voverride").textContent = "Veto: " + rep.override_reason;
    }
    var noGates = !$("gatebody").children.length;
    $("gatetable").hidden = noGates;
    $("gatehead").hidden = noGates;
    if (rep.gate_report && rep.gate_report !== "no gate report available") {
      $("gatereportwrap").hidden = false;
      $("gatereport").textContent = rep.gate_report;
    }
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}());
