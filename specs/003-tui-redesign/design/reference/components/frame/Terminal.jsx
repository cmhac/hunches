import React from 'react';

export function Terminal({ cols = 80, rows = 24, title = 'hunches', chrome = true, children, style }) {
  const body = (
    <div style={{ position: 'relative', width: cols + 'ch', height: 'calc(var(--row) * ' + rows + ')', display: 'flex', flexDirection: 'column', background: 'var(--bg)', color: 'var(--fg)', fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size)', lineHeight: 'var(--row)', overflow: 'hidden', fontVariantLigatures: 'none', whiteSpace: 'pre' }}>
      {children}
    </div>
  );
  if (!chrome) return body;
  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', borderRadius: 8, overflow: 'hidden', background: 'var(--ink-0)', boxShadow: '0 0 0 1px var(--ink-4), 0 24px 60px rgba(0,0,0,.5)', fontFamily: 'var(--font-mono)', ...style }}>
      <div style={{ height: 28, display: 'flex', alignItems: 'center', gap: 12, padding: '0 12px', color: 'var(--fg-faint)', fontSize: 12 }}>
        <span style={{ display: 'flex', gap: 6 }}>
          <i style={{ width: 10, height: 10, borderRadius: 5, background: 'var(--ink-4)' }}></i>
          <i style={{ width: 10, height: 10, borderRadius: 5, background: 'var(--ink-4)' }}></i>
          <i style={{ width: 10, height: 10, borderRadius: 5, background: 'var(--ink-4)' }}></i>
        </span>
        <span style={{ flex: 1, textAlign: 'center', marginRight: 42 }}>{title} — {cols}×{rows}</span>
      </div>
      <div style={{ padding: '4px 8px 8px', background: 'var(--bg)' }}>{body}</div>
    </div>
  );
}
