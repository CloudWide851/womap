import { Button, Tooltip } from 'antd';
import { DatabaseZap, Layers3, MapPinned, MousePointerSquareDashed, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import Feature from 'ol/Feature';
import GeoJSON from 'ol/format/GeoJSON';
import { buffer, getCenter } from 'ol/extent';
import type { Extent } from 'ol/extent';
import type { FeatureLike } from 'ol/Feature';
import Point from 'ol/geom/Point';
import Polygon from 'ol/geom/Polygon';
import Geometry from 'ol/geom/Geometry';
import { fromExtent as polygonFromExtent } from 'ol/geom/Polygon';
import Draw from 'ol/interaction/Draw';
import SelectInteraction from 'ol/interaction/Select';
import type { DrawEvent } from 'ol/interaction/Draw';
import Map from 'ol/Map';
import MapBrowserEvent from 'ol/MapBrowserEvent';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
import WebGLTileLayer from 'ol/layer/WebGLTile';
import type { Style as WebGLTileStyle } from 'ol/layer/WebGLTile';
import { fromLonLat, toLonLat, transformExtent } from 'ol/proj';
import { getRenderPixel } from 'ol/render';
import type RenderEvent from 'ol/render/Event';
import CircleStyle from 'ol/style/Circle';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import Style from 'ol/style/Style';
import OSM from 'ol/source/OSM';
import VectorSource from 'ol/source/Vector';
import XYZ from 'ol/source/XYZ';
import GeoTIFFSource from 'ol/source/GeoTIFF';

import {
  createLayerFeature,
  createManualLayer,
  getLayerFeatures,
  getRasterPixel,
  resolveApiUrl,
} from '../../services/api';
import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import { useWorkspaceContextStore } from '../../stores/useWorkspaceContextStore';
import { useSpatialAnalysisStore } from '../../stores/useSpatialAnalysisStore';
import type { RasterFormulaNode, RasterStyle } from '../../types/imports';
import type { BasemapProvider, FeatureAttributePreview, WorkspaceLayer } from '../../types/workspace';
import { normalizeBackendLayer } from '../layers/backendLayer';
import { supportsRasterWebGLPreview } from '../rasters/formulaParser';
import { MapToolbox } from './MapToolbox';
import { MapSwipeDivider } from './MapSwipeDivider';
import { createFirstVertexInteraction, resolveDrawingTarget } from './polygonEditing';

type BasemapSource = OSM | XYZ;
type MapFeatureGeometry = Point | Polygon;
type BackendFeature = Feature<Geometry>;

interface BackendLayerFocusDetail {
  name: string;
  bounds: Record<string, number>;
}

interface RasterRuntime {
  layer: WebGLTileLayer;
  sourceKey: string;
}

const featureStyleCache = new globalThis.Map<string, Style>();

const rasterColorRamps: Record<string, string[]> = {
  magma: ['#140e36', '#5a167c', '#b73779', '#f37f44', '#fcfdbf'],
  viridis: ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'],
  plasma: ['#0d0887', '#7e03a8', '#cc4778', '#f89540', '#f0f921'],
  cividis: ['#00224e', '#35456c', '#6c6e72', '#a59c74', '#fee838'],
};

function collectFormulaBands(node: RasterFormulaNode | null, bands = new Set<number>()) {
  if (!node) return bands;
  if (node.kind === 'band') bands.add(node.band);
  if (node.kind === 'unary') collectFormulaBands(node.argument, bands);
  if (node.kind === 'binary') {
    collectFormulaBands(node.left, bands);
    collectFormulaBands(node.right, bands);
  }
  if (node.kind === 'function') node.arguments.forEach((argument) => collectFormulaBands(argument, bands));
  return bands;
}

function formulaExpression(node: RasterFormulaNode, sourceBands: number[]): unknown {
  if (node.kind === 'band') return ['band', Math.max(1, sourceBands.indexOf(node.band) + 1)];
  if (node.kind === 'number') return node.value;
  if (node.kind === 'unary') {
    const value = formulaExpression(node.argument, sourceBands);
    return node.operator === '-' ? ['*', -1, value] : value;
  }
  if (node.kind === 'binary') {
    return [
      node.operator,
      formulaExpression(node.left, sourceBands),
      formulaExpression(node.right, sourceBands),
    ];
  }
  const values = node.arguments.map((argument) => formulaExpression(argument, sourceBands));
  if (node.name === 'min') return ['case', ['<=', values[0], values[1]], values[0], values[1]];
  if (node.name === 'max') return ['case', ['>=', values[0], values[1]], values[0], values[1]];
  if (node.name === 'clamp') return ['clamp', values[0], values[1], values[2]];
  if (node.name === 'log') throw new Error('OpenLayers WebGL 不支持 log 公式预览。');
  return [node.name, values[0]];
}

function rasterSourceBands(style: RasterStyle) {
  if (style.mode === 'formula' && style.formula) {
    return Array.from(collectFormulaBands(style.formula)).sort((left, right) => left - right);
  }
  return style.bands;
}

function rasterWebGLStyle(style: RasterStyle): WebGLTileStyle {
  const webglStyle: WebGLTileStyle = {
    gamma: style.gamma,
    saturation: style.mode === 'grayscale' ? -1 : 0,
    contrast: style.stretch === 'percentile' ? 0.08 : 0,
  };
  if (style.mode === 'classified') {
    const colors = rasterColorRamps[style.color_ramp] ?? rasterColorRamps.magma;
    webglStyle.color = [
      'interpolate',
      ['linear'],
      ['band', 1],
      0,
      colors[0],
      0.25,
      colors[1],
      0.5,
      colors[2],
      0.75,
      colors[3],
      1,
      colors[4],
    ];
  } else if (
    style.mode === 'formula' &&
    style.formula &&
    supportsRasterWebGLPreview(style.formula)
  ) {
    const bands = rasterSourceBands(style);
    const value = ['clamp', ['/', ['+', formulaExpression(style.formula, bands), 1], 2], 0, 1];
    webglStyle.color = ['array', value, value, value, 1];
  }
  return webglStyle;
}

function createRasterSource(layer: WorkspaceLayer) {
  const style = layer.rasterStyle;
  if (!layer.raster || !style) return null;
  return new GeoTIFFSource({
    sources: [{ url: resolveApiUrl(layer.raster.asset_url), bands: rasterSourceBands(style) }],
    normalize: style.stretch !== 'none',
    convertToRGB: 'auto',
    interpolate: true,
    transition: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 120,
    sourceOptions: {
      allowFullFile: false,
      maxRanges: 1,
      blockSize: 64 * 1024,
      cacheSize: 48,
    },
  });
}

function getAnalysisOverlayStyle(feature: FeatureLike) {
  const kind = String(feature.get('analysisKind'));
  if (kind === 'target') {
    return new Style({
      fill: new Fill({ color: 'rgba(181, 124, 42, 0.18)' }),
      stroke: new Stroke({ color: '#a66a18', width: 3 }),
    });
  }
  if (kind === 'hit') {
    return new Style({
      fill: new Fill({ color: 'rgba(87, 72, 156, 0.16)' }),
      stroke: new Stroke({ color: '#57489c', width: 2 }),
    });
  }
  return new Style({
    fill: new Fill({ color: 'rgba(70, 86, 168, 0.08)' }),
    stroke: new Stroke({ color: '#4656a8', width: 2, lineDash: [7, 5] }),
  });
}

function buildProviderUrls(provider: BasemapProvider): string[] | undefined {
  if (!provider.urlTemplate) {
    return undefined;
  }
  const subdomains = provider.subdomains.length > 0 ? provider.subdomains : [''];
  return subdomains.map((subdomain) =>
    provider.urlTemplate
      .replace('{s}', subdomain)
      .replace('{api_key}', provider.apiKey)
      .replace('{apiKey}', provider.apiKey),
  );
}

function createBasemapSource(provider?: BasemapProvider) {
  const urls = provider ? buildProviderUrls(provider) : undefined;
  if (!urls || urls.length === 0) {
    return new OSM();
  }
  return new XYZ({
    urls,
    crossOrigin: 'anonymous',
  });
}

function canClipCanvas(
  context: RenderEvent['context'],
): context is CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D {
  return Boolean(
    context &&
      'save' in context &&
      'restore' in context &&
      'beginPath' in context &&
      'rect' in context &&
      'clip' in context,
  );
}

function featureExtent(feature: FeatureAttributePreview) {
  const extent = transformExtent(feature.mapBounds, 'EPSG:4326', 'EPSG:3857');
  const isPointExtent = extent[0] === extent[2] && extent[1] === extent[3];
  return isPointExtent ? buffer(extent, 480) : extent;
}

function featureGeometry(feature: FeatureAttributePreview): MapFeatureGeometry {
  if (feature.geometryType === 'Point') {
    return new Point(fromLonLat([feature.mapBounds[0], feature.mapBounds[1]]));
  }
  return polygonFromExtent(featureExtent(feature));
}

function createOverlayFeature(feature: FeatureAttributePreview) {
  const overlayFeature = new Feature<MapFeatureGeometry>({
    geometry: featureGeometry(feature),
  });
  overlayFeature.setId(feature.id);
  overlayFeature.setProperties({
    displayCode: feature.displayCode,
    geometryType: feature.geometryType,
    layerId: feature.layerId,
    title: feature.title,
  });
  return overlayFeature;
}

function hexToRgba(hex: string, alpha: number) {
  const normalized = hex.replace('#', '');
  const full =
    normalized.length === 3
      ? normalized
          .split('')
          .map((char) => `${char}${char}`)
          .join('')
      : normalized;
  const value = Number.parseInt(full, 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function getFeatureStyle(feature: FeatureLike, layers: WorkspaceLayer[], selectedFeatureId: string | null) {
  const layerId = String(feature.get('layerId'));
  const geometryType = String(feature.get('geometryType'));
  const layer = layers.find((item) => item.id === layerId);
  if (!layer?.visible) {
    return undefined;
  }

  const selected = feature.getId() === selectedFeatureId;
  const color = layer.color;
  const opacity = layer.opacity;
  const cacheKey = `${geometryType}:${color}:${opacity}:${selected}`;
  const cached = featureStyleCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const style =
    geometryType === 'Point'
      ? new Style({
          image: new CircleStyle({
            radius: selected ? 8 : 6,
            fill: new Fill({ color: hexToRgba(color, selected ? 0.92 : 0.72) }),
            stroke: new Stroke({
              color: selected ? '#ffffff' : hexToRgba('#1f2a44', 0.62),
              width: selected ? 3 : 2,
            }),
          }),
        })
      : new Style({
          fill: new Fill({ color: hexToRgba(color, selected ? 0.22 : 0.12 * opacity) }),
          stroke: new Stroke({
            color: hexToRgba(color, selected ? 0.96 : 0.72 * opacity),
            width: selected ? 3 : 1.6,
          }),
        });
  featureStyleCache.set(cacheKey, style);
  return style;
}

function estimateScale(zoom: number) {
  const denominator = Math.max(500, Math.round(591657550.5 / 2 ** zoom));
  return `1:${denominator.toLocaleString('zh-CN')}`;
}

export function MapCanvas() {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<Map | null>(null);
  const baseLayerRef = useRef<TileLayer<BasemapSource> | null>(null);
  const swipeLayerRef = useRef<TileLayer<BasemapSource> | null>(null);
  const featureLayerRef = useRef<VectorLayer<VectorSource<Feature<MapFeatureGeometry>>> | null>(null);
  const analysisOverlayLayerRef = useRef<VectorLayer<VectorSource<Feature<Geometry>>> | null>(null);
  const backendLayersRef = useRef(
    new globalThis.Map<string, VectorLayer<VectorSource<BackendFeature>>>(),
  );
  const rasterLayersRef = useRef(new globalThis.Map<string, RasterRuntime>());
  const warnedRasterFormulaIdsRef = useRef(new Set<string>());
  const backendAbortRef = useRef<AbortController | null>(null);
  const truncatedLayerIdsRef = useRef(new Set<string>());
  const drawInteractionRef = useRef<Draw | null>(null);
  const workspacePickInteractionRef = useRef<SelectInteraction | null>(null);
  const analysisSelectInteractionRef = useRef<SelectInteraction | null>(null);
  const drawingStartedRef = useRef(false);
  const drawingSavingRef = useRef(false);
  const creatingLayerRef = useRef(false);
  const [mapReady, setMapReady] = useState(0);
  const [drawingTargetLayerId, setDrawingTargetLayerId] = useState<string | null>(null);
  const selectedBasemapRef = useRef<BasemapProvider | undefined>(undefined);
  const basemapsRef = useRef<BasemapProvider[]>([]);
  const layersRef = useRef<WorkspaceLayer[]>([]);
  const selectedFeatureIdRef = useRef<string | null>(null);
  const imagerySwipeRef = useRef(useMapStore.getState().imagerySwipe);
  const selectedBasemapId = useMapStore((state) => state.selectedBasemapId);
  const imagerySwipe = useMapStore((state) => state.imagerySwipe);
  const setViewState = useMapStore((state) => state.setViewState);
  const setSwipePosition = useMapStore((state) => state.setSwipePosition);
  const basemaps = useSettingsStore((state) => state.basemaps);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const toolActivationSequence = useWorkspaceStore((state) => state.toolActivationSequence);
  const workspaceMode = useWorkspaceStore((state) => state.workspaceMode);
  const selectedFeatureId = useWorkspaceStore((state) => state.selectedFeatureId);
  const featureFocusRequest = useWorkspaceStore((state) => state.featureFocusRequest);
  const featurePreviews = useWorkspaceStore((state) => state.featurePreviews);
  const layers = useWorkspaceStore((state) => state.layers);
  const currentWorkspace = useWorkspaceContextStore((state) => state.current);
  const analysisTarget = useSpatialAnalysisStore((state) => state.target);
  const analysisResult = useSpatialAnalysisStore((state) => state.result);
  const analysisHits = useSpatialAnalysisStore((state) => state.hits);
  const selectAnalysisFeature = useSpatialAnalysisStore((state) => state.selectFeature);
  const exitSpatialAnalysis = useSpatialAnalysisStore((state) => state.exit);
  const analysisDrawerOpen = useSpatialAnalysisStore((state) => state.drawerOpen);
  const openFeatureInspector = useWorkspaceStore((state) => state.openFeatureInspector);
  const setActiveTool = useWorkspaceStore((state) => state.setActiveTool);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const upsertBackendLayer = useWorkspaceStore((state) => state.upsertBackendLayer);
  const selectedBasemap = useMemo(
    () => basemaps.find((provider) => provider.id === selectedBasemapId),
    [basemaps, selectedBasemapId],
  );
  const beforeBasemap = useMemo(
    () => basemaps.find((provider) => provider.id === imagerySwipe.beforeBasemapId) ?? selectedBasemap,
    [basemaps, imagerySwipe.beforeBasemapId, selectedBasemap],
  );
  const afterBasemap = useMemo(
    () => basemaps.find((provider) => provider.id === imagerySwipe.afterBasemapId) ?? selectedBasemap,
    [basemaps, imagerySwipe.afterBasemapId, selectedBasemap],
  );
  selectedBasemapRef.current = selectedBasemap;
  basemapsRef.current = basemaps;
  layersRef.current = layers;
  selectedFeatureIdRef.current = selectedFeatureId;
  imagerySwipeRef.current = imagerySwipe;
  const activeBasemapLabel = imagerySwipe.enabled
    ? `${beforeBasemap?.name ?? 'OSM'} / ${afterBasemap?.name ?? 'OSM'}`
    : selectedBasemap?.name ?? 'OSM';
  const previewFeature =
    featurePreviews.find((feature) => feature.id === selectedFeatureId) ??
    featurePreviews.find((feature) => feature.layerId === selectedLayerId) ??
    featurePreviews[0];

  useEffect(() => {
    if (!mapRef.current) {
      return;
    }

    let map: Map | null = null;
    let timeoutId: number | null = null;
    let handleMoveEnd: (() => void) | null = null;
    const frameId = window.requestAnimationFrame(() => {
      timeoutId = window.setTimeout(() => {
        if (!mapRef.current) {
          return;
        }
        const currentSwipe = imagerySwipeRef.current;
        const currentBasemaps = basemapsRef.current;
        const initialBeforeBasemap =
          currentBasemaps.find((provider) => provider.id === currentSwipe.beforeBasemapId) ??
          selectedBasemapRef.current;
        const initialAfterBasemap =
          currentBasemaps.find((provider) => provider.id === currentSwipe.afterBasemapId) ??
          selectedBasemapRef.current;
        const baseLayer = new TileLayer<BasemapSource>({
          source: createBasemapSource(currentSwipe.enabled ? initialBeforeBasemap : selectedBasemapRef.current),
        });
        const swipeLayer = new TileLayer<BasemapSource>({
          source: createBasemapSource(initialAfterBasemap),
          visible: currentSwipe.enabled,
        });
        const featureSource = new VectorSource<Feature<MapFeatureGeometry>>({
          features: useWorkspaceStore.getState().featurePreviews.map(createOverlayFeature),
          useSpatialIndex: true,
        });
        const featureLayer = new VectorLayer({
          source: featureSource,
          declutter: true,
          style: (feature) =>
            getFeatureStyle(
              feature,
              layersRef.current,
              selectedFeatureIdRef.current,
            ),
        });
        const analysisOverlayLayer = new VectorLayer({
          source: new VectorSource<Feature<Geometry>>({ useSpatialIndex: true }),
          style: getAnalysisOverlayStyle,
          zIndex: 90,
        });
        baseLayerRef.current = baseLayer;
        swipeLayerRef.current = swipeLayer;
        featureLayerRef.current = featureLayer;
        analysisOverlayLayerRef.current = analysisOverlayLayer;
        map = new Map({
          target: mapRef.current,
          layers: [baseLayer, swipeLayer, featureLayer, analysisOverlayLayer],
          view: new View({
            center: [12608500, 2644100],
            zoom: 10,
          }),
          controls: [],
        });
        handleMoveEnd = () => {
          if (!map) {
            return;
          }
          const view = map.getView();
          const center = view.getCenter();
          const zoom = view.getZoom() ?? 10;
          if (!center) {
            return;
          }
          const [longitude, latitude] = toLonLat(center);
          setViewState({
            coordinate: [
              Number(longitude.toFixed(6)),
              Number(latitude.toFixed(6)),
            ],
            viewCenter: [Number(center[0].toFixed(3)), Number(center[1].toFixed(3))],
            zoom: Number(zoom.toFixed(2)),
            scale: estimateScale(zoom),
          });
        };
        map.on('moveend', handleMoveEnd);
        handleMoveEnd();
        mapInstanceRef.current = map;
        setMapReady((value) => value + 1);
      }, 0);
    });

    return () => {
      window.cancelAnimationFrame(frameId);
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      if (handleMoveEnd) {
        map?.un('moveend', handleMoveEnd);
      }
      map?.setTarget(undefined);
      mapInstanceRef.current = null;
      baseLayerRef.current = null;
      swipeLayerRef.current = null;
      featureLayerRef.current = null;
      analysisOverlayLayerRef.current = null;
      backendAbortRef.current?.abort();
      backendLayersRef.current.clear();
      rasterLayersRef.current.clear();
    };
  }, [setViewState]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapReady === 0 || !currentWorkspace) return;
    map.getView().setCenter(currentWorkspace.view.center);
    map.getView().setZoom(currentWorkspace.view.zoom);
    map.render();
  }, [currentWorkspace?.id, currentWorkspace?.revision, mapReady]);

  useEffect(() => {
    if (!mapRef.current || typeof ResizeObserver === 'undefined') {
      return;
    }
    let frameId: number | null = null;
    const observer = new ResizeObserver(() => {
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      frameId = window.requestAnimationFrame(() => {
        mapInstanceRef.current?.updateSize();
      });
    });
    observer.observe(mapRef.current);

    return () => {
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    const baseLayer = baseLayerRef.current;
    const swipeLayer = swipeLayerRef.current;
    if (!map || !baseLayer || !swipeLayer) {
      return;
    }
    baseLayer.setSource(createBasemapSource(imagerySwipe.enabled ? beforeBasemap : selectedBasemap));
    swipeLayer.setSource(createBasemapSource(afterBasemap));
    swipeLayer.setVisible(imagerySwipe.enabled);
    map.render();
  }, [afterBasemap, beforeBasemap, imagerySwipe.enabled, selectedBasemap]);

  useEffect(() => {
    const featureLayer = featureLayerRef.current;
    if (!featureLayer) {
      return;
    }
    const source = featureLayer.getSource();
    if (!source) {
      return;
    }
    source.clear(true);
    source.addFeatures(featurePreviews.map(createOverlayFeature));
    featureLayer.changed();
  }, [featurePreviews]);

  useEffect(() => {
    featureLayerRef.current?.changed();
    mapInstanceRef.current?.render();
  }, [layers, selectedFeatureId]);

  useEffect(() => {
    if (workspaceMode !== 'edit' || activeTool !== 'draw') {
      setDrawingTargetLayerId(null);
      return;
    }

    const resolution = resolveDrawingTarget(layers, selectedLayerId);
    if (resolution.kind === 'blocked') {
      setDrawingTargetLayerId(null);
      showNotice({
        tone: 'warning',
        title: '无法在当前图层绘制',
        detail: resolution.message,
      });
      return;
    }
    if (resolution.kind === 'ready') {
      setDrawingTargetLayerId(resolution.layer.id);
      return;
    }
    if (creatingLayerRef.current) return;

    creatingLayerRef.current = true;
    setDrawingTargetLayerId(null);
    showNotice({
      tone: 'info',
      title: '正在创建图斑图层',
      detail: '当前没有选中真实面图层，正在创建新的 Polygon 图层。',
    });
    void createManualLayer()
      .then((layer) => {
        const current = useWorkspaceStore.getState();
        if (current.workspaceMode !== 'edit' || current.activeTool !== 'draw') return;
        const normalized = normalizeBackendLayer(layer);
        upsertBackendLayer(normalized, true);
        showNotice({
          tone: 'success',
          title: `已创建 ${normalized.name}`,
          detail: '请在地图中双击建立第一个顶点。',
        });
      })
      .catch((error) => {
        showNotice({
          tone: 'warning',
          title: '图斑图层创建失败',
          detail: error instanceof Error ? error.message : '后端未能创建 Polygon 图层。',
        });
      })
      .finally(() => {
        creatingLayerRef.current = false;
      });
  }, [
    activeTool,
    layers,
    selectedLayerId,
    showNotice,
    toolActivationSequence,
    upsertBackendLayer,
    workspaceMode,
  ]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapReady === 0) return;
    const backendLayers = layers.filter(
      (layer) => layer.source === 'backend' && layer.kind !== 'raster',
    );
    const activeIds = new Set(backendLayers.map((layer) => layer.id));

    for (const [layerId, vectorLayer] of backendLayersRef.current) {
      if (!activeIds.has(layerId)) {
        map.removeLayer(vectorLayer);
        backendLayersRef.current.delete(layerId);
      }
    }

    for (const workspaceLayer of backendLayers) {
      let vectorLayer = backendLayersRef.current.get(workspaceLayer.id);
      if (!vectorLayer) {
        vectorLayer = new VectorLayer({
          source: new VectorSource<BackendFeature>({ useSpatialIndex: true }),
          declutter: true,
          style: (feature) =>
            getFeatureStyle(feature, layersRef.current, selectedFeatureIdRef.current),
        });
        vectorLayer.setZIndex(40);
        backendLayersRef.current.set(workspaceLayer.id, vectorLayer);
        const insertAt = Math.max(0, map.getLayers().getLength() - 1);
        map.getLayers().insertAt(insertAt, vectorLayer);
      }
      vectorLayer.setVisible(workspaceLayer.visible);
      vectorLayer.setOpacity(workspaceLayer.opacity);
      vectorLayer.changed();
    }
  }, [layers, mapReady]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapReady === 0) return;
    const rasterLayers = layers.filter(
      (layer) => layer.source === 'backend' && layer.kind === 'raster' && layer.rasterStyle,
    );
    const activeIds = new Set(rasterLayers.map((layer) => layer.id));
    for (const [layerId, runtime] of rasterLayersRef.current) {
      if (!activeIds.has(layerId)) {
        map.removeLayer(runtime.layer);
        runtime.layer.setSource(null);
        rasterLayersRef.current.delete(layerId);
      }
    }
    for (const workspaceLayer of rasterLayers) {
      const formula = workspaceLayer.rasterStyle?.formula;
      const previewUnsupported = Boolean(
        workspaceLayer.rasterStyle?.mode === 'formula' &&
        formula &&
        !supportsRasterWebGLPreview(formula),
      );
      if (previewUnsupported && !warnedRasterFormulaIdsRef.current.has(workspaceLayer.id)) {
        warnedRasterFormulaIdsRef.current.add(workspaceLayer.id);
        showNotice({
          tone: 'warning',
          title: `${workspaceLayer.name} 公式仅支持后端物化`,
          detail: '当前 WebGL 不支持 log，即时预览已关闭，不会退化为错误波段。',
        });
      } else if (!previewUnsupported) {
        warnedRasterFormulaIdsRef.current.delete(workspaceLayer.id);
      }
      const sourceKey = `${workspaceLayer.raster?.fingerprint ?? ''}:${JSON.stringify(
        rasterSourceBands(workspaceLayer.rasterStyle!),
      )}:${workspaceLayer.rasterStyle?.stretch}`;
      let runtime = rasterLayersRef.current.get(workspaceLayer.id);
      if (!runtime) {
        const source = createRasterSource(workspaceLayer);
        if (!source) continue;
        const webglLayer = new WebGLTileLayer({
          source,
          style: rasterWebGLStyle(workspaceLayer.rasterStyle!),
          visible: workspaceLayer.visible,
          opacity: workspaceLayer.opacity,
          cacheSize: 256,
        });
        webglLayer.setZIndex(20);
        runtime = { layer: webglLayer, sourceKey };
        rasterLayersRef.current.set(workspaceLayer.id, runtime);
        map.getLayers().insertAt(Math.min(2, map.getLayers().getLength()), webglLayer);
      } else if (runtime.sourceKey !== sourceKey) {
        const source = createRasterSource(workspaceLayer);
        if (source) {
          runtime.layer.setSource(source);
          runtime.sourceKey = sourceKey;
        }
      }
      runtime.layer.setStyle(rasterWebGLStyle(workspaceLayer.rasterStyle!));
      runtime.layer.setVisible(workspaceLayer.visible);
      runtime.layer.setOpacity(workspaceLayer.opacity);
    }
    map.render();
  }, [layers, mapReady, showNotice]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapReady === 0 || workspaceMode !== 'analysis') return;
    const selectableLayers = layers
      .filter((layer) => layer.source === 'backend' && layer.kind !== 'raster' && layer.visible)
      .map((layer) => backendLayersRef.current.get(layer.id))
      .filter((layer): layer is VectorLayer<VectorSource<BackendFeature>> => Boolean(layer));
    const interaction = new SelectInteraction({ layers: selectableLayers, hitTolerance: 7 });
    interaction.on('select', (event) => {
      const feature = event.selected[0];
      const parts = String(feature?.getId() ?? '').split(':');
      const featureId = Number(parts.at(-1));
      const layerId = Number(parts.at(-2));
      if (!Number.isInteger(featureId) || !Number.isInteger(layerId)) return;
      void selectAnalysisFeature(layerId, featureId)
        .then(() => showNotice({
          tone: 'success',
          title: '已选择分析目标',
          detail: `图层 ${layerId} · 图斑 ${featureId}`,
        }))
        .catch(() => undefined);
    });
    analysisSelectInteractionRef.current = interaction;
    map.addInteraction(interaction);
    return () => {
      interaction.getFeatures().clear();
      map.removeInteraction(interaction);
      if (analysisSelectInteractionRef.current === interaction) {
        analysisSelectInteractionRef.current = null;
      }
    };
  }, [layers, mapReady, selectAnalysisFeature, showNotice, workspaceMode]);

  useEffect(() => {
    const source = analysisOverlayLayerRef.current?.getSource();
    if (!source) return;
    source.clear(true);
    const addGeometry = (geometry: unknown, kind: 'target' | 'buffer' | 'hit', id: string) => {
      if (!geometry) return;
      const feature = new GeoJSON().readFeature(
        { type: 'Feature', id, geometry, properties: { analysisKind: kind } },
        { dataProjection: 'EPSG:3857', featureProjection: 'EPSG:3857' },
      ) as Feature<Geometry>;
      feature.set('analysisKind', kind);
      source.addFeature(feature);
    };
    addGeometry(analysisTarget?.geometry ?? analysisResult?.target_geometry, 'target', 'analysis-target');
    addGeometry(analysisResult?.buffer_geometry, 'buffer', 'analysis-buffer');
    for (const hit of analysisHits) {
      addGeometry(hit.geometry, 'hit', `analysis-hit-${hit.layer_id}-${hit.feature_id}`);
    }
    analysisOverlayLayerRef.current?.changed();
  }, [
    analysisHits,
    analysisResult?.buffer_geometry,
    analysisResult?.target_geometry,
    analysisTarget?.geometry,
    mapReady,
  ]);

  useEffect(() => {
    if (workspaceMode !== 'analysis' || analysisDrawerOpen) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') exitSpatialAnalysis();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [analysisDrawerOpen, exitSpatialAnalysis, workspaceMode]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapReady === 0) return;
    const clearPicker = () => {
      const interaction = workspacePickInteractionRef.current;
      if (interaction) map.removeInteraction(interaction);
      workspacePickInteractionRef.current = null;
    };
    const handleStartPick = (event: Event) => {
      const layerId = String((event as CustomEvent<{ layerId: number }>).detail?.layerId ?? '');
      const vectorLayer = backendLayersRef.current.get(layerId);
      clearPicker();
      if (!vectorLayer) {
        showNotice({ tone: 'warning', title: '图层不可拾取', detail: '请先显示并加载该工作空间图层。' });
        return;
      }
      const interaction = new SelectInteraction({
        layers: [vectorLayer],
        hitTolerance: 6,
      });
      interaction.once('select', (selectEvent) => {
        const feature = selectEvent.selected[0];
        const featureId = Number(String(feature?.getId() ?? '').split(':').at(-1));
        if (Number.isInteger(featureId)) {
          window.dispatchEvent(new CustomEvent('womap:workspace-feature-picked', {
            detail: { layerId: Number(layerId), featureId },
          }));
          showNotice({ tone: 'success', title: '已加入指定图斑', detail: `图斑 ${featureId}` });
        }
        clearPicker();
      });
      workspacePickInteractionRef.current = interaction;
      map.addInteraction(interaction);
      showNotice({ tone: 'info', title: '地图拾取已启用', detail: '点击目标图斑加入工作空间选择。' });
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') clearPicker();
    };
    window.addEventListener('womap:start-workspace-feature-pick', handleStartPick);
    window.addEventListener('keydown', handleEscape);
    return () => {
      window.removeEventListener('womap:start-workspace-feature-pick', handleStartPick);
      window.removeEventListener('keydown', handleEscape);
      clearPicker();
    };
  }, [mapReady, showNotice]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (
      !map ||
      mapReady === 0 ||
      workspaceMode !== 'edit' ||
      activeTool !== 'draw' ||
      !drawingTargetLayerId
    ) {
      return;
    }

    const draw = new Draw({ type: 'Polygon', stopClick: true });
    draw.setActive(false);
    drawingStartedRef.current = false;
    drawingSavingRef.current = false;
    const starter = createFirstVertexInteraction(
      draw,
      () => !drawingStartedRef.current && !drawingSavingRef.current,
      () => {
        drawingStartedRef.current = true;
        showNotice({
          tone: 'info',
          title: '已建立图斑起点',
          detail: '继续单击添加顶点，至少三个顶点后双击完成。',
        });
      },
    );

    const handleDrawAbort = () => {
      drawingStartedRef.current = false;
      draw.setActive(false);
    };
    const handleDrawEnd = (event: DrawEvent) => {
      const geometry = event.feature.getGeometry();
      if (!(geometry instanceof Polygon)) {
        handleDrawAbort();
        return;
      }
      drawingSavingRef.current = true;
      draw.setActive(false);
      void createLayerFeature(
        drawingTargetLayerId,
        geometry.getCoordinates() as number[][][],
      )
        .then((response) => {
          const normalizedLayer = normalizeBackendLayer(response.layer);
          const savedFeature = new GeoJSON().readFeature(
            {
              type: 'Feature',
              id: response.feature.id,
              geometry: response.feature.geometry,
              properties: response.feature.properties,
            },
            { dataProjection: 'EPSG:3857', featureProjection: 'EPSG:3857' },
          ) as BackendFeature;
          savedFeature.set('layerId', normalizedLayer.id);
          savedFeature.set('geometryType', normalizedLayer.geometryType);
          savedFeature.setId(`backend:${normalizedLayer.id}:${response.feature.id}`);
          backendLayersRef.current
            .get(normalizedLayer.id)
            ?.getSource()
            ?.addFeature(savedFeature);
          upsertBackendLayer(normalizedLayer, true);
          showNotice({
            tone: 'success',
            title: '图斑已保存',
            detail: `${normalizedLayer.name} 现有 ${normalizedLayer.featureCount} 个要素。`,
          });
        })
        .catch((error) => {
          showNotice({
            tone: 'warning',
            title: '图斑保存失败',
            detail: error instanceof Error ? error.message : '后端未能保存当前 Polygon。',
          });
        })
        .finally(() => {
          drawingSavingRef.current = false;
          drawingStartedRef.current = false;
          draw.setActive(false);
        });
    };

    draw.on('drawabort', handleDrawAbort);
    draw.on('drawend', handleDrawEnd);
    map.addInteraction(draw);
    map.addInteraction(starter);
    drawInteractionRef.current = draw;

    return () => {
      draw.abortDrawing();
      draw.un('drawabort', handleDrawAbort);
      draw.un('drawend', handleDrawEnd);
      map.removeInteraction(starter);
      map.removeInteraction(draw);
      if (drawInteractionRef.current === draw) drawInteractionRef.current = null;
      drawingStartedRef.current = false;
    };
  }, [
    activeTool,
    drawingTargetLayerId,
    mapReady,
    showNotice,
    toolActivationSequence,
    upsertBackendLayer,
    workspaceMode,
  ]);

  useEffect(() => {
    if (workspaceMode !== 'edit' || activeTool !== 'draw') return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      drawInteractionRef.current?.abortDrawing();
      drawingStartedRef.current = false;
      setActiveTool('select');
      showNotice({
        tone: 'info',
        title: '已取消图斑绘制',
        detail: '草图已清除，地图恢复普通选择。',
      });
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [activeTool, setActiveTool, showNotice, workspaceMode]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapReady === 0) return;
    let timer: number | null = null;
    let disposed = false;
    const loadViewport = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const size = map.getSize();
        if (!size || disposed) return;
        const extent = map.getView().calculateExtent(size);
        const bbox = extent.map((value) => Number(value.toFixed(3))).join(',');
        backendAbortRef.current?.abort();
        const controller = new AbortController();
        backendAbortRef.current = controller;
        const visibleLayers = layersRef.current.filter(
          (layer) => layer.source === 'backend' && layer.kind !== 'raster' && layer.visible,
        );
        void Promise.all(
          visibleLayers.map(async (workspaceLayer) => {
            const response = await getLayerFeatures(
              workspaceLayer.id,
              bbox,
              2000,
              controller.signal,
              useWorkspaceContextStore.getState().current?.id,
            );
            if (controller.signal.aborted || disposed) return;
            if (response.meta.truncated && !truncatedLayerIdsRef.current.has(workspaceLayer.id)) {
              truncatedLayerIdsRef.current.add(workspaceLayer.id);
              showNotice({
                tone: 'warning',
                title: `${workspaceLayer.name} 仅显示当前安全窗口`,
                detail: response.meta.warning ?? '请放大地图以查看更完整的图斑。',
              });
            } else if (!response.meta.truncated) {
              truncatedLayerIdsRef.current.delete(workspaceLayer.id);
            }
            const vectorLayer = backendLayersRef.current.get(workspaceLayer.id);
            const source = vectorLayer?.getSource();
            if (!source) return;
            const features = new GeoJSON().readFeatures(
              {
                type: 'FeatureCollection',
                features: (response.features as Array<{
                  id: number;
                  source_feature_id?: string | null;
                  geometry: unknown;
                  properties: Record<string, unknown>;
                }>).map((feature) => ({
                  type: 'Feature',
                  id: feature.id,
                  geometry: feature.geometry,
                  properties: {
                    ...feature.properties,
                    womapSourceFeatureId: feature.source_feature_id ?? null,
                  },
                })),
              },
              { dataProjection: 'EPSG:3857', featureProjection: 'EPSG:3857' },
            ) as BackendFeature[];
            for (const feature of features) {
              feature.set('layerId', workspaceLayer.id);
              feature.set('geometryType', workspaceLayer.geometryType);
              feature.setId(`backend:${workspaceLayer.id}:${feature.getId()}`);
            }
            source.clear(true);
            source.addFeatures(features);
            vectorLayer?.changed();
          }),
        ).catch((error) => {
          if (error instanceof DOMException && error.name === 'AbortError') return;
        });
      }, 180);
    };
    map.on('moveend', loadViewport);
    loadViewport();
    return () => {
      disposed = true;
      map.un('moveend', loadViewport);
      if (timer !== null) window.clearTimeout(timer);
      backendAbortRef.current?.abort();
    };
  }, [layers, mapReady, showNotice]);

  useEffect(() => {
    const handleFocusLayer = (event: Event) => {
      const map = mapInstanceRef.current;
      const detail = (event as CustomEvent<BackendLayerFocusDetail>).detail;
      if (!map || !detail?.bounds) return;
      const { min_x: minX, min_y: minY, max_x: maxX, max_y: maxY } = detail.bounds;
      if (![minX, minY, maxX, maxY].every(Number.isFinite)) return;
      let extent: Extent = [minX, minY, maxX, maxY];
      if (minX === maxX || minY === maxY) extent = buffer(extent, 480);
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      map.getView().fit(extent, {
        duration: reducedMotion ? 0 : 360,
        maxZoom: 16,
        padding: [64, 64, 64, 64],
      });
      showNotice({
        tone: 'success',
        title: `已定位 ${detail.name}`,
        detail: '地图已切换到新导入图层的范围。',
      });
    };
    window.addEventListener('womap:focus-backend-layer', handleFocusLayer);
    return () => window.removeEventListener('womap:focus-backend-layer', handleFocusLayer);
  }, [showNotice]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapReady === 0) return;
    let pixelClick: ((event: MapBrowserEvent) => void) | null = null;
    const cancel = () => {
      if (pixelClick) map.un('singleclick', pixelClick);
      pixelClick = null;
    };
    const handleStart = (event: Event) => {
      const layerId = Number((event as CustomEvent<{ layerId: number }>).detail?.layerId);
      if (!Number.isInteger(layerId)) return;
      cancel();
      pixelClick = (mapEvent) => {
        cancel();
        const [x, y] = mapEvent.coordinate;
        void getRasterPixel(layerId, x, y)
          .then((pixel) => {
            window.dispatchEvent(new CustomEvent('womap:raster-pixel-picked', { detail: pixel }));
            showNotice({
              tone: 'success',
              title: pixel.nodata ? '当前位置为 NoData' : '已读取像元',
              detail: pixel.nodata
                ? `${x.toFixed(2)}, ${y.toFixed(2)}`
                : pixel.values.map((value) => value === null ? '—' : Number(value).toFixed(3)).join(' · '),
            });
          })
          .catch((error) => showNotice({
            tone: 'warning',
            title: '像元读取失败',
            detail: error instanceof Error ? error.message : '当前坐标不在栅格范围内。',
          }));
      };
      map.once('singleclick', pixelClick);
      showNotice({ tone: 'info', title: '像元拾取已启用', detail: '请在地图影像范围内单击。' });
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') cancel();
    };
    window.addEventListener('womap:start-raster-pixel-pick', handleStart);
    window.addEventListener('keydown', handleEscape);
    return () => {
      cancel();
      window.removeEventListener('womap:start-raster-pixel-pick', handleStart);
      window.removeEventListener('keydown', handleEscape);
    };
  }, [mapReady, showNotice]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !featureFocusRequest) {
      return;
    }
    const feature = featurePreviews.find((item) => item.id === featureFocusRequest.featureId);
    if (!feature) {
      return;
    }
    const extent = featureExtent(feature);
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const view = map.getView();
    view.fit(extent, {
      duration: reducedMotion ? 0 : 360,
      maxZoom: feature.geometryType === 'Point' ? 15 : 14,
      padding: [72, 72, 72, 72],
    });
    const center = getCenter(extent);
    const [longitude, latitude] = toLonLat(center);
    setViewState({
      coordinate: [Number(longitude.toFixed(6)), Number(latitude.toFixed(6))],
      zoom: Number((view.getZoom() ?? 10).toFixed(2)),
      scale: estimateScale(view.getZoom() ?? 10),
    });
  }, [featureFocusRequest, featurePreviews, setViewState]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    const swipeLayer = swipeLayerRef.current;
    if (!map || !swipeLayer || !imagerySwipe.enabled) {
      return;
    }

    const handlePreRender = (event: RenderEvent) => {
      const context = event.context;
      if (!canClipCanvas(context)) {
        return;
      }
      const mapSize = map.getSize();
      if (!mapSize) {
        return;
      }
      const width = Math.round((mapSize[0] * imagerySwipe.position) / 100);
      const topLeft = getRenderPixel(event, [width, 0]);
      const bottomRight = getRenderPixel(event, mapSize);
      context.save();
      context.beginPath();
      context.rect(
        topLeft[0],
        topLeft[1],
        bottomRight[0] - topLeft[0],
        bottomRight[1] - topLeft[1],
      );
      context.clip();
    };

    const handlePostRender = (event: RenderEvent) => {
      const context = event.context;
      if (canClipCanvas(context)) {
        context.restore();
      }
    };

    swipeLayer.on('prerender', handlePreRender);
    swipeLayer.on('postrender', handlePostRender);
    map.render();

    return () => {
      swipeLayer.un('prerender', handlePreRender);
      swipeLayer.un('postrender', handlePostRender);
      map.render();
    };
  }, [imagerySwipe.enabled, imagerySwipe.position]);

  return (
    <main
      className={`map-shell ${workspaceMode === 'edit' && activeTool === 'draw' ? 'is-drawing' : ''}`}
    >
      <div className="map-frame" ref={mapRef} />
      <MapToolbox />
      {workspaceMode === 'analysis' && (
        <Button
          className="exit-analysis-button"
          icon={<X size={15} />}
          onClick={exitSpatialAnalysis}
        >
          退出空间分析
        </Button>
      )}
      <div className="map-floating-strip">
        <Tooltip title="当前底图">
          <span>
            <MapPinned size={14} aria-hidden="true" />
            {activeBasemapLabel}
          </span>
        </Tooltip>
        {imagerySwipe.enabled && (
          <Tooltip title="卷帘位置">
            <span>
              <Layers3 size={14} aria-hidden="true" />
              卷帘 {imagerySwipe.position}%
            </span>
          </Tooltip>
        )}
        <Tooltip title="视口查询策略">
          <span>
            <Layers3 size={14} aria-hidden="true" />
            bbox
          </span>
        </Tooltip>
        <Tooltip title="空间索引">
          <span>
            <DatabaseZap size={14} aria-hidden="true" />
            GiST
          </span>
        </Tooltip>
        {previewFeature && (
          <button
            type="button"
            className="map-feature-trigger"
            aria-label={`${previewFeature.displayCode} 查看示例图斑属性`}
            title="选中图斑"
            onClick={() => openFeatureInspector(previewFeature.layerId, previewFeature.id)}
          >
            <MousePointerSquareDashed size={14} aria-hidden="true" />
            {previewFeature.displayCode}
          </button>
        )}
      </div>
      {imagerySwipe.enabled && (
        <MapSwipeDivider position={imagerySwipe.position} onChange={setSwipePosition} />
      )}
    </main>
  );
}
