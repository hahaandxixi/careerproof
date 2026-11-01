/** Retain a read action's focus without overriding navigation or user input. */
export function trackReadRetryFocus(source: HTMLElement, target: () => HTMLElement | null, isCurrent: () => boolean) {
  const doc = source.ownerDocument;
  const win = doc.defaultView;
  let moved = doc.activeElement !== source;
  const focus = (event: FocusEvent) => { if (event.target !== source && event.target !== doc.body) moved = true; };
  const pointer = () => { moved = true; };
  const keyboard = (event: KeyboardEvent) => { if (event.key === "Tab" || event.key === "Escape") moved = true; };
  const blur = () => { moved = true; };
  doc.addEventListener("focusin", focus);
  doc.addEventListener("pointerdown", pointer, true);
  doc.addEventListener("keydown", keyboard, true);
  win?.addEventListener("blur", blur);
  return () => {
    const settle = () => {
      doc.removeEventListener("focusin", focus);
      doc.removeEventListener("pointerdown", pointer, true);
      doc.removeEventListener("keydown", keyboard, true);
      win?.removeEventListener("blur", blur);
      if (moved || !isCurrent() || doc.visibilityState !== "visible") return;
      if (doc.activeElement !== source && doc.activeElement !== doc.body) return;
      const next = source.isConnected && source.getClientRects().length && !source.hasAttribute("disabled") ? source : target();
      if (next?.isConnected && next.getClientRects().length && !next.hasAttribute("disabled")) next.focus({ preventScroll: true });
    };
    // React must commit the fresh status before an old action can be replaced.
    if (win) win.requestAnimationFrame(settle); else settle();
  };
}
