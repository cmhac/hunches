import React from 'react';

export function Select({ value, options = [], open = false, focused = false, compact = false, onPick }) {
  const label = (options.find((o) => (o.value || o) === value) || {}).label || value;
  return (
    <div style={{ position: 'relative', padding: compact ? 0 : 'var(--half-y) var(--half-x)', flex: '0 0 auto' }}>
      <div style={compact ? { height: 'var(--row)', background: focused ? 'var(--boost)' : 'var(--surface)', boxShadow: focused ? 'inset 0.5ch 0 0 var(--primary)' : 'none', padding: '0 1ch', display: 'flex', color: 'var(--fg-strong)' } : { height: 'var(--row)', boxSizing: 'content-box', border: '1px solid ' + (focused ? 'var(--border)' : 'var(--border-blurred)'), background: 'var(--surface)', padding: 'calc(var(--half-y) - 1px) calc(var(--half-x) - 1px + 1ch)', display: 'flex', color: 'var(--fg-strong)' }}>
        <span style={{ flex: 1 }}>{label}</span>
        <span style={{ color: focused ? 'var(--primary)' : 'var(--fg-muted)' }}>{open ? '▲' : '▼'}</span>
      </div>
      {open ? (
        <div style={{ position: 'absolute', zIndex: 5, left: compact ? 0 : 'var(--half-x)', right: compact ? 0 : 'var(--half-x)', top: compact ? 'var(--row)' : 'calc(var(--row) * 2.5)', background: 'var(--panel)', border: '1px solid var(--border)', padding: 'calc(var(--half-y) - 1px) 0' }}>
          {options.map((o, i) => {
            const v = o.value || o;
            const on = v === value;
            return <div key={i} onClick={onPick ? () => onPick(v) : undefined} style={{ padding: '0 1ch', background: on ? 'var(--cursor-bg)' : 'transparent', color: on ? 'var(--cursor-fg)' : 'var(--fg)', fontWeight: on ? 700 : 400, cursor: 'pointer' }}>{o.label || o}</div>;
          })}
        </div>
      ) : null}
    </div>
  );
}
