const state = {
  traces: [],
  selected: null,
};

const elements = {
  file: document.querySelector("#result-file"),
  count: document.querySelector("#trace-count"),
  list: document.querySelector("#trace-list"),
  empty: document.querySelector("#empty-state"),
  view: document.querySelector("#trace-view"),
  error: document.querySelector("#error-state"),
  status: document.querySelector("#trace-status"),
  provider: document.querySelector("#trace-provider"),
  task: document.querySelector("#trace-task"),
  traceId: document.querySelector("#trace-id"),
  model: document.querySelector("#trace-model"),
  started: document.querySelector("#trace-started"),
  stepCount: document.querySelector("#trace-steps-count"),
  steps: document.querySelector("#steps"),
};

elements.file.addEventListener("change", async () => {
  const file = elements.file.files?.[0];
  if (!file) return;
  try {
    state.traces = extractTraces(await file.text());
    if (!state.traces.length) throw new Error("No version 1 solver traces were found.");
    state.selected = state.traces[0];
    elements.error.hidden = true;
    elements.empty.hidden = true;
    render();
  } catch (error) {
    state.traces = [];
    state.selected = null;
    elements.view.hidden = true;
    elements.empty.hidden = true;
    elements.error.hidden = false;
    elements.error.textContent = error instanceof Error ? error.message : String(error);
    renderList();
  }
});

function extractTraces(text) {
  const payloads = [];
  try {
    payloads.push(JSON.parse(text));
  } catch {
    for (const line of text.split("\n")) {
      if (line.trim()) payloads.push(JSON.parse(line));
    }
  }
  const rows = payloads.flatMap((payload) =>
    Array.isArray(payload?.results) ? payload.results : [payload],
  );
  return rows
    .map((row) => row?.solver_trace)
    .filter(
      (trace) =>
        trace?.schema_version === 1 &&
        typeof trace.trace_id === "string" &&
        Array.isArray(trace.steps),
    )
    .sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)));
}

function render() {
  renderList();
  renderTrace();
}

function renderList() {
  elements.count.textContent = state.traces.length;
  elements.list.replaceChildren(
    ...state.traces.map((trace) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `trace-item${trace === state.selected ? " active" : ""}`;
      button.append(
        row(
          badge(trace.status),
          text("span", "step-count", `${trace.step_count} step${trace.step_count === 1 ? "" : "s"}`),
        ),
        text("strong", "", trace.task_id),
        text("span", "model", trace.model || trace.solver),
        text("time", "", formatTimestamp(trace.started_at)),
      );
      button.addEventListener("click", () => {
        state.selected = trace;
        render();
      });
      return button;
    }),
  );
}

function renderTrace() {
  const trace = state.selected;
  elements.view.hidden = !trace;
  if (!trace) return;
  elements.status.textContent = trace.status;
  elements.status.className = `status ${trace.status}`;
  elements.provider.textContent = trace.provider;
  elements.task.textContent = trace.task_id;
  elements.traceId.textContent = trace.trace_id;
  elements.model.textContent = trace.model || trace.solver;
  elements.started.textContent = formatTimestamp(trace.started_at);
  elements.stepCount.textContent = trace.step_count;
  elements.steps.replaceChildren(...trace.steps.map(stepElement));
}

function stepElement(step) {
  const section = document.createElement("section");
  section.className = "step";
  const heading = document.createElement("header");
  heading.append(
    text("span", "step-index", String(step.index)),
    text("h2", "", `Step ${step.index}`),
    badge(step.status),
    text("time", "", formatTimestamp(step.started_at)),
  );
  section.append(
    heading,
    block("Prompt", step.request?.prompt),
    block("Model response", step.response?.content),
    block("Shell action", step.action?.command, "code"),
    outputBlock("Execution", step.execution),
    outputBlock("Verification", step.verification),
  );
  return section;
}

function outputBlock(label, output) {
  if (!output) return block(label, "");
  const metadata = [
    `exit ${output.return_code}`,
    `${Number(output.duration_seconds || 0).toFixed(2)}s`,
    output.timed_out ? "timed out" : "",
  ]
    .filter(Boolean)
    .join(" | ");
  const body = [output.stdout, output.stderr && `stderr:\n${output.stderr}`]
    .filter(Boolean)
    .join("\n\n");
  return block(`${label} | ${metadata}`, body || "No output");
}

function block(label, value, className = "") {
  const wrapper = document.createElement("div");
  wrapper.className = "block";
  if (!value) {
    wrapper.hidden = true;
    return wrapper;
  }
  const pre = document.createElement("pre");
  pre.className = className;
  pre.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  wrapper.append(text("div", "label", label), pre);
  return wrapper;
}

function badge(status) {
  return text("span", `status ${status || ""}`, status || "unknown");
}

function row(...children) {
  const element = document.createElement("span");
  element.className = "item-row";
  element.append(...children);
  return element;
}

function text(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value || "";
  return element;
}

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value || "") : date.toLocaleString();
}
