export type WorkbenchShortcut = 'save' | 'undo' | 'redo';

function isEditableTarget(target: EventTarget | null) {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

export function resolveWorkbenchShortcut(
  event: Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'shiftKey' | 'key' | 'target'>,
): WorkbenchShortcut | null {
  if ((!event.ctrlKey && !event.metaKey) || isEditableTarget(event.target)) return null;
  const key = event.key.toLowerCase();
  if (key === 's') return 'save';
  if (key === 'y' || (key === 'z' && event.shiftKey)) return 'redo';
  if (key === 'z') return 'undo';
  return null;
}
