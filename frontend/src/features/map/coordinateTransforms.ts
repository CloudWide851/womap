import { transform } from 'ol/proj';

import type {
  CoordinateConversionInput,
  CoordinateConversionResult,
  CoordinateCrs,
} from '../../types/workspace';

interface CoordinateSystemMeta {
  id: CoordinateCrs;
  label: string;
  shortLabel: string;
  unit: 'degrees' | 'meters';
  xLabel: string;
  yLabel: string;
}

export const coordinateSystems: CoordinateSystemMeta[] = [
  {
    id: 'EPSG:4326',
    label: 'WGS84 经纬度',
    shortLabel: 'WGS84',
    unit: 'degrees',
    xLabel: '经度',
    yLabel: '纬度',
  },
  {
    id: 'EPSG:3857',
    label: 'Web Mercator 米',
    shortLabel: 'Web Mercator',
    unit: 'meters',
    xLabel: 'X',
    yLabel: 'Y',
  },
  {
    id: 'GCJ-02',
    label: 'GCJ-02 火星坐标',
    shortLabel: 'GCJ-02',
    unit: 'degrees',
    xLabel: '经度',
    yLabel: '纬度',
  },
  {
    id: 'BD-09',
    label: 'BD-09 百度坐标',
    shortLabel: 'BD-09',
    unit: 'degrees',
    xLabel: '经度',
    yLabel: '纬度',
  },
];

const pi = Math.PI;
const xPi = (Math.PI * 3000.0) / 180.0;
const semiMajorAxis = 6378245.0;
const eccentricitySquared = 0.00669342162296594323;

export function getCoordinateSystem(crs: CoordinateCrs): CoordinateSystemMeta {
  const meta = coordinateSystems.find((system) => system.id === crs);
  if (!meta) {
    throw new Error(`不支持的坐标系：${crs}`);
  }
  return meta;
}

function parseFiniteCoordinate(value: string, label: string): number {
  const parsed = Number(value.trim());
  if (!Number.isFinite(parsed)) {
    throw new Error(`请输入有效的${label}数值。`);
  }
  return parsed;
}

function isGeographicCrs(crs: CoordinateCrs): boolean {
  return crs !== 'EPSG:3857';
}

function assertCoordinateRange(x: number, y: number, crs: CoordinateCrs): void {
  if (isGeographicCrs(crs) && (x < -180 || x > 180 || y < -90 || y > 90)) {
    throw new Error('经纬度超出范围，请检查输入坐标。');
  }

  if (crs === 'EPSG:3857') {
    const max = 20037508.35;
    if (Math.abs(x) > max || Math.abs(y) > max) {
      throw new Error('Web Mercator 坐标超出可用范围。');
    }
  }
}

function outOfChina(lon: number, lat: number): boolean {
  return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
}

function transformLat(x: number, y: number): number {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  ret += ((20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0) / 3.0;
  ret += ((20.0 * Math.sin(y * pi) + 40.0 * Math.sin((y / 3.0) * pi)) * 2.0) / 3.0;
  ret += ((160.0 * Math.sin((y / 12.0) * pi) + 320 * Math.sin((y * pi) / 30.0)) * 2.0) / 3.0;
  return ret;
}

function transformLon(x: number, y: number): number {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  ret += ((20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0) / 3.0;
  ret += ((20.0 * Math.sin(x * pi) + 40.0 * Math.sin((x / 3.0) * pi)) * 2.0) / 3.0;
  ret += ((150.0 * Math.sin((x / 12.0) * pi) + 300.0 * Math.sin((x / 30.0) * pi)) * 2.0) / 3.0;
  return ret;
}

function wgs84ToGcj02(lon: number, lat: number): [number, number] {
  if (outOfChina(lon, lat)) {
    return [lon, lat];
  }

  let dLat = transformLat(lon - 105.0, lat - 35.0);
  let dLon = transformLon(lon - 105.0, lat - 35.0);
  const radLat = (lat / 180.0) * pi;
  let magic = Math.sin(radLat);
  magic = 1 - eccentricitySquared * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180.0) / (((semiMajorAxis * (1 - eccentricitySquared)) / (magic * sqrtMagic)) * pi);
  dLon = (dLon * 180.0) / ((semiMajorAxis / sqrtMagic) * Math.cos(radLat) * pi);
  return [lon + dLon, lat + dLat];
}

function gcj02ToWgs84(lon: number, lat: number): [number, number] {
  if (outOfChina(lon, lat)) {
    return [lon, lat];
  }

  const [gcjLon, gcjLat] = wgs84ToGcj02(lon, lat);
  return [lon * 2 - gcjLon, lat * 2 - gcjLat];
}

function gcj02ToBd09(lon: number, lat: number): [number, number] {
  const z = Math.sqrt(lon * lon + lat * lat) + 0.00002 * Math.sin(lat * xPi);
  const theta = Math.atan2(lat, lon) + 0.000003 * Math.cos(lon * xPi);
  return [z * Math.cos(theta) + 0.0065, z * Math.sin(theta) + 0.006];
}

function bd09ToGcj02(lon: number, lat: number): [number, number] {
  const x = lon - 0.0065;
  const y = lat - 0.006;
  const z = Math.sqrt(x * x + y * y) - 0.00002 * Math.sin(y * xPi);
  const theta = Math.atan2(y, x) - 0.000003 * Math.cos(x * xPi);
  return [z * Math.cos(theta), z * Math.sin(theta)];
}

function toWgs84(x: number, y: number, source: CoordinateCrs): [number, number] {
  switch (source) {
    case 'EPSG:4326':
      return [x, y];
    case 'EPSG:3857': {
      const transformed = transform([x, y], 'EPSG:3857', 'EPSG:4326');
      return [transformed[0], transformed[1]];
    }
    case 'GCJ-02':
      return gcj02ToWgs84(x, y);
    case 'BD-09': {
      const [gcjLon, gcjLat] = bd09ToGcj02(x, y);
      return gcj02ToWgs84(gcjLon, gcjLat);
    }
    default:
      throw new Error(`不支持的源坐标系：${source}`);
  }
}

function fromWgs84(lon: number, lat: number, target: CoordinateCrs): [number, number] {
  switch (target) {
    case 'EPSG:4326':
      return [lon, lat];
    case 'EPSG:3857': {
      const transformed = transform([lon, lat], 'EPSG:4326', 'EPSG:3857');
      return [transformed[0], transformed[1]];
    }
    case 'GCJ-02':
      return wgs84ToGcj02(lon, lat);
    case 'BD-09': {
      const [gcjLon, gcjLat] = wgs84ToGcj02(lon, lat);
      return gcj02ToBd09(gcjLon, gcjLat);
    }
    default:
      throw new Error(`不支持的目标坐标系：${target}`);
  }
}

function normalizeZero(value: number): number {
  return Math.abs(value) < 1e-9 ? 0 : value;
}

function formatCoordinateValue(value: number, crs: CoordinateCrs): string {
  return normalizeZero(value).toFixed(getCoordinateSystem(crs).unit === 'meters' ? 2 : 6);
}

export function convertCoordinate(input: CoordinateConversionInput): CoordinateConversionResult {
  const sourceMeta = getCoordinateSystem(input.source);
  const targetMeta = getCoordinateSystem(input.target);
  const x = parseFiniteCoordinate(input.x, sourceMeta.xLabel);
  const y = parseFiniteCoordinate(input.y, sourceMeta.yLabel);
  assertCoordinateRange(x, y, input.source);

  const [wgsLon, wgsLat] = toWgs84(x, y, input.source);
  assertCoordinateRange(wgsLon, wgsLat, 'EPSG:4326');
  const [targetX, targetY] = fromWgs84(wgsLon, wgsLat, input.target).map(normalizeZero) as [
    number,
    number,
  ];

  return {
    source: input.source,
    target: input.target,
    x: targetX,
    y: targetY,
    formattedX: formatCoordinateValue(targetX, input.target),
    formattedY: formatCoordinateValue(targetY, input.target),
    xLabel: targetMeta.xLabel,
    yLabel: targetMeta.yLabel,
    targetLabel: targetMeta.label,
  };
}
