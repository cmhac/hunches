import React from 'react';

const TONES = {
  pass: ['var(--success)', 'var(--ink-1)'],
  fail: ['var(--error)', 'var(--ink-1)'],
  stale: ['var(--warning)', 'var(--ink-1)'],
  info: ['var(--secondary)', 'var(--ink-1)'],
  neutral: ['var(--boost)', 'var(--fg-strong)'],
  primary: ['var(--primary)', 'var(--ink-1)'],
};

export function Badge({ tone = 'neutral', children }) {
  const [bg, fg] = TONES[tone] || TONES.neutral;
  return <span style={{ background: bg, color: fg, fontWeight: 700, padding: '0 1ch', whiteSpace: 'pre' }}>{children}</span>;
}
