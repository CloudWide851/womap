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
});
