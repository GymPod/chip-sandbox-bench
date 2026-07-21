import { ConvexClient } from "convex/browser";
import { api } from "../convex/_generated/api";

const convexUrl = import.meta.env.VITE_CONVEX_URL;
const convex = convexUrl ? new ConvexClient(convexUrl) : null;

const state = {
  tasks: [],
  task: null,
  tab: "overview",
  file: null,
  content: "",
  requestId: 0,
};

const elements = {
  loading: document.querySelector("#loading-state"),
  error: document.querySelector("#error-state"),
  errorMessage: document.querySelector("#error-message"),
  taskView: document.querySelector("#task-view"),
  taskList: document.querySelector("#task-list"),
  noResults: document.querySelector("#no-results"),
  search: document.querySelector("#task-search"),
  filter: document.querySelector("#discipline-filter"),
  visibleCount: document.querySelector("#visible-count"),
  taskTotal: document.querySelector("#task-total"),
  fileTotal: document.querySelector("#file-total"),
  discipline: document.querySelector("#task-discipline"),
  benchmark: document.querySelector("#task-benchmark"),
  title: document.querySelector("#task-title"),
  taskId: document.querySelector("#task-id"),
  tools: document.querySelector("#tool-list"),
  prompt: document.querySelector("#task-prompt"),
  instruction: document.querySelector("#task-instruction"),
  sourceRepo: document.querySelector("#source-repo"),
  sourceCommit: document.querySelector("#source-commit"),
  sourcePaths: document.querySelector("#source-paths"),
  tabs: document.querySelector("#tabs"),
  overview: document.querySelector("#overview-panel"),
  filePanel: document.querySelector("#file-panel"),
  fileList: document.querySelector("#file-list"),
  fileLanguage: document.querySelector("#file-language"),
  filePath: document.querySelector("#file-path"),
  codeFrame: document.querySelector("#code-frame"),
  codeContent: document.querySelector("#code-content"),
  copyButton: document.querySelector("#copy-button"),
  copyLabel: document.querySelector("#copy-label"),
  drawer: document.querySelector("#task-rail"),
  scrim: document.querySelector("#drawer-scrim"),
  drawerToggle: document.querySelector("#task-drawer-toggle"),
};

function displayTitle(taskId) {
  const prefixes = [
    "arch-microarch-",
    "architecture-modeling-",
    "rtl-design-",
    "software-",
    "verification-",
  ];
  const shortId = prefixes.reduce(
    (value, prefix) => (value.startsWith(prefix) ? value.slice(prefix.length) : value),
    taskId,
  );
  return shortId
    .split("-")
    .map((word) => {
      const labels = {
        archgym: "ArchGym",
        bitcnt: "Bit Count",
        champsim: "ChampSim",
        crc32: "CRC32",
        mcy: "MCY",
        opentitan: "OpenTitan",
        riscv: "RISC-V",
        rtl: "RTL",
        rtllm: "RTLLM",
        systemc: "SystemC",
        verilogeval: "VerilogEval",
      };
      return labels[word] || word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

function plural(count, label) {
  return `${count} ${label}${count === 1 ? "" : "s"}`;
}

function route() {
  const value = window.location.hash.replace(/^#\/?/, "");
  const [taskId, tab, ...fileParts] = value.split("/").map(decodeURIComponent);
  return { taskId, tab, file: fileParts.join("/") };
}

function setRoute(taskId, tab = "overview", file = "", replace = false) {
  const parts = [taskId, tab];
  if (file) parts.push(...file.split("/"));
  const hash = `#/${parts.map(encodeURIComponent).join("/")}`;
  if (replace) {
    history.replaceState(null, "", hash);
    applyRoute();
  } else if (window.location.hash === hash) {
    applyRoute();
  } else {
    window.location.hash = hash;
  }
}

function groupFiles(task, group) {
  return task.files.filter((file) => file.group === group);
}

function renderTaskList() {
  const query = elements.search.value.trim().toLowerCase();
  const discipline = elements.filter.value;
  const visible = state.tasks.filter((task) => {
    const haystack = [task.task_id, task.discipline, task.benchmark, task.prompt, ...(task.tools || [])].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!discipline || task.discipline === discipline);
  });

  const groups = new Map();
  for (const task of visible) {
    if (!groups.has(task.discipline)) groups.set(task.discipline, []);
    groups.get(task.discipline).push(task);
  }

  elements.taskList.replaceChildren(
    ...[...groups].map(([groupDiscipline, tasks]) => {
      const group = document.createElement("section");
      group.className = "task-group";
      group.dataset.discipline = disciplineKey(groupDiscipline);
      group.setAttribute("aria-label", groupDiscipline);

      const heading = document.createElement("div");
      heading.className = "task-group-heading";
      heading.append(textElement("span", "discipline-dot", ""), document.createTextNode(groupDiscipline));
      group.append(heading);

      for (const task of tasks) {
        const button = document.createElement("button");
        button.className = `task-item${task === state.task ? " active" : ""}`;
        button.type = "button";
        button.dataset.taskId = task.task_id;
        button.innerHTML = `
          <span class="task-item-title">${escapeHtml(displayTitle(task.task_id))}</span>
          <span class="task-item-meta">
            <span class="task-item-benchmark">${escapeHtml(task.benchmark)}</span>
            <span class="task-item-files">${task.file_count}</span>
          </span>`;
        button.addEventListener("click", () => {
          setRoute(task.task_id);
          closeDrawer();
        });
        group.append(button);
      }
      return group;
    }),
  );
  elements.visibleCount.textContent = visible.length;
  elements.noResults.hidden = visible.length !== 0;
}

function renderTask() {
  const task = state.task;
  document.title = `${displayTitle(task.task_id)} | Chip Task Viewer`;
  elements.discipline.textContent = task.discipline;
  elements.benchmark.textContent = task.benchmark;
  elements.title.textContent = displayTitle(task.task_id);
  elements.taskId.textContent = task.task_id;
  elements.prompt.textContent = task.prompt;
  elements.instruction.textContent = task.instruction;
  elements.sourceRepo.textContent = task.source.repo;
  elements.sourceCommit.textContent = task.source.commit;
  elements.tools.replaceChildren(...(task.tools || []).map((tool) => textElement("span", "tool-pill", tool)));
  elements.sourcePaths.replaceChildren(...(task.source.paths || []).map((path) => textElement("div", "source-path", path)));

  for (const group of ["workspace", "tests", "solution"]) {
    document.querySelector(`[data-count="${group}"]`).textContent = groupFiles(task, group).length;
  }

  renderTaskList();
}

function renderTab() {
  for (const tab of elements.tabs.querySelectorAll(".tab")) {
    const active = tab.dataset.tab === state.tab;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  const overview = state.tab === "overview";
  elements.overview.hidden = !overview;
  elements.filePanel.hidden = overview;
  if (!overview) renderFiles();
}

function renderFiles() {
  const files = groupFiles(state.task, state.tab);
  elements.fileList.replaceChildren(
    ...files.map((file) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `file-item${file.path === state.file?.path ? " active" : ""}`;
      button.title = file.path;
      button.innerHTML = `<span class="file-glyph">${escapeHtml(extension(file.name))}</span><span class="file-name">${escapeHtml(file.name)}</span>`;
      button.addEventListener("click", () => setRoute(state.task.task_id, state.tab, file.path));
      return button;
    }),
  );
  if (state.file) {
    elements.fileLanguage.textContent = state.file.language;
    elements.filePath.textContent = state.file.path;
  }
}

async function loadFile(file) {
  const requestId = ++state.requestId;
  state.file = file;
  state.content = "";
  renderFiles();
  renderCodeMessage("Loading...");
  elements.copyButton.disabled = true;

  try {
    if (!convex) throw new Error("VITE_CONVEX_URL is not configured.");
    const payload = await convex.query(api.tasks.readFile, {
      taskId: state.task.task_id,
      path: file.path,
    });
    if (!payload) throw new Error(`Could not load ${file.path}`);
    if (requestId !== state.requestId) return;
    state.content = payload.content;
    renderHighlightedCode(payload.content, file);
    elements.copyButton.disabled = false;
  } catch (error) {
    if (requestId !== state.requestId) return;
    renderCodeMessage(error.message);
  }
}

function renderHighlightedCode(content, file) {
  const language = syntaxLanguage(file.language);
  elements.codeFrame.querySelector(".line-numbers-rows")?.remove();
  elements.codeFrame.className = `code-lines line-numbers language-${language}`;
  elements.codeContent.className = `language-${language}`;
  elements.codeContent.textContent = content;
  Prism.highlightElement(elements.codeContent);
}

function renderCodeMessage(message) {
  elements.codeFrame.querySelector(".line-numbers-rows")?.remove();
  elements.codeFrame.className = "code-lines";
  elements.codeContent.className = "";
  elements.codeContent.textContent = message;
}

function syntaxLanguage(language) {
  const languages = {
    C: "c",
    "C++": "cpp",
    "C/C++ Header": "cpp",
    JSON: "json",
    Markdown: "markdown",
    Python: "python",
    Shell: "bash",
    SystemVerilog: "verilog",
    Verilog: "verilog",
    YAML: "yaml",
  };
  return languages[language] || "plain";
}

function applyRoute() {
  if (!state.tasks.length) return;
  const requested = route();
  const task = state.tasks.find((candidate) => candidate.task_id === requested.taskId) || state.tasks[0];
  const tabs = ["overview", "workspace", "tests", "solution"];
  let tab = tabs.includes(requested.tab) ? requested.tab : "overview";
  let file = null;

  if (tab !== "overview") {
    const files = groupFiles(task, tab);
    file = files.find((candidate) => candidate.path === requested.file) || files[0] || null;
    if (!file) tab = "overview";
  }

  const expectedFile = file?.path || "";
  if (task.task_id !== requested.taskId || tab !== requested.tab || expectedFile !== requested.file) {
    setRoute(task.task_id, tab, expectedFile, true);
    return;
  }

  const taskChanged = state.task !== task;
  const fileChanged = state.file?.path !== file?.path || taskChanged;
  state.task = task;
  state.tab = tab;
  state.file = file;
  if (taskChanged) renderTask();
  renderTab();
  if (file && fileChanged) loadFile(file);
  window.scrollTo({ top: 0, behavior: "instant" });
}

async function loadTasks() {
  elements.loading.hidden = false;
  elements.error.hidden = true;
  elements.taskView.hidden = true;
  try {
    if (!convex) throw new Error("VITE_CONVEX_URL is not configured.");
    const tasks = await convex.query(api.tasks.list);
    if (!tasks.length) throw new Error("No tasks were found in Convex.");
    state.tasks = tasks;

    const disciplines = [...new Set(state.tasks.map((task) => task.discipline))].sort();
    elements.filter.replaceChildren(
      new Option("All disciplines", ""),
      ...disciplines.map((discipline) => new Option(discipline, discipline)),
    );
    const fileCount = state.tasks.reduce((total, task) => total + task.file_count, 0);
    elements.taskTotal.textContent = plural(state.tasks.length, "task");
    elements.fileTotal.textContent = plural(fileCount, "file");
    elements.loading.hidden = true;
    elements.taskView.hidden = false;
    renderTaskList();
    applyRoute();
  } catch (error) {
    elements.loading.hidden = true;
    elements.error.hidden = false;
    elements.errorMessage.textContent = error.message;
  }
}

function textElement(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value;
  return element;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function extension(name) {
  const suffix = name.split(".").pop();
  return suffix === name ? "txt" : suffix.slice(0, 4);
}

function disciplineKey(discipline) {
  if (discipline.includes("Microarchitecture")) return "microarchitecture";
  if (discipline === "Architecture Modeling") return "modeling";
  if (discipline === "RTL Design") return "rtl";
  if (discipline === "Software Development") return "software";
  return "verification";
}

function openDrawer() {
  elements.drawer.classList.add("open");
  elements.scrim.classList.add("open");
  elements.drawerToggle.setAttribute("aria-expanded", "true");
}

function closeDrawer() {
  elements.drawer.classList.remove("open");
  elements.scrim.classList.remove("open");
  elements.drawerToggle.setAttribute("aria-expanded", "false");
}

elements.search.addEventListener("input", renderTaskList);
elements.filter.addEventListener("change", renderTaskList);
elements.tabs.addEventListener("click", (event) => {
  const tab = event.target.closest(".tab");
  if (tab) setRoute(state.task.task_id, tab.dataset.tab);
});
elements.copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(state.content);
  elements.copyLabel.textContent = "Copied";
  window.setTimeout(() => (elements.copyLabel.textContent = "Copy"), 1200);
});
elements.drawerToggle.addEventListener("click", () => {
  elements.drawer.classList.contains("open") ? closeDrawer() : openDrawer();
});
elements.scrim.addEventListener("click", closeDrawer);
document.querySelector("#retry-button").addEventListener("click", loadTasks);
window.addEventListener("hashchange", applyRoute);
window.addEventListener("keydown", (event) => {
  if (event.key === "/" && document.activeElement !== elements.search) {
    event.preventDefault();
    elements.search.focus();
  }
  if (event.key === "Escape") closeDrawer();
});

loadTasks();
