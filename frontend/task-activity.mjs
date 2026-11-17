import { iconButton } from "./icons.mjs";
const statuses = { backlog: "Backlog", in_progress: "In progress", to_review: "To review", done: "Done" };
const labels = { title: "Title", description: "Description", status: "Status", milestone: "Milestone", milestone_id: "Assignment", archived: "Archive", position: "Order" };
const node = (tag, text, className) => {
  const e = document.createElement(tag);
  if (text !== void 0) e.textContent = text;
  if (className) e.className = className;
  return e;
};
function value(field, v) {
  if (v === null || v === "") return "None";
  if (field === "status") return statuses[v] || v;
  if (field === "milestone_id") return "#C" + String(v).padStart(2, "0");
  if (field === "milestone") return v ? "Milestone" : "Task";
  if (field === "archived") return v ? "Archived" : "Active";
  return String(v);
}
function mountTaskActivity(dialog, id, { api, state, write, getRevision, error }) {
  const drafts = state.commentDrafts ??= /* @__PURE__ */ new Map();
  let revision = -1, limit = 100, pending = null, disposed = false, hasOlder = false;
  const section = node("section", void 0, "task-activity"), heading = node("h3", "Comments & activity"), list = node("div", void 0, "task-activity-list"), status = node("p", void 0, "task-activity-error"), older = node("button", "Load earlier activity"), form = node("form", void 0, "task-comment-form"), label = node("label", "Comment"), input = node("textarea"), send = node("button", "Comment");
  section.setAttribute("aria-label", "Comments and activity");
  status.setAttribute("role", "status");
  older.type = "button";
  older.hidden = true;
  older.onclick = () => {
    limit = Math.min(1e3, limit + 100);
    refresh(true);
  };
  input.id = "task-comment-" + id;
  label.htmlFor = input.id;
  input.placeholder = "Write a comment…";
  input.maxLength = 1e5;
  input.value = drafts.get(id) || "";
  input.oninput = () => drafts.set(id, input.value);
  send.type = "submit";
  form.append(label, input, send);
  section.append(heading, older, list, status, form);
  dialog.append(section);
  function render(entries) {
    const ids = new Set(entries.map((e) => String(e.id)));
    for (const child of [...list.children]) if (!ids.has(child.dataset.entry)) child.remove();
    for (const entry of entries) {
      let item = [...list.children].find((e) => e.dataset.entry === String(entry.id));
      if (item) continue;
      item = node("article", void 0, "task-activity-entry " + (entry.kind === "update" ? "task-update" : "task-comment"));
      item.dataset.entry = entry.id;
      const meta = node("div", void 0, "task-activity-meta"), author = node("strong", entry.author), time = node("time");
      time.dateTime = entry.created_at.replace(" ", "T") + "Z";
      time.textContent = new Date(time.dateTime).toLocaleString();
      const remove = iconButton(entry.kind === "update" ? "Delete update" : "Delete comment", "trash", async () => {
        remove.disabled = true;
        if (await write({ action: "delete_activity", id, entry_id: entry.id })) await refresh(true);
        else {
          status.textContent = error();
          remove.disabled = false;
        }
      });
      if (entry.kind === "update") meta.append(node("span", "Update", "task-activity-kind"));
      meta.append(author, time, remove);
      item.append(meta);
      if (entry.kind === "comment") item.append(node("p", entry.body));
      else {
        const updates = node("div", void 0, "task-update-fields");
        if (entry.body) updates.append(node("p", entry.body));
        else for (const [field, change] of Object.entries(entry.changes)) {
          if (field === "description") {
            const details = node("details"), summary = node("summary", "Description changed");
            details.append(summary, node("p", "Before: " + value(field, change.from)), node("p", "After: " + value(field, change.to)));
            updates.append(details);
          } else updates.append(node("p", (labels[field] || field) + ": " + value(field, change.from) + " → " + value(field, change.to)));
        }
        item.append(updates);
      }
      const next = [...list.children].find((e) => Number(e.dataset.entry) > entry.id);
      list.insertBefore(item, next || null);
    }
    if (!entries.length && !list.children.length) list.textContent = "";
  }
  async function refresh(force = false) {
    if (disposed) return;
    if (pending) {
      await pending;
      if (force && !disposed) return refresh(true);
      return;
    }
    if (!force && revision === getRevision()) return;
    const params = new URLSearchParams({ limit });
    if (!force && revision >= 0) params.set("revision", revision);
    pending = (async () => {
      try {
        const data = await api(`tasks/${id}/activity?${params}`);
        if (disposed || !data) return;
        render(data.entries);
        revision = data.revision;
        hasOlder = data.has_older;
        older.hidden = !hasOlder || limit >= 1e3;
        status.textContent = hasOlder && limit >= 1e3 ? "Showing the latest 1,000 entries. Earlier activity is available through the CLI." : "";
      } catch (e) {
        if (!disposed) status.textContent = e.message;
      } finally {
        pending = null;
      }
    })();
    await pending;
  }
  form.onsubmit = async (event) => {
    event.preventDefault();
    if (!input.value.trim()) return;
    const body = input.value;
    send.disabled = true;
    status.textContent = "";
    if (await write({ action: "comment", id, body })) {
      if (input.value === body) {
        input.value = "";
        drafts.delete(id);
      }
      await refresh(true);
    } else status.textContent = error();
    send.disabled = false;
  };
  input.onkeydown = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      form.requestSubmit();
    }
  };
  refresh();
  return { refresh, dispose: () => {
    disposed = true;
  } };
}
export {
  mountTaskActivity
};
