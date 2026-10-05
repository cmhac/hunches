function SearchView({ v, app }) {
  const counts = v.empty ? HD.bandCounts.map(() => 0) : HD.bandCounts;
  const total = counts.reduce((a, b) => a + b, 0);
  const rows = HD.bands.map((b, i) => [i === HD.bands.length - 1 ? b + '+' : b + '-' + HD.bands[i + 1], fmt(counts[i]), fmt(counts.slice(i).reduce((a, x) => a + x, 0))]);
  rows.push({ cells: ['Total', fmt(total), ''], strong: true });
  const topAll = v.empty ? [] : HD.won.slice(0, 10).map(([n, i]) => [n, HD.seeds[i]]);
  const thr = v.threshold ?? HD.bands[0];
  const thrIdx = Math.max(0, HD.bands.indexOf(thr));
  const factor = total ? counts.slice(thrIdx).reduce((a, x) => a + x, 0) / total : 1;
  const dimmed = v.locked || v.empty;
  const hasRun = !v.empty && !v.seedsChanged;
  const pct = v.running ? Math.round(((v.seedsDone || 0) / (v.seedsTotal || 1)) * 100) : 0;
  const label = v.running ? ' ' + (v.seedsDone || 0) + '/' + (v.seedsTotal || 0) + '  ' + HD.seeds[(v.seedsDone || 1) - 1] + ' ' : '';
  const lab = (c, bg) => <div style={{ position: 'absolute', inset: 0, padding: '0 1ch', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: c, background: bg, fontWeight: 700 }}>{label}</div>;
  const top = topAll.map(([n, sd]) => [Math.round(n * factor), sd]);
  return (
    <React.Fragment>
      <div style={{ display: 'flex', gap: '2ch', alignItems: 'center', padding: '0 1ch', flex: '0 0 auto', marginBottom: 'var(--row)' }}>
        <Button variant="primary" disabled={v.running || v.locked}>  {v.running ? 'Searching…' : (hasRun ? 'Rerun search  r' : 'Run search  r')}  </Button>
        {v.status ? <span style={{ color: v.statusTone === 'warn' ? 'var(--warning)' : v.statusTone === 'ok' ? 'var(--success)' : 'var(--fg-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{v.status}</span> : null}
        {v.running ? (
          <div style={{ position: 'relative', flex: 1, minWidth: 0, height: 'var(--row)', background: 'var(--panel)', overflow: 'hidden' }}>
            {lab('var(--fg-muted)', 'transparent')}
            <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: pct + '%', background: 'var(--primary)', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 'calc(100% * 100 / ' + Math.max(pct, 1) + ')', maxWidth: 'none' }}>{lab('var(--ink-1)', 'transparent')}</div>
            </div>
          </div>
        ) : null}
      </div>
      {v.warning ? <Notice tone="warn">{v.warning}</Notice> : null}
      {v.error ? <Notice tone="error">{v.error}</Notice> : null}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', opacity: dimmed ? 0.4 : 1, pointerEvents: dimmed ? 'none' : 'auto' }}>
      <Panel title="Candidates by similarity" subtitle={fmt(total) + ' total'} focused={!dimmed}>
        <div style={{ display: 'grid', gridTemplateColumns: '11ch minmax(0,1fr) 11ch', gap: '0 2ch', color: 'var(--fg-muted)' }}>
          <span>Similarity</span><span></span><span style={{ textAlign: 'right' }}>Candidates</span>
        </div>
        {HD.bands.map((b, i) => {
          const c = counts[i];
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '11ch minmax(0,1fr) 11ch', gap: '0 2ch', alignItems: 'center' }}>
              <span style={{ color: 'var(--fg-strong)' }}>{i === HD.bands.length - 1 ? b + '+' : b + '–' + HD.bands[i + 1]}</span>
              <div style={{ overflow: 'hidden', whiteSpace: 'nowrap' }}><Bar value={c} max={Math.max(1, ...counts)} width={40} color="var(--primary)" /></div>
              <span style={{ textAlign: 'right', color: c ? 'var(--fg-strong)' : 'var(--fg-faint)', fontWeight: 700 }}>{fmt(c)}</span>
            </div>
          );
        })}
      </Panel>
      <Panel style={{ position: 'relative' }} title="Top seeds" subtitle={<span style={{ whiteSpace: 'pre' }}><span style={{ color: 'var(--fg-muted)' }}>similarity at or above </span><span style={{ background: v.thrOpen ? 'var(--boost)' : 'var(--panel)', color: 'var(--fg-strong)', fontWeight: 700, padding: '0 1ch', boxShadow: v.thrOpen ? 'inset 0.5ch 0 0 var(--primary)' : 'none' }}>{String(thr)} {v.thrOpen ? '▲' : '▼'}</span></span>} grow>
        {v.thrOpen ? (
          <div style={{ position: 'absolute', right: 'var(--panel-gx, 0px)', top: 'var(--row)', zIndex: 5, background: 'var(--panel)', boxShadow: '0 0 0 1px var(--ink-5)', minWidth: '10ch' }}>
            {HD.bands.map((b) => <div key={b} style={{ padding: '0 1ch', background: b === thr ? 'var(--boost)' : 'transparent', boxShadow: b === thr ? 'inset 0.5ch 0 0 var(--primary)' : 'none', color: b === thr ? 'var(--fg-strong)' : 'var(--fg)', fontWeight: b === thr ? 700 : 400 }}>{String(b)}</div>)}
          </div>
        ) : null}
        {top.length ? top.map(([n, sd], i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '3ch 7ch 14ch minmax(0,1fr)', gap: '0 1ch', whiteSpace: 'nowrap', alignItems: 'center' }}>
            <span style={{ color: 'var(--fg-faint)', textAlign: 'right' }}>{i + 1}</span>
            <span style={{ textAlign: 'right', ...strong }}>{fmt(n)}</span>
            <span><Bar value={n} max={top[0][0]} width={12} color={i === 0 ? 'var(--accent)' : 'var(--primary)'} /></span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', color: i === 0 ? 'var(--fg-strong)' : 'var(--fg)' }}>{sd}</span>
          </div>
        )) : <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--fg-muted)', whiteSpace: 'pre-wrap', padding: '0 2ch' }}>Run the search to see which seeds find the most items.</div>}
      </Panel>
      </div>
      <Footer keys={K(['r', hasRun ? 'Rerun search' : 'Run search'])} />
      {v.modal ? (
        <Modal title="Rerun search?" width={64} dense actions={<React.Fragment><Button>Cancel</Button><Button variant="primary" focused>Rerun search</Button></React.Fragment>}>
          <div style={{ whiteSpace: 'pre-wrap' }}>You've already run the searches, and haven't changed the seed candidates. Depending on the size of the corpus, this can take a long time. Are you sure you want to rerun searches?</div>
        </Modal>
      ) : null}
    </React.Fragment>
  );
}
STATES.push(
  { stage: 2, id: 'search/not-approved', name: 'Seeds not approved', when: 'Reached with n before approving seeds', View: SearchView, v: { empty: true, locked: true, status: 'Seeds are not approved yet.', statusTone: 'warn' } },
  { stage: 2, id: 'search/never-run', name: 'Not run yet', when: 'Seeds approved, no candidates.jsonl', View: SearchView, v: { empty: true }, go: { r: 'search/running' } },
  { stage: 2, id: 'search/running', name: 'Searching', when: 'r pressed; button disabled', View: SearchView, v: { empty: true, running: true, seedsDone: 4, seedsTotal: 12 }, go: { r: 'search/done' } },
  { stage: 2, id: 'search/done', name: 'Done', when: 'Search finished', View: SearchView, go: { r: 'search/confirm' }, v: { long: 'Done. 3,612 candidates written to candidates.jsonl. Re-running overwrites it; gold labels refer to ids and stay valid, but refresh sample sets if the candidate set changed a lot.' } },
  { stage: 2, id: 'search/resumed', name: 'Resumed', when: 'Reopened: last run shown, no status', View: SearchView, go: { r: 'search/confirm' }, v: {} },
  { stage: 2, id: 'search/seeds-changed', name: 'Seeds changed', when: 'seeds.csv edited since candidates.jsonl was written: no confirmation on run', View: SearchView, go: { r: 'search/running' }, v: { seedsChanged: true, status: 'Seeds changed, rerun needed', statusTone: 'warn' } },
  { stage: 2, id: 'search/top-filtered', name: 'Top seeds, filtered', when: 'Similarity threshold above the first band: counts include only items at or above it', View: SearchView, v: { threshold: 0.7 } },
  { stage: 2, id: 'search/threshold-open', name: 'Top seeds, threshold picker', when: 'Select open on the similarity threshold', View: SearchView, v: { threshold: 0.65, thrOpen: true } },
  { stage: 2, id: 'search/confirm', name: 'Confirm rerun', when: 'r with candidates.jsonl already present', View: SearchView, go: { Enter: 'search/running' }, v: { modal: true } },
  { stage: 2, id: 'search/capped', name: 'S3 hit cap reached', when: 'S3 backend returned its cap for a seed', View: SearchView, v: { long: 'Done. 3,612 candidates written to candidates.jsonl.', warning: 'WARNING: S3 returned its cap of 10,000 hits for at least one seed; only the 10,000 highest-scoring hits are kept.' } },
  { stage: 2, id: 'search/mismatch', name: 'Embedding mismatch', when: 'Search failed; message contains "mismatch"', View: SearchView, v: { empty: true, error: 'Search failed: embedding model mismatch: corpus is openai:text-embedding-3-large, config is openai:text-embedding-3-small\nFix: set embedding_model in .hunches/config.toml to the model the corpus was embedded with.' } },
  { stage: 2, id: 'search/error', name: 'Search failed', when: 'Any other error', View: SearchView, v: { empty: true, error: 'Search failed: [Errno 2] No such file or directory: corpus/vectors.npy' } },
);
