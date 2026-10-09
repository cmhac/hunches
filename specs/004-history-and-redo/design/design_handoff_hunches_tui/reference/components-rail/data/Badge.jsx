
import React from 'react';

// pass/fail/stale/info/neutral/primary as before; accent (assistant) and muted (baseline) added for the History modal.
const TONES = {
  pass: ['var(--success)', 'var(--ink-1)'],
  fail: ['var(--error)', 'var(--ink-1)'],
  stale: ['var(--warning)', 'var(--ink-1)'],
  info: ['var(--secondary)', 'var(--ink-1)'],
  neutral: ['var(--boost)', 'var(--fg-strong)'],
  primary: ['var(--primary)', 'var(--ink-1)'],
  accent: ['var(--accent)', 'var(--ink-1)'],
  muted: ['var(--panel)', 'var(--fg-muted)'],
};

export function Badge({ tone = 'neutral', children }) {
  const [bg, fg] = TONES[tone] || TONES.neutral;
  return <span style={{ background: bg, color: fg, fontWeight: 700, padding: '0 1ch', whiteSpace: 'pre' }}>{children}</span>;
}
