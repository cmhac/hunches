import React from 'react';

export function Diff({ text = '' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      {text.split('\n').map((l, i) => {
        let color = 'var(--fg)';
        let bg = 'transparent';
        if (l.startsWith('+++') || l.startsWith('---')) color = 'var(--fg-muted)';
        else if (l.startsWith('@@')) color = 'var(--secondary)';
        else if (l.startsWith('+')) { color = 'var(--success)'; bg = 'var(--success-muted)'; }
        else if (l.startsWith('-')) { color = 'var(--error)'; bg = 'var(--error-muted)'; }
        return <div key={i} style={{ color, background: bg, padding: '0 1ch', whiteSpace: 'pre', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l || ' '}</div>;
      })}
    </div>
  );
}
