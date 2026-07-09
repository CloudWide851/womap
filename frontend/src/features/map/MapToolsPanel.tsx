import { Button } from 'antd';
import { Blend, LocateFixed, ScanLine } from 'lucide-react';

import { coordinateSystems } from './coordinateTransforms';
import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { CoordinateCrs } from '../../types/workspace';

export function MapToolsPanel() {
  const coordinateConversion = useMapStore((state) => state.coordinateConversion);
  const imagerySwipe = useMapStore((state) => state.imagerySwipe);
  const setCoordinateInput = useMapStore((state) => state.setCoordinateInput);
  const setCoordinateCrs = useMapStore((state) => state.setCoordinateCrs);
  const convertCoordinate = useMapStore((state) => state.convertCoordinate);
  const setSwipeEnabled = useMapStore((state) => state.setSwipeEnabled);
  const setSwipeBasemap = useMapStore((state) => state.setSwipeBasemap);
  const setSwipePosition = useMapStore((state) => state.setSwipePosition);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const basemaps = useSettingsStore((state) => state.basemaps);
  const enabledBasemaps = basemaps.filter((provider) => provider.enabled);
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

  const handleSwipeToggle = (enabled: boolean) => {
    setSwipeEnabled(enabled);
    showNotice({
      tone: 'info',
      title: enabled ? '卷帘已开启' : '卷帘已关闭',
      detail: enabled ? '拖动位置滑杆比较前后两期底图。' : '地图已回到普通底图显示。',
    });
  };

  return (
    <section className="panel-section map-tools-panel-section" aria-label="地图工具">
      <div className="panel-heading compact-heading">
        <div>
          <p>工具</p>
          <h2>地图工具</h2>
        </div>
        <ScanLine size={15} aria-hidden="true" />
      </div>

      <div className="map-tool-block">
        <div className="tool-block-title">
          <LocateFixed size={14} aria-hidden="true" />
          <span>坐标转换</span>
        </div>
        <div className="coordinate-grid">
          <label>
            <span>源</span>
            <select
              aria-label="源坐标系"
              value={input.source}
              onChange={(event) => setCoordinateCrs('source', event.target.value as CoordinateCrs)}
            >
              {coordinateSystems.map((system) => (
                <option key={system.id} value={system.id}>
                  {system.shortLabel}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>目标</span>
            <select
              aria-label="目标坐标系"
              value={input.target}
              onChange={(event) => setCoordinateCrs('target', event.target.value as CoordinateCrs)}
            >
              {coordinateSystems.map((system) => (
                <option key={system.id} value={system.id}>
                  {system.shortLabel}
                </option>
              ))}
            </select>
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
      </div>

      <div className="map-tool-block">
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
            onChange={(event) => handleSwipeToggle(event.target.checked)}
          />
        </label>
        <div className="swipe-select-grid">
          <label>
            <span>前期</span>
            <select
              aria-label="前期底图"
              value={imagerySwipe.beforeBasemapId}
              onChange={(event) => setSwipeBasemap('beforeBasemapId', event.target.value)}
            >
              {enabledBasemaps.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>后期</span>
            <select
              aria-label="后期底图"
              value={imagerySwipe.afterBasemapId}
              onChange={(event) => setSwipeBasemap('afterBasemapId', event.target.value)}
            >
              {enabledBasemaps.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
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
      </div>
    </section>
  );
}
