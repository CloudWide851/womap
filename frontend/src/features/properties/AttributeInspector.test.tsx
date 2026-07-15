import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import { AttributeInspector } from './AttributeInspector';

afterEach(() => {
  cleanup();
  useWorkspaceStore.getState().reset();
  vi.restoreAllMocks();
});

describe('AttributeInspector', () => {
  it('moves focus inside, traps Tab, closes on Escape, and restores focus', async () => {
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      callback(0);
      return 1;
    });
    render(
      <>
        <button type="button">打开属性</button>
        <AttributeInspector />
      </>,
    );
    const opener = screen.getByRole('button', { name: '打开属性' });
    opener.focus();

    act(() => useWorkspaceStore.getState().openLayerInspector('project-boundary'));
    const dialog = await screen.findByRole('dialog');
    const close = screen.getByRole('button', { name: '关闭属性检查器' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(close).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(opener).toHaveFocus();
  });
});
