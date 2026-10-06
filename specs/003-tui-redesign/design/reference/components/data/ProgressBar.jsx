import React from 'react';

export function ProgressBar({ value = 0, total = 100, width = 40, eta, color = 'var(--primary)' }) {
  const frac = total ? Math.min(1, value / total) : 0;
  const halves = Math.round(frac * width * 2);
  const full = Math.floor(halves / 2);
  const half = halves % 2 === 1;
  const rest = width - full - (half ? 1 : 0);
  return (
    <span style={{ whiteSpace: 'pre', display: 'inline-flex', gap: '2ch' }}>
      <span>
        <span style={{ color: frac >= 1 ? 'var(--success)' : color }}>{'━'.repeat(full) + (half ? '╸' : '')}</span>
        <span style={{ color: 'var(--ink-4)' }}>{'━'.repeat(Math.max(0, rest))}</span>
      </span>
      <span style={{ color: 'var(--fg-strong)', fontWeight: 700, minWidth: '4ch', textAlign: 'right' }}>{Math.floor(frac * 100) + '%'}</span>
      {eta ? <span style={{ color: 'var(--fg-muted)' }}>{'ETA ' + eta}</span> : null}
    </span>
  );
}
