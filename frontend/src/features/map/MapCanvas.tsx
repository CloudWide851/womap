import { useEffect, useRef } from 'react';
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
  const selectedBasemap = basemaps.find((provider) => provider.id === selectedBasemapId);

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
        <span>{selectedBasemap?.name ?? 'OSM'} 底图</span>
        <span>bbox 视口加载</span>
        <span>GiST 空间索引</span>
        <span>选中 0</span>
      </div>
    </main>
  );
}
