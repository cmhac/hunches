import React from 'react';

const S = { information: 'var(--secondary)', warning: 'var(--warning)', error: 'var(--error)', success: 'var(--success)' };

export function Toast({ title, message, severity = 'information', floating = true }) {
  const c = S[severity] || S.information;
  const box = (
    <div style={{ width: '40ch', background: 'var(--panel)', boxShadow: 'inset 0.5ch 0 0 ' + c, padding: 'var(--half-y) 1ch var(--half-y) 2ch', whiteSpace: 'pre-wrap' }}>
      {title ? <div style={{ color: c, fontWeight: 700 }}>{title}</div> : null}
      <div style={{ color: 'var(--fg)' }}>{message}</div>
    </div>
  );
  if (!floating) return box;
  return <div style={{ position: 'absolute', right: '1ch', bottom: 'calc(var(--row) * 2)', zIndex: 8 }}>{box}</div>;
}
