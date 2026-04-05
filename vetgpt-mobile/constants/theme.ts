/**
 * vetgpt-mobile/constants/theme.ts
 * Global design tokens — colors, spacing, typography, shadows.
 */

export const Colors = {
  // Brand
  primary:        '#0B6E4F',   // deep vet green
  primaryLight:   '#12916A',
  primaryDark:    '#084D37',
  accent:         '#F5A623',   // amber — premium feature highlight
  accentLight:    '#FFC45E',

  // Backgrounds
  background:     '#F7F8FA',
  surface:        '#FFFFFF',
  surfaceAlt:     '#F0F2F5',
  card:           '#FFFFFF',

  // Text
  textPrimary:    '#1A1A2E',
  textSecondary:  '#5A6470',
  textMuted:      '#9BA3AE',
  textOnPrimary:  '#FFFFFF',
  textOnAccent:   '#FFFFFF',

  // Semantic
  success:        '#1A9E6E',
  warning:        '#F5A623',
  error:          '#E53935',
  info:           '#2196F3',

  // UI
  border:         '#E4E7EB',
  borderStrong:   '#C8CDD3',
  divider:        '#ECEEF1',
  overlay:        'rgba(0,0,0,0.45)',

  // Chat bubbles
  bubbleUser:     '#0B6E4F',
  bubbleBot:      '#FFFFFF',
  bubbleUserText: '#FFFFFF',
  bubbleBotText:  '#1A1A2E',

  // Offline indicator
  offline:        '#E53935',
  online:         '#1A9E6E',

  // Premium
  premium:        '#F5A623',
  premiumBg:      '#FFF8EC',
};

export const Spacing = {
  xs:  4,
  sm:  8,
  md:  16,
  lg:  24,
  xl:  32,
  xxl: 48,
};

export const Radius = {
  sm:   6,
  md:   12,
  lg:   18,
  xl:   24,
  full: 9999,
};

export const Typography = {
  h1:       { fontSize: 28, fontWeight: '700' as const, lineHeight: 36 },
  h2:       { fontSize: 22, fontWeight: '700' as const, lineHeight: 30 },
  h3:       { fontSize: 18, fontWeight: '600' as const, lineHeight: 26 },
  h4:       { fontSize: 16, fontWeight: '600' as const, lineHeight: 24 },
  body:     { fontSize: 15, fontWeight: '400' as const, lineHeight: 23 },
  bodySmall:{ fontSize: 13, fontWeight: '400' as const, lineHeight: 20 },
  caption:  { fontSize: 11, fontWeight: '400' as const, lineHeight: 16 },
  label:    { fontSize: 12, fontWeight: '600' as const, lineHeight: 18 },
  mono:     { fontSize: 13, fontWeight: '400' as const, fontFamily: 'monospace' as const },
};

export const Shadow = {
  sm: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  md: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.10,
    shadowRadius: 8,
    elevation: 4,
  },
  lg: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.14,
    shadowRadius: 16,
    elevation: 8,
  },
};
