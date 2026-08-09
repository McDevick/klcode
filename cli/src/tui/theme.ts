// Catppuccin-inspired soft dark palette with semantic accents.
// Background steps create panel hierarchy: background < surface < surfaceAlt.
// userBg is the light-gray fill behind user bubbles; blue marks tool names.
export const theme = {
  background: '#1E1E2E',
  surface: '#313244',
  surfaceAlt: '#45475A',
  border: '#585B70',
  userBg: '#3B3B4F',
  text: '#CDD6F4',
  textDim: '#A6ADC8',
  blue: '#89B4FA',
  teal: '#94E2D5',
  green: '#A6E3A1',
  red: '#F38BA8',
  yellow: '#F9E2AF',
  deepYellow: '#E5C07B',
  purple: '#CBA6F7',
} as const;
