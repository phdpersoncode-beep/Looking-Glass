import {ViewPlugin} from '@codemirror/view';
import {overviewLayout} from './match-overview.mjs';

const label = id => 'Go to thread #' + id;

export function threadOverview(spanField, navigate) {
  return ViewPlugin.fromClass(class {
    constructor(view) {
      this.view = view;
      this.dom = document.createElement('nav');
      this.dom.className = 'cm-thread-map';
      this.dom.setAttribute('aria-label', 'Discussion locations');
      this.dom.hidden = true;
      this.buttons = new Map();
      view.dom.append(this.dom);
      this.measure();
    }

    update(update) {
      if (update.docChanged || update.geometryChanged || update.viewportChanged ||
          update.startState.field(spanField) !== update.state.field(spanField)) this.measure();
    }

    measure() {
      const spans = this.view.state.field(spanField);
      if (!spans.length) {
        if (this.buttons.size) this.render({top: 0, height: 0, groups: []});
        return;
      }
      if (this.spans !== spans) {
        this.spans = spans;
        this.sortedSpans = [...spans].sort((a, b) => a.from - b.from || a.id - b.id);
      }
      const sorted = this.sortedSpans;
      this.view.requestMeasure({
        key: this,
        read: view => {
          if (view.state.field(spanField) !== spans) return null;
          const {top, height, points} = overviewLayout(view, sorted);
          const groups = [];
          sorted.forEach((span, index) => {
            const last = groups.at(-1), point = points[index];
            if (last && point - last.top < 8) last.spans.push(span);
            else groups.push({top: point, spans: [span]});
          });
          return {top, height, groups};
        },
        write: layout => {
          if (layout && this.view.state.field(spanField) === spans) this.render(layout);
        }
      });
    }

    render({top, height, groups}) {
      this.dom.hidden = !groups.length;
      this.dom.style.top = top + 'px';
      this.dom.style.height = height + 'px';
      const next = new Map();
      let at = 0;
      for (const group of groups) {
        const ids = group.spans.map(span => span.id);
        const key = ids.join(',');
        let button = this.buttons.get(key);
        if (!button) {
          button = document.createElement('button');
          button.type = 'button';
          button.className = 'cm-thread-marker';
          button.title = ids.length === 1 ? label(ids[0]) : ids.length + ' threads here';
          button.setAttribute('aria-label', button.title);
          if (ids.length > 1) button.setAttribute('aria-expanded', 'false');
          button.onclick = () => {
            if (ids.length === 1) navigate(ids[0]);
            else if (this.popup?.button === button) this.closePopup(true);
            else this.openPopup(button, ids);
          };
        }
        button.classList.toggle('cm-thread-marker-resolved', group.spans.every(span => span.resolved));
        button.style.top = group.top + 'px';
        if (this.dom.children[at] !== button) this.dom.insertBefore(button, this.dom.children[at] || null);
        next.set(key, button);
        at++;
      }
      if (this.popup && ![...next.values()].includes(this.popup.button)) this.closePopup();
      for (const [key, button] of this.buttons) if (!next.has(key)) button.remove();
      this.buttons = next;
    }

    openPopup(button, ids) {
      this.closePopup();
      const list = document.createElement('div');
      list.className = 'cm-thread-choices';
      list.setAttribute('role', 'group');
      list.setAttribute('aria-label', 'Threads at this location');
      for (const id of ids) {
        const choice = document.createElement('button');
        choice.type = 'button';
        choice.textContent = 'Thread #' + id;
        choice.onclick = () => { this.closePopup(); navigate(id); };
        list.append(choice);
      }
      const events = new AbortController();
      this.popup = {button, list, events};
      button.setAttribute('aria-expanded', 'true');
      list.style.maxHeight = Math.min(240, this.dom.clientHeight) + 'px';
      this.dom.append(list);
      const maxTop = this.dom.clientHeight - list.offsetHeight;
      list.style.top = Math.max(0, Math.min(maxTop, button.offsetTop)) + 'px';
      document.addEventListener('pointerdown', event => {
        if (!list.contains(event.target) && event.target !== button) this.closePopup();
      }, {signal: events.signal});
      list.addEventListener('focusout', event => {
        if (!list.contains(event.relatedTarget) && event.relatedTarget !== button) this.closePopup();
      });
      list.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        event.stopPropagation();
        this.closePopup(true);
      });
      list.firstChild.focus({preventScroll: true});
    }

    closePopup(focus = false) {
      if (!this.popup) return;
      const {button, list, events} = this.popup;
      this.popup = null;
      events.abort();
      button.setAttribute('aria-expanded', 'false');
      list.remove();
      if (focus) button.focus({preventScroll: true});
    }

    destroy() {
      this.closePopup();
      this.dom.remove();
    }
  });
}
