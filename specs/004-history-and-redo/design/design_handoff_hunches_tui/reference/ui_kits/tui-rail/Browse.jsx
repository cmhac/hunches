function BrowseView({ v, app }) {
  const sel = v.selected || [];
  const q = (v.search || '').toLowerCase();
  const items = HD.results.filter((r) => (!q || r.text.toLowerCase().includes(q)) && (!sel.length || r.labels.some((l) => sel.includes(l))));
  const rows = v.empty ? [] : items;
  const cur = Math.min(v.cursor ?? 0, Math.max(0, rows.length - 1));
  const it = rows[cur];
  const narrow = app.cols < 100;
  const total = v.empty ? 0 : 3612;
  const shown = v.empty ? 0 : v.overflow ? 1000 : q || sel.length ? rows.length * 37 : 1000;
  const count = v.empty ? 'Showing 0 of 0' : 'Showing ' + fmt(Math.min(shown, 1000)) + ' of ' + fmt(total) + (v.overflow ? ' (2,904 match; refine the search)' : '');
  const focus = v.focus || 'table';
  const table = (
    <Panel title="results.jsonl" subtitle={count} focused={focus === 'table'} grow={2} pad={0}>
      {rows.length ? (
        <DataTable cursor={cur} focused={focus === 'table'} columns={[{ label: 'ID', width: '8ch' }, { label: 'Labels', width: narrow ? '16ch' : '30ch' }, { label: 'Sim', width: '7ch', align: 'right' }, { label: 'Text', width: 'minmax(0,1fr)' }]}
          rows={rows.slice(0, 30).map((r) => ({ cells: [r.id, <Labels names={r.labels} />, r.sim.toFixed(3), r.text], key: r.id }))} />
      ) : <div style={{ ...muted, padding: '0 1ch' }}>{v.empty ? 'results.jsonl is empty. Run stage 8 first.' : 'No results match.'}</div>}
    </Panel>
  );
  const detail = (
    <Panel title={it ? 'item ' + it.id : 'item'} grow={1} style={narrow ? { flex: '0 0 calc(var(--row) * 5)' } : undefined}>
      <div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg-strong)' }}>{it ? it.text : ''}</div>
    </Panel>
  );
  return (
    <React.Fragment>
      {v.stale ? <Notice tone="warn" banner>Results come from an older prompt: prompt.md changed after the full run. Press p to go to Full run and re-run.</Notice> : null}
      <Input value={v.search || ''} placeholder="Search text (case-insensitive)" focused={focus === 'search'} />
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Panel title="labels" focused={focus === 'labels'} style={{ flex: '0 0 24ch' }} pad={0}>
          {HD.labels.map((l, i) => {
            const on = sel.includes(l.name);
            const c = focus === 'labels' && i === (v.labelCursor ?? 0);
            return (
              <div key={l.name} style={{ display: 'flex', gap: '1ch', padding: '0 1ch', background: c ? 'var(--boost)' : 'transparent', whiteSpace: 'nowrap', overflow: 'hidden' }}>
                <span style={{ color: on ? 'var(--primary)' : 'var(--fg-faint)', fontWeight: 700 }}>{on ? '■' : '□'}</span>
                <LabelTag name={l.name} color={l.color} />
              </div>
            );
          })}
        </Panel>
        {narrow ? <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>{table}{detail}</div> : <React.Fragment>{table}{detail}</React.Fragment>}
      </div>
      <Footer keys={K(['tab', 'Focus'])} />
    </React.Fragment>
  );
}
STATES.push(
  { stage: 9, id: 'browse/all', name: 'All results', when: 'First 1,000 rows drawn', View: BrowseView, v: {}, go: { '/': 'browse/search' } },
  { stage: 9, id: 'browse/stale', name: 'Results from an older prompt', when: 'results.jsonl is current for its own run, but the run digest no longer matches prompt.md', marks: { 8: ['stale', 'prompt changed'] }, View: BrowseView, v: { stale: true } },
  { stage: 9, id: 'browse/search', name: 'Text search', when: 'Typing filters on every change', View: BrowseView, v: { search: 'severance', focus: 'search' } },
  { stage: 9, id: 'browse/labels', name: 'Label filter', when: 'SelectionList: rows with any checked label', View: BrowseView, v: { selected: ['hiring_freeze'], focus: 'labels', labelCursor: 2 } },
  { stage: 9, id: 'browse/overflow', name: 'Over 1,000 matches', when: 'Only the first 1,000 are drawn', View: BrowseView, v: { search: 'laid', overflow: true } },
  { stage: 9, id: 'browse/no-match', name: 'No matches', when: 'Filters exclude everything', View: BrowseView, v: { search: 'pension buyout', focus: 'search' } },
  { stage: 9, id: 'browse/empty', name: 'No results', when: 'results.jsonl missing or only failed rows', View: BrowseView, v: { empty: true } },
);
