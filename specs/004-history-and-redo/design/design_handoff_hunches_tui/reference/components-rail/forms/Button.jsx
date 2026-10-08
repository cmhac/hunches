
import React from 'react';

const V = {
  default: ['var(--boost)', 'var(--fg-strong)'],
  primary: ['var(--primary)', 'var(--ink-1)'],
  success: ['var(--success)', 'var(--ink-1)'],
  error: ['var(--error)', 'var(--ink-1)'],
};

export function Button({ variant = 'default', focused = false, disabled = false, compact = false, onClick, children }) {
  let [bg, fg] = V[variant] || V.default;
  if (disabled) { bg = 'var(--panel)'; fg = 'var(--fg-faint)'; }
  return <button onClick={disabled ? undefined : onClick} style={{ background: bg, color: fg, cursor: disabled ? 'default' : 'pointer', textDecoration: focused ? 'underline' : 'none', textUnderlineOffset: 3, whiteSpace: 'pre', border: 0, font: 'inherit', fontWeight: 700, padding: compact ? '0 1ch' : '0 2ch', height: 'var(--row)', lineHeight: 'var(--row)', boxShadow: focused ? '0 0 0 1px var(--fg-strong)' : 'none' }}>{children}</button>;
}
