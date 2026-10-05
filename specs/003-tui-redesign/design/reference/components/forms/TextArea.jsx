import React from 'react';
import { Panel } from '../layout/Panel.jsx';

function hl(line, language) {
  if (language === 'yaml') {
    if (/^\s*#/.test(line)) return <span style={{ color: 'var(--fg-faint)' }}>{line}</span>;
    const m = line.match(/^(\s*-?\s*)([A-Za-z_][\w-]*)(:)(.*)$/);
    if (m) return <span><span style={{ color: 'var(--fg-muted)' }}>{m[1]}</span><span style={{ color: 'var(--secondary)' }}>{m[2]}</span><span style={{ color: 'var(--fg-muted)' }}>{m[3]}</span><span style={{ color: 'var(--fg-strong)' }}>{m[4]}</span></span>;
  }
  if (language === 'markdown' && /^#/.test(line)) return <span style={{ color: 'var(--primary)', fontWeight: 700 }}>{line}</span>;
  return <span>{line}</span>;
}

export function TextArea({ title, text = '', language, focused = false, lineNumbers = true, cursorLine = -1, grow = true }) {
  const lines = text.split('\n');
  const w = String(lines.length).length + 1;
  return (
    <Panel title={title} focused={focused} grow={grow} pad={0}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {lines.map((l, i) => (
          <div key={i} style={{ display: 'flex', background: i === cursorLine ? 'var(--surface)' : 'transparent' }}>
            {lineNumbers ? <span style={{ flex: '0 0 ' + (w + 1) + 'ch', textAlign: 'right', paddingRight: '1ch', color: i === cursorLine ? 'var(--fg)' : 'var(--fg-faint)' }}>{i + 1}</span> : null}
            <span style={{ flex: 1, minWidth: 0, whiteSpace: 'pre', overflow: 'hidden', textOverflow: 'ellipsis', paddingLeft: lineNumbers ? 0 : '1ch' }}>{hl(l, language)}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
