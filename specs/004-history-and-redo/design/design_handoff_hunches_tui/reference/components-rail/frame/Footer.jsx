
import React from 'react';

const GLOBAL = ['Quit', 'Next stage', 'Previous stage', 'Project settings', 'Projects', 'System settings', 'History', 'Redo plan'];

export function Footer({ keys = [], right }) {
  const wide = typeof window !== 'undefined' && window.__wide;
  const list = wide ? keys.filter((k) => !GLOBAL.includes(k.label)) : keys;
  return (
    <div data-footer="1" style={{ height: 'var(--row)', flex: '0 0 auto', display: 'flex', gap: '2ch', padding: '0 2ch', background: 'var(--surface)', whiteSpace: 'nowrap', overflow: 'hidden', margin: wide ? '0 0 0 -1ch' : 0 }}>
      {list.map((k, i) => (
        <span key={i} onClick={k.onClick} style={{ opacity: k.disabled ? 0.4 : 1, cursor: k.onClick ? 'pointer' : 'default', whiteSpace: 'pre' }}>
          <span style={{ background: 'var(--boost)', color: 'var(--fg-strong)', fontWeight: 700, padding: '0 1ch' }}>{k.key}</span>
          <span style={{ color: 'var(--footer-desc)' }}> {k.label}</span>
        </span>
      ))}
      <span style={{ flex: 1 }}></span>
      {right !== undefined ? right : wide ? null : <span style={{ whiteSpace: 'pre' }}><span style={{ background: 'var(--boost)', color: 'var(--fg-strong)', fontWeight: 700, padding: '0 1ch' }}>^p</span><span style={{ color: 'var(--footer-desc)' }}> palette</span></span>}
    </div>
  );
}
