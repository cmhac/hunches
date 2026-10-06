import React from 'react';

export function Panel({ title, subtitle, focused = false, pad = 1, grow, bg = 'var(--bg)', children, style, innerStyle }) {
  const flex = grow === true ? 1 : grow;
  return (
    <div style={{ position: 'relative', padding: 'var(--half-y) var(--half-x)', display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, flex, background: bg, ...style }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'hidden', border: '1px solid ' + (focused ? 'var(--border)' : 'var(--border-blurred)'), borderRadius: 'var(--radius-round)', padding: 'calc(var(--half-y) - 1px) calc(var(--half-x) - 1px + ' + pad + 'ch)', ...innerStyle }}>
        {children}
      </div>
      {title ? <span style={{ position: 'absolute', top: 0, left: '2ch', maxWidth: 'calc(100% - 4ch)', overflow: 'hidden', textOverflow: 'ellipsis', padding: '0 1ch', background: bg, color: focused ? 'var(--primary)' : 'var(--fg-muted)', fontWeight: 700 }}>{title}</span> : null}
      {subtitle ? <span style={{ position: 'absolute', bottom: 0, right: '2ch', padding: '0 1ch', background: bg, color: 'var(--fg-muted)' }}>{subtitle}</span> : null}
    </div>
  );
}
