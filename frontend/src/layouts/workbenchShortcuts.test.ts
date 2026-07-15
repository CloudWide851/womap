import { describe, expect, it } from 'vitest';

import { resolveWorkbenchShortcut } from './workbenchShortcuts';

function shortcutEvent(
  key: string,
  target: EventTarget | null = document.body,
  overrides: Partial<Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'shiftKey'>> = {},
) {
  return {
    key,
    target,
    ctrlKey: true,
    metaKey: false,
    shiftKey: false,
    ...overrides,
  };
}

describe('resolveWorkbenchShortcut', () => {
  it('maps save, undo, and both redo variants', () => {
    expect(resolveWorkbenchShortcut(shortcutEvent('s'))).toBe('save');
    expect(resolveWorkbenchShortcut(shortcutEvent('z'))).toBe('undo');
    expect(resolveWorkbenchShortcut(shortcutEvent('z', document.body, { shiftKey: true }))).toBe(
      'redo',
    );
    expect(resolveWorkbenchShortcut(shortcutEvent('y'))).toBe('redo');
    expect(
      resolveWorkbenchShortcut(shortcutEvent('s', document.body, { ctrlKey: false, metaKey: true })),
    ).toBe('save');
  });

  it('does not intercept typing or unmodified keys', () => {
    const input = document.createElement('input');
    const textarea = document.createElement('textarea');
    const select = document.createElement('select');
    const editable = document.createElement('div');
    Object.defineProperty(editable, 'isContentEditable', { value: true });
    document.body.append(input, textarea, select, editable);

    expect(resolveWorkbenchShortcut(shortcutEvent('z', input))).toBeNull();
    expect(resolveWorkbenchShortcut(shortcutEvent('z', textarea))).toBeNull();
    expect(resolveWorkbenchShortcut(shortcutEvent('z', select))).toBeNull();
    expect(resolveWorkbenchShortcut(shortcutEvent('z', editable))).toBeNull();
    expect(
      resolveWorkbenchShortcut(shortcutEvent('z', document.body, { ctrlKey: false })),
    ).toBeNull();
  });
});
