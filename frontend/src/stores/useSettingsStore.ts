import { create } from 'zustand';

import type { BasemapProvider, PanelLayoutSettings } from '../types/workspace';

interface SettingsState {
  basemaps: BasemapProvider[];
  panels: PanelLayoutSettings;
  swipePanelSnapshot: PanelLayoutSettings | null;
  togglePanel: (panel: keyof PanelLayoutSettings) => void;
  collapseSidePanelsForSwipe: () => void;
  restoreSidePanelsAfterSwipe: () => void;
  reset: () => void;
}

const basemaps: BasemapProvider[] = [
  {
    id: 'amap-vector',
    type: 'xyz',
    name: '高德矢量',
    urlTemplate:
      'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    apiKey: '',
    subdomains: ['1', '2', '3', '4'],
    enabled: true,
    apiKeyConfigured: false,
  },
  {
    id: 'tencent-vector',
    type: 'xyz',
    name: '腾讯矢量',
    urlTemplate: 'https://rt{s}.map.gtimg.com/tile?z={z}&x={x}&y={y}&type=vector&styleid=1',
    apiKey: '',
    subdomains: ['0', '1', '2', '3'],
    enabled: true,
    apiKeyConfigured: false,
  },
  {
    id: 'tianditu-vector',
    type: 'xyz',
    name: '天地图矢量',
    urlTemplate: 'https://t{s}.tianditu.gov.cn/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk={api_key}',
    apiKey: '',
    subdomains: ['0', '1', '2', '3', '4', '5', '6', '7'],
    enabled: false,
    apiKeyConfigured: false,
  },
  {
    id: 'baidu-vector',
    type: 'xyz',
    name: '百度矢量',
    urlTemplate: 'https://online{s}.map.bdimg.com/tile/?qt=tile&x={x}&y={y}&z={z}&styles=pl',
    apiKey: '',
    subdomains: ['0', '1', '2', '3'],
    enabled: false,
    apiKeyConfigured: false,
  },
  {
    id: 'custom-xyz',
    type: 'xyz',
    name: '自定义 XYZ',
    urlTemplate: '',
    apiKey: '',
    subdomains: [],
    enabled: false,
    apiKeyConfigured: false,
  },
];

function createInitialPanels(): PanelLayoutSettings {
  return {
    layers: true,
    basemaps: true,
    jobs: true,
    properties: true,
    fields: true,
    performance: true,
  };
}

export const useSettingsStore = create<SettingsState>((set) => ({
  basemaps,
  panels: createInitialPanels(),
  swipePanelSnapshot: null,
  togglePanel: (panel) =>
    set((state) => ({
      panels: {
        ...state.panels,
        [panel]: !state.panels[panel],
      },
    })),
  collapseSidePanelsForSwipe: () =>
    set((state) => {
      if (state.swipePanelSnapshot) {
        return state;
      }
      return {
        swipePanelSnapshot: state.panels,
        panels: {
          ...state.panels,
          layers: false,
          basemaps: false,
          jobs: false,
          properties: false,
          fields: false,
        },
      };
    }),
  restoreSidePanelsAfterSwipe: () =>
    set((state) => {
      if (!state.swipePanelSnapshot) {
        return state;
      }
      return {
        panels: state.swipePanelSnapshot,
        swipePanelSnapshot: null,
      };
    }),
  reset: () =>
    set({
      basemaps,
      panels: createInitialPanels(),
      swipePanelSnapshot: null,
    }),
}));
