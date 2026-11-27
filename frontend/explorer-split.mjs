// The two trees keep their own scroll areas, so changing the split only
// changes layout. The saved share survives collapse and viewport changes.
export function mountExplorerSplit(host, storageKey) {
  const handle = host.querySelector('#explorer-split');
  const marker = host.querySelector('.marker-section');
  const markerContent = host.querySelector('#marker-section-content');
  const markerResults = host.querySelector('#marker-results');
  const fileContent = host.querySelector('#file-section-content');
  const markerChrome = [...host.querySelectorAll('.marker-section .explorer-heading, #marker-actions, #marker-filter, #marker-status')];
  const fileChrome = [...host.querySelectorAll('.file-section .explorer-heading, .root-label, #file-filter')];
  const stored = Number.parseFloat(localStorage.getItem(storageKey));
  let share = Number.isFinite(stored) && stored >= 0 && stored <= 1 ? stored : null;
  let available = 0, minimum = 0, maximum = 0, height = 0, drag;

  function occupied(blocks) {
    return blocks.reduce((total, block) => {
      const height = block.offsetHeight;
      if (!height) return total;
      const {marginTop, marginBottom} = getComputedStyle(block);
      return total + height + Number.parseFloat(marginTop) + Number.parseFloat(marginBottom);
    }, 0);
  }

  function render() {
    if (!available) return;
    if (share === null) {
      host.style.removeProperty('--explorer-marker-height');
      height = marker.offsetHeight;
    } else {
      height = Math.round(Math.min(maximum, Math.max(minimum, share * available)));
      host.style.setProperty('--explorer-marker-height', height + 'px');
    }
    handle.setAttribute('aria-valuemin', minimum);
    handle.setAttribute('aria-valuemax', maximum);
    handle.setAttribute('aria-valuenow', height);
    handle.setAttribute('aria-valuetext', Math.round(height * 100 / available) + '% for Marker Tree');
  }

  function measure() {
    handle.hidden = markerContent.hidden || fileContent.hidden;
    available = handle.hidden ? 0 : Math.max(0, host.clientHeight - handle.offsetHeight);
    if (!available) {
      finish(true);
      return;
    }
    const upper = occupied(markerChrome) + 1; // The Marker Tree starts with a border.
    const lower = occupied(fileChrome);
    if (available < upper + lower) {
      minimum = maximum = Math.round(available * upper / (upper + lower));
    } else {
      const scrollRoom = Math.floor((available - upper - lower) / 2);
      const markerRoom = markerResults.childElementCount ? Math.min(25, scrollRoom) : 0;
      minimum = Math.ceil(upper + markerRoom);
      maximum = Math.max(minimum, Math.floor(available - lower - Math.min(40, scrollRoom)));
    }
    host.style.setProperty('--explorer-marker-min', minimum + 'px');
    host.style.setProperty('--explorer-marker-max', maximum + 'px');
    render();
  }

  function resize(next) {
    share = Math.min(maximum, Math.max(minimum, next)) / available;
    render();
  }

  function save() {
    localStorage.setItem(storageKey, String(share));
  }

  function finish(cancel = false) {
    if (!drag) return;
    const initial = drag;
    drag = null;
    if (handle.hasPointerCapture(initial.pointer)) handle.releasePointerCapture(initial.pointer);
    document.body.classList.remove('explorer-splitting');
    if (cancel) {
      share = initial.share;
      render();
    } else if (share !== initial.share) save();
  }

  handle.onpointerdown = event => {
    if (event.button !== 0 || drag || !available) return;
    event.preventDefault();
    handle.focus({preventScroll: true});
    drag = {pointer: event.pointerId, y: event.clientY, height, share};
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add('explorer-splitting');
  };
  handle.onpointermove = event => {
    if (event.pointerId === drag?.pointer && event.clientY !== drag.y) {
      resize(drag.height + event.clientY - drag.y);
    } else if (event.pointerId === drag?.pointer && share !== drag.share) {
      share = drag.share;
      render();
    }
  };
  handle.onpointerup = handle.onlostpointercapture = event => {
    if (event.pointerId === drag?.pointer) finish();
  };
  handle.onpointercancel = event => {
    if (event.pointerId === drag?.pointer) finish(true);
  };

  handle.onkeydown = event => {
    if (event.key === 'Escape' && drag) {
      event.preventDefault();
      event.stopPropagation();
      finish(true);
      return;
    }
    if (drag || !available || !['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? 50 : 10;
    resize(event.key === 'Home' ? minimum : event.key === 'End' ? maximum :
      height + (event.key === 'ArrowUp' ? -step : step));
    save();
  };
  handle.ondblclick = () => {
    share = null;
    localStorage.removeItem(storageKey);
    render();
  };

  const sizes = new ResizeObserver(entries => {
    // The marker's automatic height can change when its results arrive.
    // A user-set height needs recalculation only when the viewport or controls change.
    if (share === null || entries.some(entry => entry.target !== marker)) measure();
  });
  for (const target of [host, marker, ...markerChrome, ...fileChrome]) sizes.observe(target);
  const visibility = new MutationObserver(measure);
  for (const panel of [markerContent, fileContent]) {
    visibility.observe(panel, {attributes: true, attributeFilter: ['hidden']});
  }
  measure();
}
