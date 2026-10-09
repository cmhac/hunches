
import React from 'react';

export function Select({ value, options = [], open = false, focused = false, compact = false, onPick }) {
  const label = (options.find((o) => (o.value || o) === value) || {}).label || value;
  return (
    <div style={{ position: 'relative', flex: '0 0 auto' }}>
      <div style={{ height: 'var(--row)', background: focused ? 'var(--boost)' : 'var(--panel)', boxShadow: focused ? 'inset 0.5ch 0 0 var(--primary)' : 'none', padding: '0 1ch', display: 'flex', color: 'var(--fg-strong)' }}>
        <span style={{ flex: 1 }}>{label}</span>
        <span style={{ color: focused ? 'var(--primary)' : 'var(--fg-muted)' }}>{open ? '▲' : '▼'}</span>
      </div>
      {open ? (
        <div style={{ position: 'absolute', zIndex: 5, left: 0, right: 0, top: 'var(--row)', background: 'var(--panel)', boxShadow: '0 0 0 1px var(--ink-5)' }}>
          {options.map((o, i) => {
            const v = o.value || o;
            const on = v === value;
            return <div key={i} onClick={onPick ? () => onPick(v) : undefined} style={{ padding: '0 1ch', background: on ? 'var(--boost)' : 'transparent', boxShadow: on ? 'inset 0.5ch 0 0 var(--primary)' : 'none', color: on ? 'var(--fg-strong)' : 'var(--fg)', fontWeight: on ? 700 : 400, cursor: 'pointer' }}>{o.label || o}</div>;
          })}
        </div>
      ) : null}
    </div>
  );
}
