import { useEffect, useRef } from 'react';
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';

interface MapSwipeDividerProps {
  position: number;
  onChange: (position: number) => void;
}

export function clampSwipePosition(position: number) {
  return Math.min(100, Math.max(0, Math.round(position)));
}

export function swipePositionFromClientX(clientX: number, left: number, width: number) {
  if (width <= 0) return 0;
  return clampSwipePosition(((clientX - left) / width) * 100);
}

export function MapSwipeDivider({ position, onChange }: MapSwipeDividerProps) {
  const activePointerIdRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      activePointerIdRef.current = null;
    },
    [],
  );

  const updateFromPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    const container = event.currentTarget.parentElement;
    if (!container) return;
    const bounds = container.getBoundingClientRect();
    onChange(swipePositionFromClientX(event.clientX, bounds.left, bounds.width));
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    activePointerIdRef.current = event.pointerId;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    updateFromPointer(event);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (activePointerIdRef.current !== event.pointerId) return;
    updateFromPointer(event);
  };

  const finishPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (activePointerIdRef.current !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    activePointerIdRef.current = null;
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 10 : 1;
    let nextPosition: number | null = null;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') nextPosition = position - step;
    if (event.key === 'ArrowRight' || event.key === 'ArrowUp') nextPosition = position + step;
    if (event.key === 'Home') nextPosition = 0;
    if (event.key === 'End') nextPosition = 100;
    if (nextPosition === null) return;
    event.preventDefault();
    onChange(clampSwipePosition(nextPosition));
  };

  return (
    <div
      className="map-swipe-divider"
      style={{ left: `${position}%` }}
      role="slider"
      tabIndex={0}
      aria-label="两期影像卷帘位置"
      aria-orientation="horizontal"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={position}
      aria-valuetext={`${position}%`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishPointer}
      onPointerCancel={finishPointer}
      onKeyDown={handleKeyDown}
    >
      <span className="map-swipe-line" aria-hidden="true" />
      <span className="map-swipe-handle" aria-hidden="true">
        <i />
        <i />
      </span>
    </div>
  );
}
