export type GeometryType = 'Point' | 'LineString' | 'Polygon' | 'Mixed';

export interface WorkspaceLayer {
  id: string;
  name: string;
  geometryType: GeometryType;
  featureCount: number;
  visible: boolean;
  locked: boolean;
  opacity: number;
  color: string;
}

export interface ToolAction {
  key: string;
  label: string;
}
