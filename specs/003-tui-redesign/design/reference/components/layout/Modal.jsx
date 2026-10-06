import React from 'react';

export function Modal({ title, width = 60, height, dense = false, children, actions }) {
  return (
    <div style={{ position: 'absolute', inset: 0, background: 'var(--scrim)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10 }}>
      <div style={{ position: 'relative', width: width + 'ch', maxWidth: '100%', maxHeight: '90%', height: height ? 'calc(var(--row) * ' + height + ')' : undefined, boxSizing: 'border-box', padding: 'var(--half-y) var(--half-x)', background: 'var(--surface)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: dense ? 0 : 'var(--row)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-round)', padding: dense ? 'calc(var(--half-y) - 1px) calc(var(--half-x) - 1px + 1ch)' : 'calc(var(--half-y) - 1px + var(--row)) calc(var(--half-x) - 1px + 2ch)', overflow: 'hidden', whiteSpace: 'pre-wrap' }}>
          {children}
          {actions ? <div style={{ display: 'flex', gap: '2ch', justifyContent: 'flex-end' }}>{actions}</div> : null}
        </div>
        {title ? <span style={{ position: 'absolute', top: 0, left: '2ch', padding: '0 1ch', background: 'var(--surface)', color: 'var(--primary)', fontWeight: 700 }}>{title}</span> : null}
      </div>
    </div>
  );
}
