import { iconButton } from "./icons.mjs";
import { linkFileReferences } from "./file-references.mjs";
import { renderMarkdown } from "./markdown-render.mjs";
const activityTime = new Intl.DateTimeFormat(undefined, {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"});
const statuses = { backlog: "Backlog", in_progress: "In progress", to_review: "To review", done: "Done" };
const labels = { title: "Title", description: "Description", status: "Status", milestone: "Milestone", milestone_id: "Assignment", milestone_number:"Milestone number", archived: "Archive", position: "Order", parent_id:"Parent", outline_position:"Checklist order" };
const node = (tag, text, className) => {
  const e = document.createElement(tag);
  if (text !== void 0) e.textContent = text;
  if (className) e.className = className;
  return e;
};
function value(field, v) {
  if (v === null || v === "") return "None";
  if (field === "status") return statuses[v] || v;
  if (field === "milestone_number") return "#M"+v;
  if (field === "milestone_id" || field === "parent_id") return "#C" + String(v).padStart(2, "0");
  if (field === "milestone") return v ? "Milestone" : "Task";
  if (field === "archived") return v ? "Archived" : "Active";
  return String(v);
}
function mountTaskActivity(dialog, id, { api, download, composers, write, getRevision, error }) {
  const previews = new Map();
  let revision = -1, limit = 100, pending = null, disposed = false, hasOlder = false;
  const section = node("section", void 0, "task-activity"), heading = node("h3", "Comments & activity"), list = node("div", void 0, "task-activity-list"), status = node("p", void 0, "task-activity-error"), older = node("button", "Load earlier activity"), form = node("form", void 0, "task-comment-form"), send = node("button", "Comment");
  section.setAttribute("aria-label", "Comments and activity");
  status.setAttribute("role", "status");
  older.type = "button";
  older.hidden = true;
  older.onclick = () => {
    limit = Math.min(1e3, limit + 100);
    refresh(true);
  };
  form.dataset.taskCard = id;
  form.append(document.getElementById('task-comment-composer').content.cloneNode(true));
  const input = form.querySelector('textarea');
  input.dataset.taskFileMentions = '';
  input.maxLength = 1e5;
  send.type = 'submit';
  form.insertBefore(send, form.querySelector('.pending-files'));
  composers.render(form);
  section.append(heading, older, list, status, form);
  dialog.append(section);
  function removePreviews(item) {
    for (const [image, url] of previews) if (item.contains(image)) {
      URL.revokeObjectURL(url);
      previews.delete(image);
    }
  }
  function renderAttachment(file) {
    const item = node('li');
    const save = node('button', file.name);
    save.type = 'button';
    save.title = 'Download ' + file.name;
    save.onclick = async () => {
      try {
        const url = URL.createObjectURL(await download(file));
        const link = node('a');
        link.href = url;
        link.download = file.name;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (problem) {
        status.textContent = problem.message;
      }
    };
    item.append(save);
    if (['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.media_type)) {
      const preview = node('details');
      const image = node('img');
      image.alt = file.name;
      preview.append(node('summary', 'Preview ' + file.name), image);
      preview.ontoggle = async () => {
        if (!preview.open || image.hasAttribute('src') || preview.dataset.loading) return;
        preview.dataset.loading = 'true';
        try {
          const blob = await download(file);
          if (disposed || !preview.isConnected || image.hasAttribute('src')) return;
          const url = URL.createObjectURL(blob);
          previews.set(image, url);
          image.src = url;
        } catch (problem) {
          if (!disposed) status.textContent = problem.message;
        } finally {
          delete preview.dataset.loading;
        }
      };
      item.append(preview);
    }
    return item;
  }
  function render(entries) {
    const ids = new Set(entries.map((e) => String(e.id)));
    for (const child of [...list.children]) if (!ids.has(child.dataset.entry)) {
      removePreviews(child);
      child.remove();
    }
    for (const entry of entries) {
      let item = [...list.children].find((e) => e.dataset.entry === String(entry.id));
      if (item) continue;
      item = node("article", void 0, "task-activity-entry " + (entry.kind === "update" ? "task-update" : "task-comment"));
      item.dataset.entry = entry.id;
      const meta = node("div", void 0, "task-activity-meta"), author = node("strong", entry.author), time = node("time");
      time.dateTime = entry.created_at.replace(" ", "T") + "Z";
      const date=new Date(time.dateTime);
      time.title=date.toLocaleString();
      time.textContent = Number.isFinite(date.getTime()) ? activityTime.format(date) : entry.created_at;
      author.title=entry.author;
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
      if (entry.kind === "comment") {
        if (entry.body) {
          const body = node("div", undefined, "comment-markdown task-markdown");
          renderMarkdown(body, entry.body, linkFileReferences);
          item.append(body);
        }
        if (entry.attachments?.length) {
          const files = node('ul', undefined, 'task-comment-files');
          files.append(...entry.attachments.map(renderAttachment));
          item.append(files);
        }
      }
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
    const files = composers.files(form);
    if (composers.isSending(form) || (!input.value.trim() && !files.length)) return;
    const body = input.value;
    composers.setSending(form, true);
    composers.status(form, 'Sending…');
    try {
      if (await write({action: 'comment', id, body}, files)) {
        composers.complete(form, body);
        composers.status(form, '');
        await refresh(true);
      } else composers.status(form, error(), true);
    } finally {
      composers.setSending(form, false);
    }
  };
  refresh();
  return { refresh, dispose: () => {
    disposed = true;
    removePreviews(section);
  } };
}
export {
  mountTaskActivity
};
