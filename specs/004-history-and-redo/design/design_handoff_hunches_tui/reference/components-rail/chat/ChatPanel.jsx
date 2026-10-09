
import React from 'react';
import { Panel } from '../layout/Panel.jsx';
import { Input } from '../forms/Input.jsx';
import { Button } from '../forms/Button.jsx';

const MAXROWS = 12;
const detail = (m) => {
  const lines = (m.body || '').split('\n');
  const shown = lines.slice(0, MAXROWS);
  return (
    <div style={{ margin: '0 0 0 2ch', background: 'var(--panel)', padding: '0 1ch', whiteSpace: 'pre-wrap', color: 'var(--fg-muted)', minWidth: 0 }}>
      {shown.map((l, i) => {
        if (l.indexOf('# ') === 0) return <div key={i} style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>{l.slice(2)}</div>;
        const p = (/^(\s*[\d,]+\s{2}|\s*[-+]\s|\s*)/.exec(l) || [''])[0].length;
        return <div key={i} style={{ paddingLeft: p + 'ch', textIndent: '-' + p + 'ch' }}>{l || ' '}</div>;
      })}
      {lines.length > MAXROWS ? <div style={{ color: 'var(--fg-faint)' }}>… {lines.length - MAXROWS} more lines (scroll)</div> : null}
    </div>
  );
};
const toggle = (open) => <span style={{ color: 'var(--fg-faint)', flex: '0 0 auto' }}>{open ? '▾' : '▸'}</span>;

export function ChatPanel({ title = 'chat', model, messages = [], streaming, input = '', placeholder = 'Message the assistant', focused = false, grow = true, onInput, onSubmit, empty }) {
  const line = (m, i) => {
    if (m.role === 'user') return <div key={i} style={{ display: 'flex', color: 'var(--fg-strong)' }}><span style={{ color: 'var(--primary)', flex: '0 0 2ch' }}>›</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{m.text}</span></div>;
    if (m.role === 'context') return (
      <div key={i}>
        <div style={{ display: 'flex', gap: '1ch', color: 'var(--fg-muted)' }}>
          <span style={{ flex: '0 0 2ch' }}>◇</span>
          {m.edit ? <span style={{ background: 'var(--primary)', color: 'var(--ink-1)', fontWeight: 700, padding: '0 1ch', flex: '0 0 auto' }}>YOU EDITED</span> : null}
          {m.updated ? <span style={{ background: 'var(--secondary)', color: 'var(--ink-1)', fontWeight: 700, padding: '0 1ch', flex: '0 0 auto' }}>UPDATED</span> : null}
          <span style={{ flex: 1, minWidth: 0, whiteSpace: 'pre-wrap' }}>{m.summary}</span>{toggle(m.open)}
        </div>
        {m.open ? detail(m) : null}
      </div>
    );
    if (m.role === 'tool' && m.name) return (
      <div key={i}>
        <div style={{ display: 'flex', gap: '1ch', color: 'var(--fg-muted)', whiteSpace: 'nowrap' }}>
          <span style={{ flex: '0 0 2ch' }}>↳</span><span style={{ color: 'var(--fg)', flex: '0 0 auto' }}>{m.name}</span>
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.summary}</span>{toggle(m.open)}
        </div>
        {m.open ? detail(m) : null}
      </div>
    );
    if (m.role === 'tool') return <div key={i} style={{ display: 'flex', color: 'var(--fg-muted)' }}><span style={{ flex: '0 0 2ch' }}>↳</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{m.text}</span></div>;
    if (m.role === 'proposal') return (
      <div key={i} style={{ margin: '0 0 0 2ch', background: 'var(--panel)', boxShadow: 'inset 0.5ch 0 0 var(--secondary)', padding: '0 1ch' }}>
        <div style={{ display: 'flex', gap: '1ch', whiteSpace: 'nowrap' }}><span style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>Proposed prompt change</span><span style={{ flex: 1 }}></span><span style={{ color: 'var(--success)' }}>+{m.plus}</span><span style={{ color: 'var(--error)' }}>−{m.minus}</span></div>
        {m.status === 'pending' ? (
          <React.Fragment>
            <div style={{ color: 'var(--fg-muted)' }}>Review the diff, edit it, then accept or reject.</div>
            <div style={{ display: 'flex', gap: '1ch', flexWrap: 'wrap' }}><Button variant="primary" compact> Review </Button><Button compact> Reject </Button></div>
          </React.Fragment>
        ) : m.status === 'accepted' ? <div style={{ color: 'var(--success)' }}>Accepted{m.note ? <span style={{ color: 'var(--fg-muted)' }}> · {m.note}</span> : null}</div>
          : <div style={{ color: 'var(--fg-muted)' }}>Rejected. The assistant keeps the current prompt.</div>}
      </div>
    );
    if (m.role === 'error') return <div key={i} style={{ color: 'var(--error)', whiteSpace: 'pre-wrap' }}>{'Error: ' + m.text}</div>;
    return <div key={i} style={{ display: 'flex', color: 'var(--fg)' }}><span style={{ color: 'var(--accent)', flex: '0 0 2ch' }}>│</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{m.text}</span></div>;
  };
  const gap = (m) => (m.role === 'tool' ? 0 : 'var(--row)');
  return (
    <Panel title={title} subtitle={model} focused={focused} grow={grow} pad={0} innerStyle={{ gap: 0 }}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', padding: '0 1ch var(--row)' }}>
        {!messages.length && !streaming && empty ? <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--fg-muted)', whiteSpace: 'pre-wrap', padding: '0 2ch' }}>{empty}</div> : null}
        {messages.map((m, i) => <div key={i} style={{ marginTop: i === 0 ? 0 : (m.role === 'tool' && messages[i - 1].role !== 'tool' ? 0 : gap(m)) }}>{line(m, i)}</div>)}
        {streaming ? <div style={{ display: 'flex', color: 'var(--accent)', marginTop: messages.length ? 'var(--row)' : 0 }}><span style={{ flex: '0 0 2ch' }}>│</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{streaming}<span style={{ background: 'var(--accent)' }}> </span></span></div> : null}
      </div>
      <div style={{ display: 'flex', gap: '1ch', flex: '0 0 auto' }}><div style={{ flex: 1, minWidth: 0 }}><Input value={input} placeholder={placeholder} focused={focused} onChange={onInput} onSubmit={onSubmit} /></div><Button variant="primary" disabled={!input || !!streaming} onClick={onSubmit ? () => onSubmit(input) : undefined}> ↑ </Button></div>
    </Panel>
  );
}
