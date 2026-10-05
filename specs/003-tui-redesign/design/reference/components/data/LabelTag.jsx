import React from 'react';

export function LabelTag({ name, color, dim = false }) {
  const c = color || (name === 'off_topic' ? 'var(--label-off)' : 'var(--label-1)');
  return (
    <span style={{ whiteSpace: 'pre', opacity: dim ? 0.6 : 1 }}>
      <span style={{ color: 'var(--tag-mark, ' + c + ')' }}>■ </span>
      <span style={{ color: 'var(--tag-fg, ' + (name === 'off_topic' ? 'var(--fg-muted)' : 'var(--fg-strong)') + ')' }}>{name}</span>
    </span>
  );
}
