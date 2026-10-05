import React from 'react';

const V = {
  default: ['var(--boost)', 'var(--fg-strong)'],
  primary: ['var(--primary)', 'var(--ink-1)'],
  success: ['var(--success)', 'var(--ink-1)'],
  error: ['var(--error)', 'var(--ink-1)'],
};

export function Button({ variant = 'default', focused = false, disabled = false, compact = false, onClick, children }) {
  const [bg, fg] = V[variant] || V.default;
  const base = { background: bg, color: fg, fontWeight: 700, cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.45 : 1, textDecoration: focused ? 'underline' : 'none', textUnderlineOffset: 3, whiteSpace: 'pre', border: 0, font: 'inherit', fontWeight: 700 };
  if (compact) return <button onClick={disabled ? undefined : onClick} style={{ ...base, padding: '0 1ch', height: 'var(--row)', lineHeight: 'var(--row)' }}>{children}</button>;
  return (
    <button onClick={disabled ? undefined : onClick} style={{ ...base, minWidth: '16ch', height: 'calc(var(--row) * 3)', padding: '0 2ch', boxShadow: 'inset 0 3px 0 rgba(255,255,255,' + (focused ? '.28' : '.14') + '), inset 0 -3px 0 rgba(0,0,0,.35)' + (focused ? ', 0 0 0 1px var(--fg-strong)' : '') }}>
      {children}
    </button>
  );
}
