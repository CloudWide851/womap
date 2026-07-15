import type MapBrowserEvent from 'ol/MapBrowserEvent';
import type Draw from 'ol/interaction/Draw';
import { describe, expect, it, vi } from 'vitest';

import type { WorkspaceLayer } from '../../types/workspace';
import {
  createFirstVertexInteraction,
  resolveDrawingTarget,
  SNAP_PIXEL_TOLERANCE,
  snapEligibleLayers,
} from './polygonEditing';

function layer(overrides: Partial<WorkspaceLayer> = {}): WorkspaceLayer {
  return {
    id: '1',
    name: '图斑',
    geometryType: 'Polygon',
    featureCount: 0,
    visible: true,
    locked: false,
    opacity: 1,
    color: '#4656a8',
    fields: [],
    performance: {
      featureCount: 0,
      largeLayer: false,
      indexed: true,
      recommendedMode: 'bbox',
    },
    source: 'backend',
    ...overrides,
  };
}

describe('polygon editing helpers', () => {
  it('creates a backend layer for demo or empty selections', () => {
    expect(resolveDrawingTarget([layer({ source: 'demo' })], '1')).toEqual({ kind: 'create' });
    expect(resolveDrawingTarget([], null)).toEqual({ kind: 'create' });
  });

  it('blocks locked and incompatible backend layers', () => {
    expect(resolveDrawingTarget([layer({ locked: true })], '1')).toMatchObject({
      kind: 'blocked',
    });
    expect(resolveDrawingTarget([layer({ geometryType: 'Point' })], '1')).toMatchObject({
      kind: 'blocked',
    });
  });

  it('limits snapping to visible unlocked backend vector layers', () => {
    const eligible = layer({ id: 'eligible' });
    const layers = [
      eligible,
      layer({ id: 'demo', source: 'demo' }),
      layer({ id: 'hidden', visible: false }),
      layer({ id: 'locked', locked: true }),
      layer({ id: 'raster', kind: 'raster', geometryType: 'Raster' }),
    ];

    expect(snapEligibleLayers(layers)).toEqual([eligible]);
    expect(SNAP_PIXEL_TOLERANCE).toBe(10);
  });

  it('uses the first double click as the first polygon vertex', () => {
    const setActive = vi.fn();
    const appendCoordinates = vi.fn();
    const onStart = vi.fn();
    const draw = { setActive, appendCoordinates } as unknown as Draw;
    const interaction = createFirstVertexInteraction(draw, () => true, onStart);

    const propagated = interaction.handleEvent({
      type: 'dblclick',
      coordinate: [12, 34],
    } as MapBrowserEvent<PointerEvent>);

    expect(propagated).toBe(false);
    expect(onStart).toHaveBeenCalledOnce();
    expect(setActive).toHaveBeenCalledWith(true);
    expect(appendCoordinates).toHaveBeenCalledWith([[12, 34]]);
  });

  it('leaves ordinary events and later double clicks to OpenLayers Draw', () => {
    const draw = { setActive: vi.fn(), appendCoordinates: vi.fn() } as unknown as Draw;
    const interaction = createFirstVertexInteraction(draw, () => false, vi.fn());

    expect(
      interaction.handleEvent({ type: 'click', coordinate: [1, 2] } as MapBrowserEvent<PointerEvent>),
    ).toBe(true);
    expect(
      interaction.handleEvent({ type: 'dblclick', coordinate: [1, 2] } as MapBrowserEvent<PointerEvent>),
    ).toBe(true);
  });
});
