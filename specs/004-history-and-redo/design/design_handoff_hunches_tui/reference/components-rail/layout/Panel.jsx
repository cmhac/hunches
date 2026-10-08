
import React from 'react';

export function Panel({ title, subtitle, focused = false, pad = 1, grow, bg = 'var(--surface)', children, style, innerStyle }) {
  const flex = grow === true ? 1 : grow;
  const tpx = pad === 0 ? '1ch' : '2ch';
  const cpx = pad === 0 ? '0' : '2ch';
  return (
    <div data-panel="1" style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, flex, padding: '0 var(--panel-gx, 0px) var(--panel-gap, 0px) 0', ...style }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'hidden', background: bg, boxShadow: focused ? 'inset 0.5ch 0 0 var(--primary)' : 'none' }}>
        {title || subtitle ? (
          <div style={{ display: 'flex', gap: '2ch', padding: '0 ' + tpx, flex: '0 0 auto', whiteSpace: 'nowrap', overflow: 'hidden' }}>
            <span style={{ color: focused ? 'var(--primary)' : 'var(--fg-strong)', fontWeight: 700, flex: '0 0 auto' }}>{title}</span>
            <span style={{ flex: 1 }}></span>
            {subtitle ? <span style={{ color: 'var(--fg-muted)', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{subtitle}</span> : null}
          </div>
        ) : null}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'hidden', padding: '0 ' + cpx, ...innerStyle }}>
          {children}
        </div>
      </div>
    </div>
  );
}
