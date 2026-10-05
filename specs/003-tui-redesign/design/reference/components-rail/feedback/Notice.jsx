
import React from 'react';

const T = {
  note: ['var(--fg-muted)', 'transparent', 'var(--fg-muted)'],
  ok: ['var(--success)', 'var(--success-muted)', 'var(--success)'],
  warn: ['var(--warning)', 'var(--warning-muted)', 'var(--warning)'],
  error: ['var(--error)', 'var(--error-muted)', 'var(--error)'],
  stale: ['var(--error)', 'var(--error-muted)', 'var(--error)'],
};

export function Notice({ tone = 'note', banner = false, children }) {
  const [fg, bg, bar] = T[tone] || T.note;
  return (
    <div style={{ color: fg, background: banner ? bg : 'transparent', boxShadow: banner ? 'inset 0.5ch 0 0 ' + bar : 'none', fontWeight: banner ? 700 : 400, padding: banner ? '0 2ch' : '0 1ch', whiteSpace: 'pre-wrap', flex: '0 0 auto' }}>
      {children}
    </div>
  );
}
