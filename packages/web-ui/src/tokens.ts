import { createJsonValue } from './serializable.ts';

const tokenSource = {
  schema: 'UNBRANDED_TOKENS_V1',
  brandState: 'PROVISIONAL_UNBRANDED_OD_002',
  semanticColor: {
    surface: '#FFFFFF',
    text: '#1B1F23',
    muted: '#59636E',
    border: '#C6CDD5',
    info: '#0B63CE',
    success: '#19743B',
    warning: '#8A5A00',
    danger: '#B42318',
  },
  typography: {
    display: {
      fontFamily: 'system-ui, sans-serif',
      fontSizePx: 40,
      fontWeight: 700,
      lineHeight: 1.2,
    },
    heading: {
      fontFamily: 'system-ui, sans-serif',
      fontSizePx: 28,
      fontWeight: 700,
      lineHeight: 1.25,
    },
    body: {
      fontFamily: 'system-ui, sans-serif',
      fontSizePx: 16,
      fontWeight: 400,
      lineHeight: 1.5,
    },
    label: {
      fontFamily: 'system-ui, sans-serif',
      fontSizePx: 14,
      fontWeight: 600,
      lineHeight: 1.4,
    },
    mono: {
      fontFamily: 'ui-monospace, monospace',
      fontSizePx: 14,
      fontWeight: 400,
      lineHeight: 1.5,
    },
  },
  spacingPx: {
    none: 0,
    x1: 4,
    x2: 8,
    x3: 12,
    x4: 16,
    x6: 24,
    x8: 32,
    x12: 48,
    x16: 64,
  },
  radiusPx: {
    none: 0,
    small: 4,
    medium: 8,
    large: 12,
    round: 9999,
  },
  shadow: {
    none: 'none',
    raised: '0 1px 3px rgba(27, 31, 35, 0.18)',
    overlay: '0 12px 32px rgba(27, 31, 35, 0.24)',
  },
  focus: {
    color: '#0B63CE',
    offsetPx: 2,
    widthPx: 2,
  },
  zIndex: {
    base: 0,
    navigation: 100,
    overlay: 900,
    dialog: 1000,
    focus: 1100,
  },
  status: {
    unknown: { color: '#59636E', text: 'Unknown', icon: 'circle-help' },
    draft: { color: '#59636E', text: 'Draft', icon: 'file-edit' },
    ready: { color: '#0B63CE', text: 'Ready', icon: 'circle-info' },
    blocked: { color: '#B42318', text: 'Blocked', icon: 'circle-blocked' },
    complete: { color: '#19743B', text: 'Complete', icon: 'circle-check' },
  },
  severity: {
    info: { color: '#0B63CE', text: 'Info', icon: 'circle-info' },
    low: { color: '#59636E', text: 'Low', icon: 'arrow-down' },
    medium: { color: '#8A5A00', text: 'Medium', icon: 'triangle-warning' },
    high: { color: '#B42318', text: 'High', icon: 'diamond-alert' },
    critical: { color: '#7A1A14', text: 'Critical', icon: 'octagon-alert' },
  },
} as const;

export type UnbrandedTokens = typeof tokenSource;

export const UNBRANDED_TOKENS_V1 = createJsonValue(tokenSource) as UnbrandedTokens;
