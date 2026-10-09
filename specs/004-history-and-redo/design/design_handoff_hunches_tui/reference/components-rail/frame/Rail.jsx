
import React from 'react';
import { STAGES } from './StatusHeader.jsx';

const Item = ({ on, mark, markColor, children, right, color, title, dim }) => (
  <div title={title} style={{ display: 'flex', gap: '1ch', padding: '0 1ch 0 2ch', margin: '0 -2ch', background: on ? 'var(--panel)' : 'transparent', boxShadow: on ? 'inset 0.5ch 0 0 var(--primary)' : 'none', color: on ? 'var(--fg-strong)' : color, fontWeight: on ? 700 : 400, whiteSpace: 'nowrap', opacity: dim ? 0.4 : 1 }}>
    <span style={{ color: markColor, flex: '0 0 1ch' }}>{mark}</span>
    <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{children}</span>
    {right ? <span style={{ color: 'var(--fg-faint)', fontWeight: 400 }}>{right}</span> : null}
  </div>
);

// A stale or incomplete stage gets a glyph and a legend word, never colour alone.
const MARK = { stale: '↻', incomplete: '◐' };

export function Rail({ stage = 0, title = '', project = 'project', stages = STAGES, cost = 0, unknownModels = [], marks = {}, open = '' }) {
  const unknown = unknownModels.length > 0;
  const kinds = [...new Set(Object.values(marks).map((m) => m[0]))];
  const noHist = typeof window !== 'undefined' && window.__noHistory;
  const appItems = [['Projects', 'F4', ['Projects', 'New project']], ['Project settings', 'F3', ['Settings']], ['System settings', 'F5', ['Setup']]];
  return (
    <div style={{ flex: '0 0 26ch', background: 'var(--surface)', padding: 'var(--row) 2ch 0', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <div style={{ color: 'var(--primary)', fontWeight: 700 }}>hunches</div>
      <div style={{ color: 'var(--fg-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project}</div>
      <div style={{ height: 'var(--row)' }}></div>
      {stages.map((s, i) => {
        const n = i + 1, on = n === stage, done = n < stage, mk = marks[n];
        const mark = mk ? MARK[mk[0]] : done ? '✓' : on ? '●' : '·';
        const markColor = mk ? 'var(--warning)' : done ? 'var(--success)' : on ? 'var(--primary)' : 'var(--fg-faint)';
        const color = mk ? 'var(--warning)' : done ? 'var(--fg-muted)' : 'var(--fg-faint)';
        return <Item key={i} on={on} mark={mark} markColor={markColor} color={color} title={n + ' ' + s + (mk ? ' · ' + mk[0].toUpperCase() + ': ' + mk[1] : '')}>{s}</Item>;
      })}
      {kinds.length ? <div style={{ color: 'var(--warning)', whiteSpace: 'nowrap', overflow: 'hidden' }}>{kinds.map((k) => MARK[k] + ' ' + k).join('  ')}</div> : null}
      <div style={{ height: 'var(--row)' }}></div>
      {appItems.map(([label, key, titles]) => {
        const on = stage === 0 && titles.includes(title);
        return <Item key={label} on={on} mark={on ? '▸' : ' '} markColor="var(--primary)" color="var(--fg-muted)" right={key}>{label}</Item>;
      })}
      <Item on={open === 'History'} mark={open === 'History' ? '▸' : ' '} markColor="var(--primary)" color="var(--fg-muted)" right="F8" dim={noHist}>History</Item>
      {kinds.length ? <Item on={open === 'Redo plan'} mark="↻" markColor="var(--warning)" color="var(--warning)" right="F9">Redo plan</Item> : null}
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
