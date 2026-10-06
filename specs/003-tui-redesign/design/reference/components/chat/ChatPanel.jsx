import React from 'react';
import { Panel } from '../layout/Panel.jsx';
import { Input } from '../forms/Input.jsx';

export function ChatPanel({ title = 'chat', model, messages = [], streaming, input = '', placeholder = 'Message the assistant', focused = false, grow = true, onInput, onSubmit }) {
  const line = (m, i) => {
    if (m.role === 'user') return <div key={i} style={{ display: 'flex', color: 'var(--fg-strong)' }}><span style={{ color: 'var(--primary)', flex: '0 0 2ch' }}>›</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{m.text}</span></div>;
    if (m.role === 'tool') return <div key={i} style={{ display: 'flex', color: 'var(--fg-muted)' }}><span style={{ flex: '0 0 2ch' }}>↳</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{m.text}</span></div>;
    if (m.role === 'error') return <div key={i} style={{ color: 'var(--error)', whiteSpace: 'pre-wrap' }}>{'Error: ' + m.text}</div>;
    return <div key={i} style={{ display: 'flex', color: 'var(--fg)' }}><span style={{ color: 'var(--accent)', flex: '0 0 2ch' }}>│</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{m.text}</span></div>;
  };
  return (
    <Panel title={title} subtitle={model} focused={focused} grow={grow} pad={0} innerStyle={{ gap: 0 }}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 'var(--row)', padding: '0 1ch' }}>
        {messages.map(line)}
        {streaming ? <div style={{ display: 'flex', color: 'var(--accent)' }}><span style={{ flex: '0 0 2ch' }}>│</span><span style={{ whiteSpace: 'pre-wrap', minWidth: 0 }}>{streaming}<span style={{ background: 'var(--accent)' }}> </span></span></div> : null}
      </div>
      <Input value={input} placeholder={placeholder} focused={focused} onChange={onInput} onSubmit={onSubmit} />
    </Panel>
  );
}
