import { afterEach, describe, expect, it } from 'vitest';

import { useWorkspaceStore } from './useWorkspaceStore';

describe('workspace store feature focus', () => {
  afterEach(() => {
    useWorkspaceStore.getState().reset();
  });

  it('selects the first feature for the selected layer', () => {
    useWorkspaceStore.getState().selectLayer('survey-points');

    expect(useWorkspaceStore.getState().selectedLayerId).toBe('survey-points');
    expect(useWorkspaceStore.getState().selectedFeatureId).toBe('feature-point-018');
  });

  it('creates a focus request and notice when focusing a feature', () => {
    useWorkspaceStore.getState().focusFeature('feature-boundary-108');

    expect(useWorkspaceStore.getState().selectedLayerId).toBe('project-boundary');
    expect(useWorkspaceStore.getState().selectedFeatureId).toBe('feature-boundary-108');
    expect(useWorkspaceStore.getState().featureFocusRequest).toEqual({
      featureId: 'feature-boundary-108',
      sequence: 1,
    });
    expect(useWorkspaceStore.getState().notice?.title).toBe('已定位 B-108');

    useWorkspaceStore.getState().focusFeature('feature-boundary-108');

    expect(useWorkspaceStore.getState().featureFocusRequest).toEqual({
      featureId: 'feature-boundary-108',
      sequence: 2,
    });
  });

  it('keeps feature inspector selection aligned with map focus', () => {
    useWorkspaceStore.getState().openFeatureInspector('survey-points', 'feature-point-031');

    expect(useWorkspaceStore.getState().selectedLayerId).toBe('survey-points');
    expect(useWorkspaceStore.getState().selectedFeatureId).toBe('feature-point-031');
    expect(useWorkspaceStore.getState().inspectorTarget).toEqual({
      kind: 'feature',
      layerId: 'survey-points',
      featureId: 'feature-point-031',
    });
    expect(useWorkspaceStore.getState().featureFocusRequest?.featureId).toBe('feature-point-031');
  });

  it('upserts and selects a backend layer without duplicating it', () => {
    const base = useWorkspaceStore.getState().layers[0];
    const backendLayer = { ...base, id: '12', source: 'backend' as const, featureCount: 0 };

    useWorkspaceStore.getState().upsertBackendLayer(backendLayer, true);
    useWorkspaceStore.getState().upsertBackendLayer({ ...backendLayer, featureCount: 1 });

    expect(useWorkspaceStore.getState().selectedLayerId).toBe('12');
    expect(useWorkspaceStore.getState().layers.filter((layer) => layer.id === '12')).toHaveLength(1);
    expect(useWorkspaceStore.getState().layers.find((layer) => layer.id === '12')?.featureCount).toBe(1);
  });

  it('cancels the drawing tool when leaving edit mode', () => {
    useWorkspaceStore.getState().setWorkspaceMode('edit');
    useWorkspaceStore.getState().setActiveTool('draw');
    useWorkspaceStore.getState().setWorkspaceMode('browse');

    expect(useWorkspaceStore.getState().activeTool).toBe('select');
  });
});
