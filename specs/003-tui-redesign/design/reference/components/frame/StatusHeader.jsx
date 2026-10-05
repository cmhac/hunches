import React from 'react';

export const STAGES = ['Brief and seeds', 'Search', 'Taxonomy and prompt', 'Gold dev set', 'Tuning loop', 'Gold test set', 'Threshold', 'Full run', 'Browse'];

export function StatusHeader({ project = 'project', stage = 1, name: title, stages = STAGES, cost = 0, unknownModels = [], onStage }) {
  const unknown = unknownModels.length > 0;
  const name = stage === 0 ? (title || 'Setup') : stages[stage - 1];
  return (
    <div style={{ height: 'var(--row)', flex: '0 0 auto', display: 'flex', gap: '2ch', padding: '0 1ch', background: 'var(--header-bg)', color: 'var(--fg)', whiteSpace: 'nowrap', overflow: 'hidden' }}>
      <span style={{ color: 'var(--primary)', fontWeight: 700 }}>hunches</span>
      <span style={{ color: 'var(--fg-strong)', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '16ch' }}>{project}</span>
      <span style={{ display: 'flex' }}>
        {stages.map((s, i) => {
          const n = i + 1;
          const ch = n < stage ? '●' : n === stage ? '◉' : '○';
          const color = n < stage ? 'var(--fg-muted)' : n === stage ? 'var(--primary)' : 'var(--fg-faint)';
          return <span key={i} title={n + ' ' + s} onClick={onStage ? () => onStage(n) : undefined} style={{ color, cursor: onStage ? 'pointer' : 'default' }}>{ch}</span>;
        })}
      </span>
      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {stage ? <React.Fragment><span style={{ color: 'var(--primary)', fontWeight: 700 }}>{stage}</span><span style={{ color: 'var(--fg-faint)' }}>/{stages.length} </span></React.Fragment> : null}{name}
      </span>
      {unknown ? (
        <span style={{ background: 'var(--warning)', color: 'var(--ink-1)', fontWeight: 700, padding: '0 1ch', overflow: 'hidden', textOverflow: 'ellipsis' }}>cost ? · no price for {unknownModels.join(', ')}</span>
      ) : (
        <span><span style={{ color: 'var(--fg-muted)' }}>cost </span><span style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>{'$' + cost.toFixed(4)}</span></span>
      )}
    </div>
  );
}
