import Draw from 'ol/interaction/Draw';
import Interaction from 'ol/interaction/Interaction';

import type { WorkspaceLayer } from '../../types/workspace';

export type DrawingTargetResolution =
  | { kind: 'create' }
  | { kind: 'ready'; layer: WorkspaceLayer }
  | { kind: 'blocked'; message: string };

export function resolveDrawingTarget(
  layers: WorkspaceLayer[],
  selectedLayerId: string | null,
): DrawingTargetResolution {
  const selected = layers.find((layer) => layer.id === selectedLayerId);
  if (!selected || selected.source !== 'backend') return { kind: 'create' };
  if (selected.locked) return { kind: 'blocked', message: '目标图层已锁定，请先选择可编辑图层。' };
  if (!selected.visible) return { kind: 'blocked', message: '目标图层已隐藏，请先显示图层。' };
  if (!['Polygon', 'Mixed'].includes(selected.geometryType)) {
    return { kind: 'blocked', message: '目标图层不是 Polygon/Mixed，请选择面图层。' };
  }
  return { kind: 'ready', layer: selected };
}

export function createFirstVertexInteraction(
  draw: Draw,
  canStart: () => boolean,
  onStart: () => void,
) {
  return new Interaction({
    handleEvent: (event) => {
      if (event.type !== 'dblclick' || !canStart()) return true;
      onStart();
      draw.setActive(true);
      draw.appendCoordinates([event.coordinate]);
      return false;
    },
  });
}
