import { Button, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { Blend, ChevronDown, Gauge, LocateFixed, ScanSearch, Wrench, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { CoordinateToolPanel, SwipeToolPanel } from './MapToolsPanel';
import { PerformancePanel } from '../performance/PerformancePanel';
import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import { useSpatialAnalysisStore } from '../../stores/useSpatialAnalysisStore';

type ToolView = 'coordinate' | 'swipe' | 'performance';

export function MapToolbox() {
  const [open, setOpen] = useState(false);
  const [activeView, setActiveView] = useState<ToolView | null>(null);
  const performanceEnabled = useSettingsStore((state) => state.panels.performance);
  const collapseSidePanelsForSwipe = useSettingsStore(
    (state) => state.collapseSidePanelsForSwipe,
  );
  const restoreSidePanelsAfterSwipe = useSettingsStore(
    (state) => state.restoreSidePanelsAfterSwipe,
  );
  const setSwipeEnabled = useMapStore((state) => state.setSwipeEnabled);
  const setWorkspaceMode = useWorkspaceStore((state) => state.setWorkspaceMode);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const enterSpatialAnalysis = useSpatialAnalysisStore((state) => state.enter);

  const closeToolbox = useCallback(() => {
    setOpen(false);
    setActiveView(null);
  }, []);

  useEffect(() => {
    if (!open) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeToolbox();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [closeToolbox, open]);

  const handleSwipeEnabledChange = useCallback(
    (enabled: boolean) => {
      setSwipeEnabled(enabled);
      if (enabled) {
        setWorkspaceMode('browse');
        collapseSidePanelsForSwipe();
      } else {
        restoreSidePanelsAfterSwipe();
      }
      showNotice({
        tone: 'info',
        title: enabled ? '卷帘已开启' : '卷帘已关闭',
        detail: enabled ? '拖动分隔线或调整参数比较前后两期底图。' : '地图已回到普通底图显示。',
      });
    },
    [
      collapseSidePanelsForSwipe,
      restoreSidePanelsAfterSwipe,
      setSwipeEnabled,
      setWorkspaceMode,
      showNotice,
    ],
  );

  const menuItems = useMemo<MenuProps['items']>(
    () => [
      { key: 'coordinate', label: '地图工具', icon: <LocateFixed size={14} /> },
      { key: 'swipe', label: '两期卷帘', icon: <Blend size={14} /> },
      { key: 'analysis', label: '空间分析', icon: <ScanSearch size={14} /> },
      {
        key: 'performance',
        label: '性能',
        icon: <Gauge size={14} />,
        disabled: !performanceEnabled,
      },
    ],
    [performanceEnabled],
  );

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'analysis') {
      enterSpatialAnalysis();
      closeToolbox();
      return;
    }
    const nextView = key as ToolView;
    setActiveView(nextView);
    if (nextView === 'swipe') handleSwipeEnabledChange(true);
  };

  return (
    <div className="map-toolbox">
      <Dropdown
        trigger={['click']}
        placement="bottomRight"
        open={open}
        destroyOnHidden
        overlayClassName="map-toolbox-dropdown"
        onOpenChange={(nextOpen, info) => {
          if (!nextOpen && info.source === 'menu') return;
          setOpen(nextOpen);
          if (!nextOpen) setActiveView(null);
        }}
        menu={{
          items: menuItems,
          selectable: true,
          selectedKeys: activeView ? [activeView] : [],
          onClick: handleMenuClick,
        }}
        popupRender={(menus) => (
          <div className="map-toolbox-popup" data-testid="map-toolbox-popup">
            <div className="map-toolbox-popup-header">
              <div>
                <span>地图</span>
                <strong>工具</strong>
              </div>
              <Tooltip title="关闭工具">
                <Button
                  type="text"
                  size="small"
                  aria-label="关闭工具"
                  icon={<X size={15} />}
                  onClick={closeToolbox}
                />
              </Tooltip>
            </div>
            {menus}
            {activeView && (
              <div className="map-toolbox-content">
                {activeView === 'coordinate' && <CoordinateToolPanel />}
                {activeView === 'swipe' && (
                  <SwipeToolPanel onEnabledChange={handleSwipeEnabledChange} />
                )}
                {activeView === 'performance' && <PerformancePanel />}
              </div>
            )}
          </div>
        )}
      >
        <Button className="map-toolbox-trigger" icon={<Wrench size={15} />}>
          <span>工具</span>
          <ChevronDown size={13} aria-hidden="true" />
        </Button>
      </Dropdown>
    </div>
  );
}
