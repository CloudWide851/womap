import { Tooltip } from 'antd';
import { DatabaseZap, Layers3, MapPinned, MousePointerSquareDashed } from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';
import Feature from 'ol/Feature';
import { buffer, getCenter } from 'ol/extent';
import type { FeatureLike } from 'ol/Feature';
import Point from 'ol/geom/Point';
import Polygon from 'ol/geom/Polygon';
import { fromExtent as polygonFromExtent } from 'ol/geom/Polygon';
import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
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

import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { BasemapProvider, FeatureAttributePreview, WorkspaceLayer } from '../../types/workspace';

type BasemapSource = OSM | XYZ;
type MapFeatureGeometry = Point | Polygon;

const featureStyleCache = new globalThis.Map<string, Style>();

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
  const selectedBasemapRef = useRef<BasemapProvider | undefined>(undefined);
  const basemapsRef = useRef<BasemapProvider[]>([]);
  const layersRef = useRef<WorkspaceLayer[]>([]);
  const selectedFeatureIdRef = useRef<string | null>(null);
  const imagerySwipeRef = useRef(useMapStore.getState().imagerySwipe);
  const selectedBasemapId = useMapStore((state) => state.selectedBasemapId);
  const imagerySwipe = useMapStore((state) => state.imagerySwipe);
  const setViewState = useMapStore((state) => state.setViewState);
  const basemaps = useSettingsStore((state) => state.basemaps);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const selectedFeatureId = useWorkspaceStore((state) => state.selectedFeatureId);
  const featureFocusRequest = useWorkspaceStore((state) => state.featureFocusRequest);
  const featurePreviews = useWorkspaceStore((state) => state.featurePreviews);
  const layers = useWorkspaceStore((state) => state.layers);
  const openFeatureInspector = useWorkspaceStore((state) => state.openFeatureInspector);
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
        baseLayerRef.current = baseLayer;
        swipeLayerRef.current = swipeLayer;
        featureLayerRef.current = featureLayer;
        map = new Map({
          target: mapRef.current,
          layers: [baseLayer, swipeLayer, featureLayer],
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
            zoom: Number(zoom.toFixed(2)),
            scale: estimateScale(zoom),
          });
        };
        map.on('moveend', handleMoveEnd);
        handleMoveEnd();
        mapInstanceRef.current = map;
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
    };
  }, [setViewState]);

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
    <main className="map-shell">
      <div className="map-frame" ref={mapRef} />
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
        <div
          className="map-swipe-divider"
          style={{ left: `${imagerySwipe.position}%` }}
          aria-hidden="true"
        />
      )}
    </main>
  );
}
