import { useEffect, useRef } from 'react';
import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import OSM from 'ol/source/OSM';

export function MapCanvas() {
  const mapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!mapRef.current) {
      return;
    }

    const map = new Map({
      target: mapRef.current,
      layers: [
        new TileLayer({
          source: new OSM(),
        }),
      ],
      view: new View({
        center: [12608500, 2644100],
        zoom: 10,
      }),
      controls: [],
    });

    return () => {
      map.setTarget(undefined);
    };
  }, []);

  return (
    <main className="map-shell">
      <div className="map-frame" ref={mapRef} />
      <div className="map-floating-strip">
        <span>OSM 底图</span>
        <span>未保存编辑 0</span>
        <span>选中 0</span>
      </div>
    </main>
  );
}
