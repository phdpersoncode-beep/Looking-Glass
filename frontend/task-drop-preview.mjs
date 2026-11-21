export const taskDragType = 'application/x-looking-glass-cards';

export function setTaskRowDragImage(event) {
  const row = event.currentTarget;
  const {left, top, width, height} = row.getBoundingClientRect();
  const ghost = document.createElement('canvas');
  ghost.width = Math.ceil(width);
  ghost.height = Math.ceil(height);
  const paint = ghost.getContext('2d');
  paint.strokeStyle = getComputedStyle(row).getPropertyValue('--muted').trim();
  paint.setLineDash([4, 3]);
  paint.beginPath();
  paint.roundRect(1, 1, ghost.width - 2, ghost.height - 2, 4);
  paint.stroke();
  ghost.setAttribute('aria-hidden', 'true');
  ghost.style.cssText = 'position:fixed;left:-10000px;top:0;pointer-events:none';
  (row.closest('dialog') ?? document.body).append(ghost);
  event.dataTransfer.setDragImage(ghost, event.clientX - left, event.clientY - top);
  requestAnimationFrame(() => ghost.remove());
}

// Use layout coordinates for hit testing even while items are sliding into place.
export function taskDropItem(container, clientY, selector) {
  const y = clientY - container.getBoundingClientRect().top - container.clientTop;
  for (const child of container.children) {
    if (child.matches(selector) && !child.classList.contains('task-drag-origin') &&
        y < child.offsetTop + child.offsetHeight) return child;
  }
  return null;
}

export function taskDropPreview(items) {
  const gap = document.createElement('div');
  gap.className = 'task-drop-preview';
  gap.setAttribute('aria-hidden', 'true');
  const animations = new Map();
  let origins = new Set();

  function capture() {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return null;
    return new Map([...items()].filter(item => !origins.has(item))
      .map(item => [item.dataset.id, item.getBoundingClientRect().top]));
  }

  function settle(before) {
    if (!before) return;
    const movement = [...items()].filter(item => before.has(item.dataset.id) && !origins.has(item))
      .map(item => [item, before.get(item.dataset.id) - item.getBoundingClientRect().top]);
    for (const [item, delta] of movement) {
      if (Math.abs(delta) < 0.5) continue;
      const animation = item.animate([{transform: `translateY(${delta}px)`}, {transform: 'none'}],
        {duration: 165, easing: 'cubic-bezier(.2,.75,.3,1)'});
      animations.set(item, animation);
      animation.onfinish = () => {
        if (animations.get(item) === animation) animations.delete(item);
      };
    }
  }

  function update(layout, animate) {
    const before = animate ? capture() : null;
    for (const animation of animations.values()) animation.cancel();
    animations.clear();
    layout();
    settle(before);
  }

  return {
    gap, capture, settle,
    show(container, before, sources, height, indent = 0) {
      const size = `${height}px`, inset = `${indent}px`;
      if (gap.parentElement === container && gap.nextSibling === before &&
          gap.style.height === size && gap.style.marginInlineStart === inset) return;
      update(() => {
        for (const item of origins) item.classList.remove('task-drag-origin');
        origins = new Set(sources);
        for (const item of origins) item.classList.add('task-drag-origin');
        gap.style.height = size;
        gap.style.marginInlineStart = inset;
        container.insertBefore(gap, before);
      }, true);
    },
    clear(animate = true) {
      if (!gap.parentElement && (animate || !animations.size)) return;
      update(() => {
        gap.remove();
        for (const item of origins) item.classList.remove('task-drag-origin');
        origins.clear();
      }, animate);
    }
  };
}
