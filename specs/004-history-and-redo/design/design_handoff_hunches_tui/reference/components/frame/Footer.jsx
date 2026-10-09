import React from 'react';

export function Footer({ keys = [], right }) {
  return (
    <div style={{ height: 'var(--row)', flex: '0 0 auto', display: 'flex', gap: '2ch', padding: '0 1ch', background: 'var(--footer-bg)', whiteSpace: 'nowrap', overflow: 'hidden' }}>
      {keys.map((k, i) => (
        <span key={i} onClick={k.onClick} style={{ opacity: k.disabled ? 0.4 : 1, cursor: k.onClick ? 'pointer' : 'default' }}>
          <span style={{ color: 'var(--footer-key)', fontWeight: 700 }}>{k.key}</span>
          <span style={{ color: 'var(--footer-desc)' }}> {k.label}</span>
        </span>
      ))}
      <span style={{ flex: 1 }}></span>
      {right !== undefined ? right : <span><span style={{ color: 'var(--footer-key)', fontWeight: 700 }}>^p</span><span style={{ color: 'var(--footer-desc)' }}> palette</span></span>}
    </div>
  );
}
