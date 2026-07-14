import { Button, Select } from 'antd';
import { Blend, LocateFixed } from 'lucide-react';

import { coordinateSystems } from './coordinateTransforms';
import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { CoordinateCrs } from '../../types/workspace';

export function CoordinateToolPanel() {
  const coordinateConversion = useMapStore((state) => state.coordinateConversion);
  const setCoordinateInput = useMapStore((state) => state.setCoordinateInput);
  const setCoordinateCrs = useMapStore((state) => state.setCoordinateCrs);
  const convertCoordinate = useMapStore((state) => state.convertCoordinate);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const coordinateOptions = coordinateSystems.map((system) => ({
    label: system.shortLabel,
    value: system.id,
  }));
  const input = coordinateConversion.input;
  const result = coordinateConversion.result;
  const error = coordinateConversion.error;

  const handleConvert = () => {
    convertCoordinate();
    const conversion = useMapStore.getState().coordinateConversion;
    showNotice(
      conversion.error
        ? {
            tone: 'warning',
            title: '坐标转换失败',
            detail: conversion.error,
          }
        : {
            tone: 'success',
            title: '坐标转换完成',
            detail: `${conversion.result?.targetLabel ?? ''} ${conversion.result?.formattedX ?? ''}, ${
              conversion.result?.formattedY ?? ''
            }`,
          },
    );
  };

  return (
    <section className="map-toolbox-section" aria-label="地图工具内容">
      <div className="tool-block-title">
        <LocateFixed size={14} aria-hidden="true" />
        <span>坐标转换</span>
      </div>
      <div className="coordinate-grid">
        <label>
          <span>源</span>
          <Select
            size="small"
            className="womap-compact-select"
            classNames={{ popup: { root: 'womap-select-popup' } }}
            aria-label="源坐标系"
            value={input.source}
            options={coordinateOptions}
            onChange={(value) => setCoordinateCrs('source', value as CoordinateCrs)}
          />
        </label>
        <label>
          <span>目标</span>
          <Select
            size="small"
            className="womap-compact-select"
            classNames={{ popup: { root: 'womap-select-popup' } }}
            aria-label="目标坐标系"
            value={input.target}
            options={coordinateOptions}
            onChange={(value) => setCoordinateCrs('target', value as CoordinateCrs)}
          />
        </label>
        <label>
          <span>X / 经度</span>
          <input
            aria-label="坐标 X 或经度"
            inputMode="decimal"
            value={input.x}
            onChange={(event) => setCoordinateInput('x', event.target.value)}
          />
        </label>
        <label>
          <span>Y / 纬度</span>
          <input
            aria-label="坐标 Y 或纬度"
            inputMode="decimal"
            value={input.y}
            onChange={(event) => setCoordinateInput('y', event.target.value)}
          />
        </label>
      </div>
      <Button size="small" type="primary" className="coordinate-submit" onClick={handleConvert}>
        转换坐标
      </Button>
      {error && (
        <div className="coordinate-message is-error" role="alert">
          {error}
        </div>
      )}
      {result && !error && (
        <div
          className="coordinate-result"
          role="status"
          aria-live="polite"
          aria-label={`坐标转换结果 ${result.formattedX}, ${result.formattedY}`}
        >
          <span>{result.targetLabel}</span>
          <strong>
            {result.xLabel} {result.formattedX} · {result.yLabel} {result.formattedY}
          </strong>
        </div>
      )}
    </section>
  );
}

interface SwipeToolPanelProps {
  onEnabledChange: (enabled: boolean) => void;
}

export function SwipeToolPanel({ onEnabledChange }: SwipeToolPanelProps) {
  const imagerySwipe = useMapStore((state) => state.imagerySwipe);
  const setSwipeBasemap = useMapStore((state) => state.setSwipeBasemap);
  const setSwipePosition = useMapStore((state) => state.setSwipePosition);
  const basemaps = useSettingsStore((state) => state.basemaps);
  const enabledBasemapOptions = basemaps
    .filter((provider) => provider.enabled)
    .map((provider) => ({ label: provider.name, value: provider.id }));

  return (
    <section className="map-toolbox-section" aria-label="两期卷帘内容">
      <div className="tool-block-title">
        <Blend size={14} aria-hidden="true" />
        <span>两期影像卷帘</span>
      </div>
      <label className="tool-switch-row">
        <span>启用卷帘</span>
        <input
          type="checkbox"
          role="switch"
          aria-label="启用两期影像卷帘"
          checked={imagerySwipe.enabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
        />
      </label>
      <div className="swipe-select-grid">
        <label>
          <span>前期</span>
          <Select
            size="small"
            className="womap-compact-select"
            classNames={{ popup: { root: 'womap-select-popup' } }}
            aria-label="前期底图"
            value={imagerySwipe.beforeBasemapId}
            options={enabledBasemapOptions}
            onChange={(value) => setSwipeBasemap('beforeBasemapId', value)}
          />
        </label>
        <label>
          <span>后期</span>
          <Select
            size="small"
            className="womap-compact-select"
            classNames={{ popup: { root: 'womap-select-popup' } }}
            aria-label="后期底图"
            value={imagerySwipe.afterBasemapId}
            options={enabledBasemapOptions}
            onChange={(value) => setSwipeBasemap('afterBasemapId', value)}
          />
        </label>
      </div>
      <label className="swipe-range">
        <span>位置 {imagerySwipe.position}%</span>
        <input
          type="range"
          min="0"
          max="100"
          value={imagerySwipe.position}
          aria-label="卷帘位置"
          onChange={(event) => setSwipePosition(Number(event.target.value))}
        />
      </label>
    </section>
  );
}
