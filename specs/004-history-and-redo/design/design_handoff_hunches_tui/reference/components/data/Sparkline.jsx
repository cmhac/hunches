import React from 'react';

const TICKS = '▁▂▃▄▅▆▇█';

export function Sparkline({ values = [], min, max, color = 'var(--accent)' }) {
  const lo = min !== undefined ? min : Math.min(...values);
  const hi = max !== undefined ? max : Math.max(...values);
  const s = values.map((v) => TICKS[Math.max(0, Math.min(7, Math.round(((v - lo) / (hi - lo || 1)) * 7)))]).join('');
  return <span style={{ color, whiteSpace: 'pre' }}>{s}</span>;
}
