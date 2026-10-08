function SearchView({ v, app }) {
  const counts = v.empty ? HD.bandCounts.map(() => 0) : HD.bandCounts;
  const total = counts.reduce((a, b) => a + b, 0);
  const rows = HD.bands.map((b, i) => [i === HD.bands.length - 1 ? b + '+' : b + '-' + HD.bands[i + 1], fmt(counts[i]), fmt(counts.slice(i).reduce((a, x) => a + x, 0))]);
  rows.push({ cells: ['Total', fmt(total), ''], strong: true });
  const top = v.empty ? [] : [[1412, HD.seeds[0]], [988, HD.seeds[1]], [702, HD.seeds[2]], [541, HD.seeds[5]], [390, HD.seeds[7]], [277, HD.seeds[4]], [190, HD.seeds[9]], [112, HD.seeds[3]], [61, HD.seeds[10]], [29, HD.seeds[11]]];
  return (
    <React.Fragment>
      <div style={{ display: 'flex', gap: '2ch', alignItems: 'center', padding: '0 1ch', flex: '0 0 auto' }}>
        <Button compact disabled={v.running}>Run search (r)</Button>
        {v.status ? <span style={{ color: v.statusTone === 'warn' ? 'var(--warning)' : v.statusTone === 'ok' ? 'var(--success)' : 'var(--fg-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{v.status}</span> : null}
      </div>
      {v.long ? <Notice tone="ok">{v.long}</Notice> : null}
      {v.warning ? <Notice tone="warn">{v.warning}</Notice> : null}
      {v.error ? <Notice tone="error">{v.error}</Notice> : null}
      <Panel title="candidates.jsonl · by similarity band" focused>
        <DataTable cursor={-1} columns={[{ label: 'Band', width: '13ch' }, { label: 'Candidates', width: '12ch', align: 'right' }, { label: 'At or above', width: '13ch', align: 'right' }, { label: '', width: 'minmax(0,1fr)' }]} rows={rows.map((r) => (Array.isArray(r) ? [...r, ''] : { ...r, cells: [...r.cells, ''] }))} />
      </Panel>
      <Panel title="best seed (items won)" grow>
        {top.length ? top.map(([n, s], i) => (
          <div key={i} style={{ display: 'flex', gap: '2ch', whiteSpace: 'nowrap' }}><span style={{ flex: '0 0 6ch', textAlign: 'right', ...strong }}>{fmt(n)}</span><span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{s}</span></div>
        )) : <span style={muted}>Run the search to see which seeds find the most items.</span>}
      </Panel>
      <Footer keys={K(['r', 'Run search'])} />
    </React.Fragment>
  );
}
STATES.push(
  { stage: 2, id: 'search/not-approved', name: 'Seeds not approved', when: 'Reached with n before approving seeds', View: SearchView, v: { empty: true, status: 'Seeds are not approved yet.', statusTone: 'warn' } },
  { stage: 2, id: 'search/never-run', name: 'Not run yet', when: 'Seeds approved, no candidates.jsonl', View: SearchView, v: { empty: true }, go: { r: 'search/running' } },
  { stage: 2, id: 'search/running', name: 'Searching', when: 'r pressed; button disabled', View: SearchView, v: { empty: true, running: true, status: 'Searching...' }, go: { r: 'search/done' } },
  { stage: 2, id: 'search/done', name: 'Done', when: 'Search finished', View: SearchView, v: { long: 'Done. 3,612 candidates written to candidates.jsonl. Re-running overwrites it; gold labels refer to ids and stay valid, but refresh sample sets if the candidate set changed a lot.' } },
  { stage: 2, id: 'search/resumed', name: 'Resumed', when: 'Reopened: last run shown, no status', View: SearchView, v: {} },
  { stage: 2, id: 'search/capped', name: 'S3 topK cap hit', when: 'S3 backend returned its cap for a seed', View: SearchView, v: { long: 'Done. 3,612 candidates written to candidates.jsonl.', warning: 'WARNING: S3 returned its topK cap of 30 hits for at least one seed; only the highest-scoring hits are kept.' } },
  { stage: 2, id: 'search/mismatch', name: 'Embedding mismatch', when: 'Search failed; message contains "mismatch"', View: SearchView, v: { empty: true, error: 'Search failed: embedding model mismatch: corpus is openai:text-embedding-3-large, config is openai:text-embedding-3-small\nFix: set embedding_model in .hunches/config.toml to the model the corpus was embedded with.' } },
  { stage: 2, id: 'search/error', name: 'Search failed', when: 'Any other error', View: SearchView, v: { empty: true, error: 'Search failed: [Errno 2] No such file or directory: corpus/vectors.npy' } },
);
