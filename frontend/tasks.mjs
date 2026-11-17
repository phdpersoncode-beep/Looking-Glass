const columns = [["backlog", "\u25CC", "Backlog"], ["in_progress", "\u25D0", "In progress"], ["to_review", "\u25CE", "To review"], ["done", "\u2713", "Done"]];
function fuzzyCard(card, query) {
  let at = 0;
  const text = (card.title + " " + card.description).toLocaleLowerCase();
  for (const char of query.toLocaleLowerCase().trim()) {
    at = text.indexOf(char, at);
    if (at < 0) return false;
    at++;
  }
  return true;
}
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== void 0) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action, title = text) {
  const b = el("button", text);
  b.type = "button";
  b.title = title;
  b.setAttribute("aria-label", title);
  b.onclick = action;
  return b;
}
function mountTasks(host, state, api) {
  let board = { cards: [], revision: 0 }, disposed = false, busy = false, refreshing = false, dragged = null, editor = null;
  const drafts = state.drafts ??= new Map();
  const picked = new Set(), root = el("section", void 0, "task-board"), tools = el("div", void 0, "task-tools"), search = el("input"), filter = el("select"), archived = el("input"), bulk = el("div", void 0, "task-bulk"), lanes = el("div", void 0, "task-lanes"), notice = el("p", void 0, "task-notice");
  search.placeholder = "Search cards\u2026";
  search.setAttribute("aria-label", "Search cards");
  search.value = state.query || "";
  filter.setAttribute("aria-label", "Filter by milestone");
  archived.type = "checkbox";
  archived.checked = !!state.archived;
  const archiveLabel = el("label", "Show archive ");
  archiveLabel.append(archived);
  notice.setAttribute("role", "status");
  tools.append(search, filter, archiveLabel, button("+ Task", () => editNew("backlog"), "Create task"));
  const muted = el("input");
  muted.type = "checkbox";
  muted.checked = !!state.muted;
  const muteLabel = el("label", "Mute ");
  muteLabel.append(muted);
  muted.onchange = () => {
    state.muted = muted.checked;
    localStorage.setItem("looking-glass-task-muted", String(muted.checked));
  };
  if (state.muted === void 0) muted.checked = localStorage.getItem("looking-glass-task-muted") === "true";
  tools.append(muteLabel);
  root.append(tools, bulk, notice, lanes);
  host.append(root);
  function fail(error) {
    if (!disposed) notice.textContent = error.message;
  }
  function milestones(select, value = "", exclude = []) {
    select.replaceChildren(el("option", "No milestone"));
    select.firstChild.value = "";
    for (const card of board.cards.filter((c) => c.milestone && (!c.archived || c.id === Number(value)) && !exclude.includes(c.id))) {
      const option = el("option", "\u25C7 " + card.title + (card.archived ? " (archived)" : ""));
      option.value = card.id;
      select.append(option);
    }
    select.value = value;
  }
  function celebrate() {
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const burst = el("div", void 0, "task-confetti");
      for (let i = 0; i < 18; i++) {
        const bit = el("i");
        bit.style.setProperty("--x", `${(Math.random() - 0.5) * 260}px`);
        bit.style.setProperty("--y", `${30 + Math.random() * 100}px`);
        bit.style.setProperty("--r", `${Math.random() * 360}deg`);
        burst.append(bit);
      }
      root.append(burst);
      setTimeout(() => burst.remove(), 950);
    }
    if (!muted.checked) {
      try {
        const Audio = window.AudioContext || window.webkitAudioContext;
        const audio = new Audio(), osc = audio.createOscillator(), gain = audio.createGain();
        osc.connect(gain);
        gain.connect(audio.destination);
        osc.frequency.setValueAtTime(880, audio.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1320, audio.currentTime + 0.12);
        gain.gain.setValueAtTime(0.035, audio.currentTime);
        gain.gain.exponentialRampToValueAtTime(1e-4, audio.currentTime + 0.5);
        osc.start();
        osc.stop(audio.currentTime + 0.5);
        osc.onended = () => audio.close();
        audio.resume().catch(() => {
        });
      } catch {
      }
    }
  }
  async function change(data, revision = board.revision) {
    if (busy) return false;
    busy = true;
    notice.textContent = "";
    try {
      const old = board;
      const next = await api("tasks", "POST", { ...data, revision });
      if (disposed) return false;
      board = next;
      render();
      if (board.cards.some((c) => !c.milestone && c.status === "done" && old.cards.some((o) => o.id === c.id && o.status !== "done"))) celebrate();
      return true;
    } catch (error) {
      fail(error);
      if (error.status === 409) await refresh();
      return false;
    } finally {
      busy = false;
    }
  }
  // Unchanged polls do not touch the DOM or read card payloads.
  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      const next = await api("tasks" + (lanes.children.length ? "?revision=" + board.revision : ""));
      if (disposed || !next) return;
      if (next.revision > board.revision || !lanes.children.length) {
        board = next;
        render();
      }
    } catch (error) {
      fail(error);
    } finally {
      refreshing = false;
    }
  }
  function render() {
    const scroll = lanes.scrollLeft, focused = document.activeElement, focusedCard = focused?.closest(".task-card"), focusedId = focusedCard?.dataset.id, focusedAction = focusedCard && focused !== focusedCard ? focused.getAttribute("aria-label") : null, assignment = bulk.querySelector("select")?.value || "", bulkFocused = bulk.contains(focused) ? focused?.getAttribute("aria-label") : null;
    const value = state.filter || "";
    milestones(filter, value);
    filter.firstChild.textContent = "All milestones";
    if (![...filter.options].some((o) => o.value === value)) {
      state.filter = "";
      filter.value = "";
    }
    for (const id of picked) if (!board.cards.some((c) => c.id === id)) picked.delete(id);
    for (const id of drafts.keys()) if (!board.cards.some((c) => c.id === id)) drafts.delete(id);
    bulk.replaceChildren();
    if (picked.size) {
      bulk.append(el("span", `${picked.size} selected`));
      const assign = el("select");
      milestones(assign, assignment);
      assign.setAttribute("aria-label", "Assign selected cards to milestone");
      bulk.append(assign, button("Assign", () => change({ action: "update", ids: [...picked], changes: { milestone_id: Number(assign.value) || null } })), button("Archive", () => change({ action: "update", ids: [...picked], changes: { archived: true } })), button("Restore", () => change({ action: "update", ids: [...picked], changes: { archived: false } })), button("Delete", () => confirmDelete([...picked])), button("Clear", () => {
        picked.clear();
        render();
      }));
    }
    lanes.replaceChildren();
    for (const [status, symbol, label] of columns) {
      const lane = el("section", void 0, "task-lane");
      lane.dataset.status = status;
      lane.setAttribute("aria-label", label);
      const cards = board.cards.filter((c) => c.status === status && !!c.archived === !!archived.checked && (!filter.value || c.id === Number(filter.value) || c.milestone_id === Number(filter.value)) && fuzzyCard(c, search.value));
      const heading = el("header");
      heading.append(el("h3", symbol + " " + label), el("span", String(cards.length)), button("+", () => editNew(status), "Add task to " + label));
      lane.append(heading);
      lane.ondragover = (e) => {
        if (dragged !== null) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
        }
      };
      lane.ondrop = (e) => {
        e.preventDefault();
        const id = dragged;
        dragged = null;
        if (id === null) return;
        const target = e.target.closest(".task-card");
        if (target && Number(target.dataset.id) === id) return;
        change({ action: "move", id, status, before: target ? Number(target.dataset.id) : null });
      };
      for (const card of cards) {
        const item = el("article", void 0, "task-card");
        item.dataset.id = card.id;
        item.tabIndex = 0;
        item.setAttribute("aria-label", card.title);
        item.setAttribute("aria-selected", String(picked.has(card.id)));
        item.draggable = !card.archived;
        item.ondragstart = (e) => {
          dragged = card.id;
          e.dataTransfer.setData("text/plain", String(card.id));
          e.dataTransfer.effectAllowed = "move";
        };
        item.ondragend = () => {
          dragged = null;
        };
        const title = el("div", (card.milestone ? "\u25C7 " : "") + card.title, "task-card-title");
        item.append(title);
        if (card.milestone) {
          const children = board.cards.filter((c) => c.milestone_id === card.id && !c.archived);
          item.append(el("small", `${children.filter((c) => c.status === "done").length}/${children.length} tasks`));
        } else if (card.milestone_id) {
          const parent = board.cards.find((c) => c.id === card.milestone_id);
          if (parent) item.append(el("small", "\u25C7 " + parent.title));
        }
        item.onclick = (e) => {
          if (e.target.closest("button")) return;
          if (e.ctrlKey || e.metaKey) {
            picked.has(card.id) ? picked.delete(card.id) : picked.add(card.id);
            render();
          } else edit(card);
        };
        item.onkeydown = (e) => {
          if (e.target !== item) return;
          if (e.key === "Enter") {
            e.preventDefault();
            edit(card);
          }
          if (e.key === " ") {
            e.preventDefault();
            picked.has(card.id) ? picked.delete(card.id) : picked.add(card.id);
            render();
          }
        };
        const promote = button("\u25C7", () => change({ action: "update", ids: [card.id], changes: { milestone: !card.milestone } }), card.milestone ? "Convert to task" : "Promote to milestone");
        promote.className = "task-promote";
        item.append(promote);
        lane.append(item);
      }
      if (!cards.length) lane.append(el("p", "No cards", "task-empty"));
      lanes.append(lane);
    }
    lanes.scrollLeft = scroll;
    if (focusedId) {
      const card = lanes.querySelector('[data-id="' + focusedId + '"]');
      (focusedAction ? [...card?.querySelectorAll("button") || []].find((b) => b.getAttribute("aria-label") === focusedAction) : card)?.focus({ preventScroll: true });
    } else if (bulkFocused) {
      [...bulk.querySelectorAll("button,select")].find((b) => b.getAttribute("aria-label") === bulkFocused)?.focus({ preventScroll: true });
    }
  }
  function dialog(title) {
    const d = el("dialog", void 0, "task-dialog"), heading = el("h2", title);
    d.append(heading);
    document.body.append(d);
    editor = d;
    d.addEventListener("close", () => {
      d.remove();
      notice.textContent = "";
      if (editor === d) editor = null;
    });
    return d;
  }
  function field(form, text, node) {
    const wrap = el("div", void 0, "task-field"), label = el("label", text);
    node.id = "task-field-" + crypto.randomUUID();
    label.htmlFor = node.id;
    wrap.append(label, node);
    form.append(wrap);
    return node;
  }
  function editNew(status) {
    const d = dialog("New task"), form = el("form"), title = field(form, "Title", el("input"));
    title.name = "title";
    title.required = true;
    title.maxLength = 500;
    form.append(button("Cancel", () => d.close()));
    const save = el("button", "Create");
    save.type = "submit";
    form.append(save);
    form.onsubmit = async (e) => {
      e.preventDefault();
      save.disabled = true;
      if (await change({ action: "create", title: title.value, status })) d.close();
      else {
        save.disabled = false;
        error.textContent = notice.textContent;
      }
    };
    const error = el("p");
    error.setAttribute("role", "alert");
    form.append(error);
    d.append(form);
    d.showModal();
    title.focus();
  }
  function edit(card) {
    const draft = drafts.get(card.id);
    let revision = draft?.revision ?? board.revision;
    const d = dialog(card.milestone ? "\u25C7 Milestone" : "Task"), form = el("form"), title = field(form, "Title", el("input")), description = field(form, "Description", el("textarea")), status = field(form, "Status", el("select")), parent = field(form, "Milestone", el("select"));
    title.value = draft?.title ?? card.title;
    title.required = true;
    title.maxLength = 500;
    description.value = draft?.description ?? card.description;
    for (const [value, , label] of columns) {
      const o = el("option", label);
      o.value = value;
      status.append(o);
    }
    status.value = draft?.status ?? card.status;
    milestones(parent, (draft ? draft.milestone_id : card.milestone_id) || "", [card.id]);
    parent.disabled = !!card.milestone;
    const actions = el("div", void 0, "task-edit-actions"), save = el("button", "Save");
    save.type = "submit";
    const retainDraft = () => drafts.set(card.id, {revision, title:title.value, description:description.value, status:status.value, milestone_id:Number(parent.value)||null});
    form.oninput = form.onchange = retainDraft;
    d.addEventListener("cancel", () => drafts.delete(card.id));
    actions.append(save, button("Cancel", () => { drafts.delete(card.id); d.close(); }), button(card.milestone ? "Convert to task" : "\u25C7 Promote to milestone", async () => {
      if (await change({ action: "update", ids: [card.id], changes: { milestone: !card.milestone } }, revision)) d.close();
      else error.textContent = notice.textContent;
    }), button(card.archived ? "Restore" : "Archive", async () => {
      if (await change({ action: "update", ids: [card.id], changes: { archived: !card.archived } }, revision)) d.close();
      else error.textContent = notice.textContent;
    }), button("Delete", () => confirmDelete([card.id], d)));
    const error = el("p");
    error.setAttribute("role", "alert");
    form.append(actions, error);
    form.onsubmit = async (e) => {
      e.preventDefault();
      save.disabled = true;
      if (await change({ action: "update", ids: [card.id], changes: { title: title.value, description: description.value, status: status.value, ...(Number(parent.value) || null) !== card.milestone_id ? { milestone_id: Number(parent.value) || null } : {} } }, revision)) { drafts.delete(card.id); d.close(); }
      else {
        save.disabled = false;
        error.textContent = notice.textContent;
        // Keep unsent fields intact until the user reviews the saved version.
        if (board.revision !== revision) {
          const latest = board.cards.find((c) => c.id === card.id), reviewedRevision = board.revision;
          if (latest) {
            const details = el("details"), summary = el("summary", "Review latest saved card");
            details.append(summary, el("pre", JSON.stringify({ title: latest.title, description: latest.description, status: latest.status, milestone_id: latest.milestone_id, milestone: !!latest.milestone, archived: !!latest.archived }, null, 2)), button("Use this revision and keep my edits", () => {
              revision = reviewedRevision;
              retainDraft();
              error.textContent = "Latest revision acknowledged. Review your fields, then save.";
            }));
            error.append(details);
          }
        }
      }
    };
    d.append(form);
    if (card.milestone) {
      const list = el("ul", void 0, "task-checklist");
      d.append(el("h3", "Tasks"), list);
      for (const child of board.cards.filter((c) => c.milestone_id === card.id && !c.archived)) {
        const li = el("li"), check = el("input");
        check.type = "checkbox";
        check.checked = child.status === "done";
        check.setAttribute("aria-label", "Complete " + child.title);
        check.onchange = async () => {
          check.disabled = true;
          if (await change({ action: "update", ids: [child.id], changes: { status: check.checked ? "done" : "backlog" } }, revision)) {
            revision = board.revision;
            if (drafts.has(card.id)) retainDraft();
            check.disabled = false;
          } else {
            check.checked = !check.checked;
            check.disabled = false;
            error.textContent = notice.textContent;
          }
        };
        li.append(check, button(child.title, () => {
          const latest = board.cards.find((c) => c.id === child.id);
          if (!latest) { error.textContent = "This task was deleted. Reopen the milestone to refresh its checklist."; return; }
          retainDraft();
          d.close();
          edit(latest);
        }));
        list.append(li);
      }
    }
    d.showModal();
    title.focus();
  }
  function confirmDelete(ids, previous) {
    const revision = board.revision, d = dialog("Delete " + ids.length + " card" + (ids.length === 1 ? "?" : "s?"));
    d.append(el("p", "This permanently deletes the selected cards. Tasks belonging to deleted milestones are kept and unassigned."), button("Cancel", () => d.close()), button("Delete permanently", async () => {
      if (await change({ action: "delete", ids }, revision)) {
        d.close();
        previous?.close();
      } else error.textContent = notice.textContent;
    }));
    const error = el("p");
    error.setAttribute("role", "alert");
    d.append(error);
    d.showModal();
  }
  search.oninput = () => {
    state.query = search.value;
    render();
  };
  filter.onchange = () => {
    state.filter = filter.value;
    render();
  };
  archived.onchange = () => {
    state.archived = archived.checked;
    picked.clear();
    render();
  };
  refresh();
  const timer = setInterval(() => {
    if (!document.hidden && !busy) refresh();
  }, 2200);
  return () => {
    disposed = true;
    clearInterval(timer);
    document.querySelectorAll(".task-dialog").forEach((d) => {
      d.close();
      d.remove();
    });
    root.remove();
  };
}
export {
  fuzzyCard,
  mountTasks
};
