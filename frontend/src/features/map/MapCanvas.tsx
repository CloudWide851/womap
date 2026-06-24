import { Tooltip } from 'antd';
import { DatabaseZap, Layers3, MapPinned, MousePointerSquareDashed } from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';
import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import OSM from 'ol/source/OSM';
import XYZ from 'ol/source/XYZ';

import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import type { BasemapProvider } from '../../types/workspace';

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

export function MapCanvas() {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<Map | null>(null);
  const selectedBasemapId = useMapStore((state) => state.selectedBasemapId);
  const basemaps = useSettingsStore((state) => state.basemaps);
  const selectedBasemap = useMemo(
    () => basemaps.find((provider) => provider.id === selectedBasemapId),
    [basemaps, selectedBasemapId],
  );

  useEffect(() => {
    if (!mapRef.current) {
      return;
    }

    const baseLayer = new TileLayer({
      source: createBasemapSource(selectedBasemap),
    });
    const map = new Map({
      target: mapRef.current,
      layers: [baseLayer],
      view: new View({
        center: [12608500, 2644100],
        zoom: 10,
      }),
      controls: [],
    });
    mapInstanceRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) {
      return;
    }
    const baseLayer = map.getLayers().item(0) as TileLayer<OSM | XYZ>;
    baseLayer.setSource(createBasemapSource(selectedBasemap));
  }, [selectedBasemap]);

  return (
    <main className="map-shell">
      <div className="map-frame" ref={mapRef} />
      <div className="map-floating-strip">
        <Tooltip title="当前底图">
          <span>
            <MapPinned size={14} aria-hidden="true" />
            {selectedBasemap?.name ?? 'OSM'}
          </span>
        </Tooltip>
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
        <Tooltip title="选中图斑">
          <span>
            <MousePointerSquareDashed size={14} aria-hidden="true" />
            0
          </span>
        </Tooltip>
      </div>
    </main>
  );
}
