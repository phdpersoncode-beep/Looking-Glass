import {Prec, StateEffect, StateField} from '@codemirror/state';
import {keymap, runScopeHandlers} from '@codemirror/view';
import {search, SearchQuery, getSearchQuery, setSearchQuery, searchPanelOpen, openSearchPanel, closeSearchPanel, findNext, findPrevious, selectMatches, replaceNext, replaceAll} from '@codemirror/search';

const showReplace = StateEffect.define();
const replaceVisible = StateField.define({
  create: () => false,
  update: (value, transaction) => {
    for (const effect of transaction.effects) if (effect.is(showReplace)) value = effect.value;
    return value;
  }
});

export function toggleDocumentSearch(view) {
  if (searchPanelOpen(view.state) && !view.state.field(replaceVisible)) return closeSearchPanel(view);
  return revealSearch(view, false);
}

export function toggleDocumentReplace(view) {
  const visible = searchPanelOpen(view.state) && view.state.field(replaceVisible);
  return revealSearch(view, !view.state.readOnly && !visible);
}

function revealSearch(view, replace) {
  const open = searchPanelOpen(view.state);
  view.dispatch({effects: showReplace.of(replace)});
  if (!open) return openSearchPanel(view);
  // Toggling rows must retain the query, including a regular expression, even
  // when the document selection currently contains one of its matches.
  const input = view.dom.querySelector('.document-search [main-field]');
  input?.focus({preventScroll: true}); input?.select();
  return true;
}

// Used for toolbar/table focus too, before application-level Escape navigation.
export function documentSearchShortcut(view, event) {
  if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey) {
    if (event.key.toLowerCase() === 'f') return toggleDocumentSearch(view);
    if (event.key.toLowerCase() === 'h') return toggleDocumentReplace(view);
  }
  if (event.key === 'Escape') return closeSearchPanel(view);
  return false;
}

const paths = {
  expand: '<path d="m7 4 6 6-6 6"/>',
  previous: '<path d="M10 16V4m-5 5 5-5 5 5"/>',
  next: '<path d="M10 4v12m-5-5 5 5 5-5"/>',
  select: '<path d="M6 3H3v11"/><rect x="6" y="6" width="11" height="11" rx="2"/><path d="m9 12 2 2 4-4"/>',
  close: '<path d="m5 5 10 10M5 15 15 5"/>',
  replace: '<path d="M5 4h7a4 4 0 0 1 0 8H4m4-4-4 4 4 4"/>',
  replaceAll: '<path d="M5 3h7a3 3 0 0 1 0 6H4m3-3L4 9l3 3m5 0h2a2 2 0 0 1 0 4H4m3-3-3 3 3 3"/>'
};

class DocumentSearchPanel {
  constructor(view) {
    this.view = view;
    this.top = true;
    this.dom = document.createElement('div');
    this.dom.className = 'cm-search document-search';
    this.dom.setAttribute('role', 'search');
    this.dom.setAttribute('aria-label', 'Search document');

    const button = (name, label, action, icon = name) => {
      const element = document.createElement('button');
      element.type = 'button'; element.name = name; element.title = label;
      element.setAttribute('aria-label', label);
      if (paths[icon]) element.innerHTML = `<svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[icon]}</svg>`;
      else { const symbol = document.createElement('span'); symbol.textContent = icon; symbol.setAttribute('aria-hidden', 'true'); element.append(symbol); }
      element.onclick = action;
      return element;
    };
    const input = (name, label) => {
      const element = document.createElement('input');
      element.name = name; element.placeholder = label; element.setAttribute('aria-label', label);
      element.autocomplete = 'off'; element.spellcheck = false;
      element.oninput = () => this.commit();
      return element;
    };
    this.searchField = input('search', 'Find');
    this.searchField.setAttribute('main-field', 'true');
    this.replaceField = input('replace', 'Replace');
    this.replaceToggle = button('toggleReplace', 'Toggle replace (Ctrl+H)', () => toggleDocumentReplace(view), 'expand');
    this.replaceToggle.setAttribute('aria-expanded', 'false');
    this.options = ['caseSensitive', 'wholeWord', 'regexp'].map((option, index) => {
      const element = button(option, ['Match case', 'Whole words', 'Regular expression'][index], event => {
        element.setAttribute('aria-pressed', String(element.getAttribute('aria-pressed') !== 'true'));
        this.commit();
        // A mouse toggle returns to typing/navigating matches; keyboard users
        // retain their place among the option buttons.
        if (event.detail) this.searchField.focus({preventScroll: true});
      }, ['Aa', 'ab', '.*'][index]);
      element.setAttribute('aria-pressed', 'false');
      return element;
    });
    const row = document.createElement('div'); row.className = 'document-search-row';
    row.append(this.replaceToggle, this.searchField, ...this.options,
      button('previous', 'Previous match (Shift+Enter)', () => findPrevious(view)),
      button('next', 'Next match (Enter)', () => findNext(view)),
      button('select', 'Select all matches', () => selectMatches(view)),
      button('close', 'Close search (Esc)', () => closeSearchPanel(view)));
    this.replaceRow = document.createElement('div'); this.replaceRow.className = 'document-search-row document-replace-row';
    this.replaceRow.append(this.replaceField,
      button('replace', 'Replace next (Enter)', () => replaceNext(view)),
      button('replaceAll', 'Replace all', () => replaceAll(view)));
    this.dom.append(row, this.replaceRow);
    this.dom.onkeydown = event => {
      if (runScopeHandlers(view, event, 'search-panel')) event.preventDefault();
      else if (event.key === 'Enter' && !event.isComposing && [this.searchField, this.replaceField].includes(event.target)) {
        event.preventDefault();
        if (event.target === this.replaceField) replaceNext(view);
        else (event.shiftKey ? findPrevious : findNext)(view);
      }
    };
    this.update();
  }
  commit() {
    const options = Object.fromEntries(this.options.map(element => [element.name, element.getAttribute('aria-pressed') === 'true']));
    const query = new SearchQuery({...getSearchQuery(this.view.state), ...options, search: this.searchField.value, replace: this.replaceField.value});
    if (!query.eq(getSearchQuery(this.view.state))) this.view.dispatch({effects: setSearchQuery.of(query)});
  }
  update() {
    const query = getSearchQuery(this.view.state);
    if (this.searchField.value !== query.search) this.searchField.value = query.search;
    if (this.replaceField.value !== query.replace) this.replaceField.value = query.replace;
    this.searchField.setAttribute('aria-invalid', String(!!query.search && !query.valid));
    this.searchField.title = query.valid || !query.search ? 'Find in document' : 'Invalid regular expression';
    for (const element of this.options) element.setAttribute('aria-pressed', String(query[element.name]));
    this.replaceToggle.hidden = this.view.state.readOnly;
    const expanded = !this.view.state.readOnly && this.view.state.field(replaceVisible);
    this.replaceRow.hidden = !expanded;
    this.replaceToggle.setAttribute('aria-expanded', String(expanded));
  }
  mount() { this.searchField.focus({preventScroll: true}); this.searchField.select(); }
}

export const documentSearch = [
  replaceVisible,
  search({top: true, createPanel: view => new DocumentSearchPanel(view)}),
  Prec.high(keymap.of([
    {key: 'Mod-f', run: toggleDocumentSearch, scope: 'editor search-panel'},
    {key: 'Mod-h', run: toggleDocumentReplace, scope: 'editor search-panel'}
  ]))
];
