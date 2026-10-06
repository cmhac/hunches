
import React from 'react';

export function Modal({ title, width = 60, height, dense = false, children, actions }) {
  return (
    <div style={{ position: 'absolute', inset: 0, background: 'var(--scrim)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10 }}>
      <div style={{ width: width + 'ch', maxWidth: '100%', maxHeight: '92%', height: height ? 'calc(var(--row) * ' + height + ')' : undefined, boxSizing: 'border-box', padding: dense ? 'var(--row) 2ch' : 'var(--row) 3ch', background: 'var(--surface)', boxShadow: 'inset 0.5ch 0 0 var(--primary), 0 12px 40px rgba(0,0,0,.5)', display: 'flex', flexDirection: 'column', gap: dense ? 0 : 'var(--row)', overflow: 'hidden', whiteSpace: 'pre-wrap' }}>
        {title ? <div style={{ color: 'var(--primary)', fontWeight: 700, flex: '0 0 auto', paddingBottom: dense ? 'var(--row)' : 0 }}>{title}</div> : null}
        {children}
        {actions ? <div style={{ display: 'flex', gap: '2ch', justifyContent: 'flex-end', flex: '0 0 auto', paddingTop: dense ? 'var(--row)' : 0 }}>{actions}</div> : null}
      </div>
    </div>
  );
}
