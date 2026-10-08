
// History modal (F8) and Redo plan modal (F9). Both open over whatever screen the user is on.
const H_ROWS = [
  { t: '14:52:08', f: 'prompt.md', s: 'UNDO', sum: 'Undid: Prompt: edited by the user', cur: true },
  { t: '14:49:30', f: 'prompt.md', s: 'EXTERNAL', sum: 'prompt.md changed outside hunches' },
  { t: '14:41:12', f: '', s: 'APPROVAL', sum: 'Approved: Tuning loop (dev accuracy 0.920, prompt version 3)' },
  { t: '14:38:50', f: 'prompt.md', s: 'YOU', sum: 'Prompt: edited by the user' },
  { t: '14:31:07', f: 'taxonomy.yaml', s: 'YOU', sum: 'Labels: layoff_fear description', cur: true },
  { t: '14:20:44', f: 'seeds.csv', s: 'YOU', sum: 'Seed 3 edited', cur: true },
  { t: '14:12:03', f: '', s: 'VERSION', sum: 'Taxonomy version 2 saved (50 dev labels kept)' },
  { t: '14:05:19', f: 'prompt.md', s: 'ASSISTANT', sum: 'write_prompt: Prompt written.' },
  { t: '14:05:18', f: 'taxonomy.yaml', s: 'ASSISTANT', sum: 'write_taxonomy: Taxonomy written.' },
  { t: '13:58:44', f: '', s: 'APPROVAL', sum: 'Approved: Brief and seeds (12 seeds)' },
  { t: '13:41:30', f: 'seeds.csv', s: 'RESTORE', sum: 'Restored seeds.csv to 13:36:02' },
  { t: '13:30:00', f: 'prompt.md', s: 'BASELINE', sum: 'Existing file recorded' },
];
const H_DIFF = HD.diff.replace('--- current', '--- prompt.md · before (14:31:07)').replace('+++ proposed', '+++ prompt.md · 14:38:50');
const H_EVENT = 'Approved: Tuning loop\nstage 5 · 14:41:12\nprompt.md at approval: version 3\ndev accuracy 0.920 (target 0.90)\n\nAn approval is not a file. It cannot be restored; it is what you approve again when a stage is stale.';

function HistoryModal({ app, v }) {
  const file = v.file || 'All files';
  const rows = H_ROWS.filter((r) => file === 'All files' || r.f === file);
  const cur = Math.min(v.cursor ?? 3, rows.length - 1);
  const sel = rows[cur];
  const isFile = !!sel.f;
  const text = v.text;
  const restorable = isFile && !sel.cur && sel.s !== 'BASELINE';
  const body = !isFile ? H_EVENT : text ? HD.prompt : H_DIFF;
  return (
    <Modal title="History" dense width={app.cols - 4} height={app.rows - 2}
      actions={<React.Fragment><Button disabled={!isFile}>{text ? 'Show diff v' : 'Show text v'}</Button><Button variant="primary" disabled={!restorable}>Restore this r</Button><Button focused>Close Esc</Button></React.Fragment>}>
      <div style={{ display: 'flex', gap: '1ch', alignItems: 'center', flex: '0 0 auto', padding: '0 1ch' }}>
        <span style={{ color: 'var(--fg-muted)' }}>file</span>
        <div style={{ flex: '0 0 20ch' }}><Select compact value={file} options={['All files', 'seeds.csv', 'taxonomy.yaml', 'prompt.md']} open={v.filterOpen} focused={v.filterOpen} /></div>
        <span style={{ color: 'var(--fg-muted)' }}>newest first · {rows.length} entries</span>
      </div>
      <Panel title="timeline" focused grow={3} pad={0} bg="var(--bg)">
        <DataTable cursor={cur} columns={[{ label: 'Time', width: '9ch' }, { label: 'File', width: '15ch' }, { label: 'Source', width: '12ch' }, { label: 'Summary', width: 'minmax(0,1fr)' }]}
          rows={rows.map((r) => [r.t, r.f || '·', <Badge tone={H_TONE[r.s]}>{r.s}</Badge>, r.sum + (r.cur ? '  (current)' : '')])} />
      </Panel>
      <Panel title={(isFile ? (text ? 'text' : 'diff') + ' · ' + sel.f + ' · ' : '') + sel.t} subtitle={isFile ? (sel.cur ? 'this is the current text' : restorable ? 'Restore this makes ' + sel.f + ' match' : '') : 'event'} grow={2} pad={1} bg="var(--bg)">
        {isFile && !text ? <Diff text={body} /> : <div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg)' }}>{body}</div>}
      </Panel>
    </Modal>
  );
}
function HistoryView({ v, app }) {
  return (
    <React.Fragment>
      <TaxonomyView v={{ focus: 2, msgs: TAX_MSGS, taxonomy: true, prompt: true, undoL: true, undoP: true }} app={app} />
      <HistoryModal app={app} v={v} />
    </React.Fragment>
  );
}

// Redo plan. rows: n stage, why, live calls, cached calls, cost (number | '?' | null for no model calls), done: re-approved in this pass.
const RP_PROMPT = [
  { n: 5, name: 'Tuning loop', kind: 'stale', why: 'prompt changed', live: 50, cached: 0, cost: 0.0412 },
  { n: 6, name: 'Gold test set', kind: 'stale', why: 'prompt changed', live: 50, cached: 0, cost: 0.0412 },
  { n: 7, name: 'Threshold', kind: 'stale', why: 'prompt changed', live: 210, cached: 0, cost: 0.0651 },
  { n: 8, name: 'Full run', kind: 'stale', why: 'prompt changed', live: 3612, cached: 0, cost: 1.1194 },
];
const RP_SEEDS = [
  { n: 2, name: 'Search', kind: 'stale', why: 'seeds changed', live: null, cached: null, cost: null },
  { n: 4, name: 'Gold dev set', kind: 'incomplete', why: '44 of 50 rows', live: null, cached: null, cost: null },
  { n: 7, name: 'Threshold', kind: 'stale', why: 'seeds changed', live: 182, cached: 28, cost: 0.0564 },
];
const RP_PROGRESS = RP_PROMPT.map((r, i) => (i === 0 ? { ...r, done: true } : i === 1 ? { ...r, cached: 50, live: 0, cost: 0 } : r));
const rpMarks = (rows) => Object.fromEntries(rows.filter((r) => !r.done).map((r) => [r.n, [r.kind, r.why]]));
const rpMoney = (c, unpriced) => (c === null ? '·' : unpriced && c > 0 ? '?' : '$' + c.toFixed(4));
function RedoPlanModal({ app, v }) {
  const rows = v.rows;
  const left = rows.filter((r) => !r.done);
  const next = left[0];
  const unpriced = !!v.unpriced;
  const sum = (k) => rows.filter((r) => !r.done).reduce((a, r) => a + (r[k] || 0), 0);
  const totalCost = unpriced ? '?' : '$' + sum('cost').toFixed(4);
  const glyph = (r) => (r.done ? <span style={{ color: 'var(--success)' }}>✓</span> : r === next ? <span style={{ color: 'var(--primary)' }}>▸</span> : <span style={{ color: 'var(--warning)' }}>{r.kind === 'stale' ? '↻' : '◐'}</span>);
  const table = rows.map((r) => ({ key: r.n, dim: r.done, cells: [glyph(r), r.n + ' ' + r.name, r.done ? 'approved again' : r.kind.toUpperCase() + ' · ' + r.why, r.live === null ? '·' : fmt(r.live), r.cached === null ? '·' : fmt(r.cached), r.done ? '·' : rpMoney(r.cost, unpriced)] }));
  table.push({ key: 'total', strong: true, cells: ['', 'Still to do', '', sum('live') ? fmt(sum('live')) : '·', sum('cached') ? fmt(sum('cached')) : '·', left.length ? totalCost : '·'] });
  return (
    <Modal title="Redo plan" dense width={Math.min(92, app.cols - 4)} height={Math.min(app.rows - 2, 24)}
      actions={<React.Fragment><Button focused={!next}>Close Esc</Button>{next ? <Button variant="primary" focused>{(v.progress ? 'Continue to ' : 'Go to ') + next.name + ' Enter'}</Button> : null}</React.Fragment>}>
      <div style={{ color: next ? 'var(--fg)' : 'var(--success)', padding: '0 1ch', whiteSpace: 'pre-wrap' }}>
        {!next ? 'All stages are current.' : v.progress ? 'Tuning loop approved again. Next stale stage: ' + next.name + '. Nothing is approved for you; each stage needs your approval.' : 'These stages were approved before something upstream changed. Nothing is approved for you; each stage needs your approval again.'}
      </div>
      <Panel title="stages in order" subtitle="calls: live = needs the model, cached = free" pad={0} grow bg="var(--bg)">
        <DataTable cursor={-1} columns={[{ label: '', width: '4ch' }, { label: 'Stage', width: '18ch' }, { label: 'Why', width: 'minmax(0,1fr)' }, { label: 'Live', width: '7ch', align: 'right' }, { label: 'Cached', width: '8ch', align: 'right' }, { label: 'Cost', width: '10ch', align: 'right' }]} rows={table} />
      </Panel>
      {unpriced ? <Notice tone="warn">No price for {HD.cheap}: dollars show ? and are not counted as $0.</Notice> : <Notice>Cached calls cost nothing. Cost counts live calls only.</Notice>}
    </Modal>
  );
}
function RedoView({ v, app }) {
  const tuned = { m: M_DEV2, dis: HD.dis.slice(0, 4), trend: [0.86, 0.92], msgs: [T_CTX_UP, T_AG_UP] };
  return (
    <React.Fragment>
      <TuneView v={v.progress ? tuned : { stale: true, msgs: BASE }} app={app} />
      <RedoPlanModal app={app} v={v} />
    </React.Fragment>
  );
}
STATES.push(
  { stage: 3, group: 10, railOpen: 'History', id: 'history/list', name: 'History: timeline and diff', when: 'F8 from any screen with no editor open. Newest first; the selected row previews as a diff', View: HistoryView, v: {}, go: { v: 'history/text', f: 'history/filter-open', ArrowRight: 'history/event' } },
  { stage: 3, group: 10, railOpen: 'History', id: 'history/text', name: 'History: text preview', when: 'v switches the preview from diff to the full text at that point in time', View: HistoryView, v: { text: true } },
  { stage: 3, group: 10, railOpen: 'History', id: 'history/filter-open', name: 'History: file filter', when: 'Select open; choosing a file hides the other files and the approval and version rows', View: HistoryView, v: { filterOpen: true } },
  { stage: 3, group: 10, railOpen: 'History', id: 'history/filtered', name: 'History: one file', when: 'Filter set to seeds.csv', View: HistoryView, v: { file: 'seeds.csv', cursor: 1 } },
  { stage: 3, group: 10, railOpen: 'History', id: 'history/event', name: 'History: approval row', when: 'An approval or version row is selected: details shown, Restore this disabled', View: HistoryView, v: { cursor: 2 } },
  { stage: 3, group: 10, railOpen: 'History', id: 'history/current', name: 'History: current row', when: 'The newest row of a file is the current text: Restore this disabled', View: HistoryView, v: { cursor: 0 } },
  { stage: 5, group: 10, railOpen: 'Redo plan', id: 'redo/plan', name: 'Redo plan: prompt changed', when: 'F9 with stages 5 to 8 stale. Counts come from classifier.is_cached; Enter jumps to the earliest stale stage', marks: STALE_ALL, View: RedoView, v: { rows: RP_PROMPT } },
  { stage: 5, group: 10, railOpen: 'Redo plan', id: 'redo/plan-seeds', name: 'Redo plan: seeds changed', when: 'Seeds changed: Search stale, Gold dev set incomplete, Threshold stale (partly cached). Rows without model calls show ·', marks: { 2: ['stale', 'seeds changed'], 4: ['incomplete', '44 of 50 rows'], 7: ['stale', 'seeds changed'] }, View: RedoView, v: { rows: RP_SEEDS } },
  { stage: 5, group: 10, railOpen: 'Redo plan', id: 'redo/plan-unpriced', name: 'Redo plan: no price', when: 'The classifier model has no price: dollars are ?, never $0', unknownCost: true, marks: STALE_ALL, View: RedoView, v: { rows: RP_PROMPT, unpriced: true } },
  { stage: 5, group: 10, railOpen: 'Redo plan', id: 'redo/plan-progress', name: 'Redo plan: after a re-approval', when: 'The user re-approved Tuning (F2). The plan opens again with the next stale stage selected; stage 6 is now mostly cached', marks: { 6: ['stale', 'prompt changed'], 7: ['stale', 'prompt changed'], 8: ['stale', 'prompt changed'] }, View: RedoView, v: { rows: RP_PROGRESS, progress: true } },
  { stage: 8, group: 10, railOpen: 'Redo plan', id: 'redo/plan-done', name: 'Redo plan: all current', when: 'No stale or incomplete stage is left; the rail marker and the F9 key disappear', View: RedoView, v: { rows: RP_PROMPT.map((r) => ({ ...r, done: true })), progress: true } },
);
