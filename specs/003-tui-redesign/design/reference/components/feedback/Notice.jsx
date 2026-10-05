import React from 'react';

const T = {
  note: ['var(--fg-muted)', 'transparent'],
  ok: ['var(--success)', 'var(--success-muted)'],
  warn: ['var(--warning)', 'var(--warning-muted)'],
  error: ['var(--error)', 'var(--error-muted)'],
  stale: ['var(--error)', 'var(--error-muted)'],
};

export function Notice({ tone = 'note', banner = false, children }) {
  const [fg, bg] = T[tone] || T.note;
  return (
    <div style={{ color: fg, background: banner ? bg : 'transparent', fontWeight: banner ? 700 : 400, padding: banner ? '0 1ch' : '0 1ch', whiteSpace: 'pre-wrap', flex: '0 0 auto' }}>
      {children}
    </div>
  );
}
