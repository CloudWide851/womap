import { Tooltip } from 'antd';
import { DatabaseZap, Layers3, MapPinned, MousePointerSquareDashed } from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';
import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import { getRenderPixel } from 'ol/render';
import type RenderEvent from 'ol/render/Event';
import OSM from 'ol/source/OSM';
import XYZ from 'ol/source/XYZ';

import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { BasemapProvider } from '../../types/workspace';

type BasemapSource = OSM | XYZ;

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

export function MapCanvas() {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<Map | null>(null);
  const baseLayerRef = useRef<TileLayer<BasemapSource> | null>(null);
  const swipeLayerRef = useRef<TileLayer<BasemapSource> | null>(null);
  const selectedBasemapRef = useRef<BasemapProvider | undefined>(undefined);
  const basemapsRef = useRef<BasemapProvider[]>([]);
  const imagerySwipeRef = useRef(useMapStore.getState().imagerySwipe);
  const selectedBasemapId = useMapStore((state) => state.selectedBasemapId);
  const imagerySwipe = useMapStore((state) => state.imagerySwipe);
  const basemaps = useSettingsStore((state) => state.basemaps);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
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
  imagerySwipeRef.current = imagerySwipe;
  const activeBasemapLabel = imagerySwipe.enabled
    ? `${beforeBasemap?.name ?? 'OSM'} / ${afterBasemap?.name ?? 'OSM'}`
    : selectedBasemap?.name ?? 'OSM';
  const previewFeature =
    selectedLayerId === 'survey-points'
      ? { id: 'feature-point-018', label: 'P-018' }
      : { id: 'feature-boundary-102', label: 'P-102' };

  useEffect(() => {
    if (!mapRef.current) {
      return;
    }

    let map: Map | null = null;
    let timeoutId: number | null = null;
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
        baseLayerRef.current = baseLayer;
        swipeLayerRef.current = swipeLayer;
        map = new Map({
          target: mapRef.current,
          layers: [baseLayer, swipeLayer],
          view: new View({
            center: [12608500, 2644100],
            zoom: 10,
          }),
          controls: [],
        });
        mapInstanceRef.current = map;
      }, 0);
    });

    return () => {
      window.cancelAnimationFrame(frameId);
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      map?.setTarget(undefined);
      mapInstanceRef.current = null;
      baseLayerRef.current = null;
      swipeLayerRef.current = null;
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
        <button
          type="button"
          className="map-feature-trigger"
          aria-label={`${previewFeature.label} 查看示例图斑属性`}
          title="选中图斑"
          disabled={!selectedLayerId}
          onClick={() => selectedLayerId && openFeatureInspector(selectedLayerId, previewFeature.id)}
        >
          <MousePointerSquareDashed size={14} aria-hidden="true" />
          {previewFeature.label}
        </button>
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
