
import React from 'react';

export function Input({ value = '', placeholder = '', focused = false, compact = false, onChange, onSubmit, style }) {
  const inner = { height: 'var(--row)', background: focused ? 'var(--boost)' : 'var(--panel)', boxShadow: focused ? 'inset 0.5ch 0 0 var(--primary)' : 'none', padding: '0 1ch', display: 'flex', overflow: 'hidden' };
  return (
    <div style={{ flex: '0 0 auto', ...style }}>
      <div style={inner}>
        {onChange ? (
          <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} onKeyDown={(e) => { if (e.key !== 'Tab' && e.key !== 'Escape' && e.key !== 'F2') e.stopPropagation(); if (e.key === 'Enter' && onSubmit) onSubmit(value); }} style={{ all: 'unset', flex: 1, font: 'inherit', color: 'var(--fg-strong)', caretColor: 'var(--primary)' }} />
        ) : (
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', color: value ? 'var(--fg-strong)' : 'var(--fg-faint)' }}>
            {value || (focused ? '' : placeholder)}
            {focused ? <span style={{ background: 'var(--primary)', color: 'var(--ink-1)' }}> </span> : null}
            {focused && !value ? <span style={{ color: 'var(--fg-faint)' }}>{placeholder}</span> : null}
          </span>
        )}
      </div>
    </div>
  );
}
