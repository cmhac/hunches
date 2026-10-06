
import React from 'react';

export function LabelOption({ k, name, description, color, checked = false, mode = 'single', onClick }) {
  const c = color || (name === 'off_topic' ? 'var(--label-off)' : 'var(--label-1)');
  const mark = mode === 'multi' ? (checked ? '■' : '□') : checked ? '●' : '○';
  return (
    <div onClick={onClick} style={{ display: 'flex', gap: '1ch', whiteSpace: 'nowrap', cursor: onClick ? 'pointer' : 'default', margin: '0 -2ch', padding: '0 2ch', background: checked ? 'var(--boost)' : 'transparent', boxShadow: checked ? 'inset 0.5ch 0 0 var(--primary)' : 'none' }}>
      <span style={{ background: checked ? 'var(--primary)' : 'var(--panel)', color: checked ? 'var(--ink-1)' : 'var(--fg-strong)', fontWeight: 700, padding: '0 1ch' }}>{k}</span>
      <span style={{ color: c }}>{mark}</span>
      <span style={{ color: name === 'off_topic' ? 'var(--fg-muted)' : 'var(--fg-strong)', fontWeight: checked ? 700 : 400 }}>{name}</span>
      {description ? <span style={{ color: 'var(--fg-muted)', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{description}</span> : null}
    </div>
  );
}
