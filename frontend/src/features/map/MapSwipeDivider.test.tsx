import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clampSwipePosition,
  MapSwipeDivider,
  swipePositionFromClientX,
} from './MapSwipeDivider';

function SwipeHarness() {
  const [position, setPosition] = useState(50);
  return (
    <div data-testid="map-shell">
      <MapSwipeDivider position={position} onChange={setPosition} />
    </div>
  );
}

function firePointer(
  target: Element,
  type: 'pointerdown' | 'pointermove' | 'pointerup' | 'pointercancel',
  pointerId: number,
  clientX = 0,
) {
  const event = new MouseEvent(type, { bubbles: true, clientX });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  fireEvent(target, event);
}

afterEach(cleanup);

describe('MapSwipeDivider', () => {
  it('clamps pointer positions to the map shell width', () => {
    expect(swipePositionFromClientX(150, 100, 200)).toBe(25);
    expect(swipePositionFromClientX(50, 100, 200)).toBe(0);
    expect(swipePositionFromClientX(350, 100, 200)).toBe(100);
    expect(clampSwipePosition(49.6)).toBe(50);
  });

  it('captures the pointer and updates the shared slider value', () => {
    render(<SwipeHarness />);
    const shell = screen.getByTestId('map-shell');
    const slider = screen.getByRole('slider', { name: '两期影像卷帘位置' });
    Object.defineProperty(shell, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ left: 100, width: 200 }),
    });
    const setPointerCapture = vi.fn();
    const releasePointerCapture = vi.fn();
    Object.defineProperties(slider, {
      setPointerCapture: { configurable: true, value: setPointerCapture },
      hasPointerCapture: { configurable: true, value: () => true },
      releasePointerCapture: { configurable: true, value: releasePointerCapture },
    });

    firePointer(slider, 'pointerdown', 4, 150);
    expect(setPointerCapture).toHaveBeenCalledWith(4);
    expect(slider).toHaveAttribute('aria-valuenow', '25');
    firePointer(slider, 'pointermove', 4, 260);
    expect(slider).toHaveAttribute('aria-valuenow', '80');
    firePointer(slider, 'pointerup', 4);
    expect(releasePointerCapture).toHaveBeenCalledWith(4);
  });

  it('releases pointer capture and stops dragging when the pointer is canceled', () => {
    render(<SwipeHarness />);
    const shell = screen.getByTestId('map-shell');
    const slider = screen.getByRole('slider', { name: '两期影像卷帘位置' });
    Object.defineProperty(shell, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ left: 100, width: 200 }),
    });
    const releasePointerCapture = vi.fn();
    Object.defineProperties(slider, {
      setPointerCapture: { configurable: true, value: vi.fn() },
      hasPointerCapture: { configurable: true, value: () => true },
      releasePointerCapture: { configurable: true, value: releasePointerCapture },
    });

    firePointer(slider, 'pointerdown', 9, 150);
    firePointer(slider, 'pointercancel', 9);
    firePointer(slider, 'pointermove', 9, 260);

    expect(releasePointerCapture).toHaveBeenCalledWith(9);
    expect(slider).toHaveAttribute('aria-valuenow', '25');
  });

  it('supports arrows, accelerated steps, and boundary keys', () => {
    render(<SwipeHarness />);
    const slider = screen.getByRole('slider', { name: '两期影像卷帘位置' });

    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    expect(slider).toHaveAttribute('aria-valuenow', '51');
    fireEvent.keyDown(slider, { key: 'ArrowLeft', shiftKey: true });
    expect(slider).toHaveAttribute('aria-valuenow', '41');
    fireEvent.keyDown(slider, { key: 'Home' });
    expect(slider).toHaveAttribute('aria-valuenow', '0');
    fireEvent.keyDown(slider, { key: 'End' });
    expect(slider).toHaveAttribute('aria-valuenow', '100');
  });
});
