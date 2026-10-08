
import React from 'react';

export function DataTable({ columns = [], rows = [], cursor = -1, focused = true, header = true, zebra = false, onRowClick, style }) {
  const template = columns.map((c) => c.width || '1fr').join(' ');
  const cell = (c, v, i) => (
    <span key={i} style={{ padding: '0 1ch', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: c.align || 'left', minWidth: 0 }}>{v}</span>
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', ...style }}>
      {header ? (
        <div style={{ display: 'grid', gridTemplateColumns: template, color: 'var(--fg-muted)', flex: '0 0 auto' }}>
          {columns.map((c, i) => cell(c, c.label, i))}
        </div>
      ) : null}
      {rows.map((r, ri) => {
        const cells = Array.isArray(r) ? r : r.cells;
        const on = ri === cursor;
        const bg = on ? (focused ? 'var(--boost)' : 'var(--panel)') : 'transparent';
        const color = on ? 'var(--fg-strong)' : r.dim ? 'var(--fg-muted)' : r.strong ? 'var(--fg-strong)' : 'var(--fg)';
        return (
          <div key={r.key || ri} onClick={onRowClick ? () => onRowClick(ri) : undefined} style={{ display: 'grid', gridTemplateColumns: template, background: bg, color, boxShadow: on && focused ? 'inset 0.5ch 0 0 var(--primary)' : 'none', fontWeight: on || r.strong ? 700 : 400, cursor: onRowClick ? 'pointer' : 'default', flex: '0 0 auto' }}>
            {columns.map((c, i) => cell(c, cells[i], i))}
          </div>
        );
      })}
    </div>
  );
}
