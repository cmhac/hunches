
import React from 'react';
import { STAGES } from './StatusHeader.jsx';

const Item = ({ on, mark, markColor, children, right, color }) => (
  <div style={{ display: 'flex', gap: '1ch', padding: '0 1ch 0 2ch', margin: '0 -2ch', background: on ? 'var(--panel)' : 'transparent', boxShadow: on ? 'inset 0.5ch 0 0 var(--primary)' : 'none', color: on ? 'var(--fg-strong)' : color, fontWeight: on ? 700 : 400, whiteSpace: 'nowrap' }}>
    <span style={{ color: markColor, flex: '0 0 1ch' }}>{mark}</span>
    <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{children}</span>
    {right ? <span style={{ color: 'var(--fg-faint)', fontWeight: 400 }}>{right}</span> : null}
  </div>
);

export function Rail({ stage = 0, title = '', project = 'project', stages = STAGES, cost = 0, unknownModels = [] }) {
  const unknown = unknownModels.length > 0;
  const appItems = [['Projects', 'F4', ['Projects', 'New project']], ['Project settings', 'F3', ['Settings']], ['System settings', 'F5', ['Setup']]];
  return (
    <div style={{ flex: '0 0 26ch', background: 'var(--surface)', padding: 'var(--row) 2ch 0', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <div style={{ color: 'var(--primary)', fontWeight: 700 }}>hunches</div>
      <div style={{ color: 'var(--fg-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project}</div>
      <div style={{ height: 'var(--row)' }}></div>
      {stages.map((s, i) => {
        const n = i + 1, on = n === stage, done = n < stage;
        return <Item key={i} on={on} mark={done ? '✓' : on ? '●' : '·'} markColor={done ? 'var(--success)' : on ? 'var(--primary)' : 'var(--fg-faint)'} color={done ? 'var(--fg-muted)' : 'var(--fg-faint)'}>{s}</Item>;
      })}
      <div style={{ height: 'var(--row)' }}></div>
      {appItems.map(([label, key, titles]) => {
        const on = stage === 0 && titles.includes(title);
        return <Item key={label} on={on} mark={on ? '▸' : ' '} markColor="var(--primary)" color="var(--fg-muted)" right={key}>{label}</Item>;
      })}
      <div style={{ flex: 1 }}></div>
      <div style={{ color: 'var(--fg-faint)', whiteSpace: 'nowrap' }}>n/p stage · q quit</div>
      <div style={{ height: 'var(--row)' }}></div>
      <div style={{ color: 'var(--fg-muted)' }}>cost</div>
      {unknown ? (
        <React.Fragment>
          <div><span style={{ background: 'var(--warning)', color: 'var(--ink-1)', fontWeight: 700, padding: '0 1ch' }}>cost ?</span></div>
          <div style={{ color: 'var(--warning)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>no price for</div>
          <div style={{ color: 'var(--warning)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{unknownModels.join(', ')}</div>
        </React.Fragment>
      ) : <div style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>{'$' + cost.toFixed(4)}</div>}
      <div style={{ height: 'var(--row)' }}></div>
    </div>
  );
}
