function FinalView({ v }) {
  const keys = [['r', 'Re-run'], ['t', 'Back to tuning'], ['F2', 'Accept']];
  const m = v.m === undefined ? M_TEST : v.m;
  const tone = v.note && /failed/.test(v.note) ? 'error' : v.note && /^Running|finished/.test(v.note) ? 'note' : 'warn';
  return (
    <React.Fragment>
      {v.stale ? <Notice tone="stale" banner>STALE: prompt.md changed since this result was computed. Press r to re-run.</Notice> : null}
      <MetricsPanel title={'test set · held out' + (m ? ' · 2026-10-02 20:41:07Z' : '')} m={m} metric="accuracy" target={0.9}
        top={<div style={{ color: 'var(--fg-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Tuning against test disagreements weakens this held-out result.</div>} />
      <DisView items={m ? HD.dis.slice(1, 6) : []} cursor={v.cursor ?? 0} detailExtra={false} />
      <Notice tone={tone}>{v.note || ''}</Notice>
      <Footer keys={K(...keys)} />
    </React.Fragment>
  );
}
STATES.push(...goldStates(6, 'test').filter((s) => ['test/single', 'test/differs', 'test/multi', 'test/unfinished', 'test/confirm'].includes(s.id)).map((s) => ({ ...s, name: 'Labelling: ' + s.name.toLowerCase() })));
STATES.push(
  { stage: 6, id: 'final/first-run', name: 'First test run', when: 'Test set labelled; the one automatic run', View: FinalView, v: { m: null, note: 'Running test set 18/50...' } },
  { stage: 6, id: 'final/result', name: 'Result', when: 'test_result.json matches prompt.md', View: FinalView, v: { note: 'Test run finished, cost $0.0158.' }, go: { t: 'tune/below' } },
  { stage: 6, id: 'final/stale', name: 'Stale result', when: 'prompt.md changed since the run', View: FinalView, v: {}, go: { F2: 'final/stale-accept', r: 'final/rerun' } },
  { stage: 6, id: 'final/stale-accept', name: 'Accept while stale', when: 'F2 on a stale result', View: FinalView, v: { stale: true, note: 'The result is stale: re-run (r) before accepting.' } },
  { stage: 6, id: 'final/rerun', name: 'Re-running', when: 'r pressed', View: FinalView, v: { stale: true, note: 'Running test set 9/50...' } },
  { stage: 6, id: 'final/run-failed', name: 'Test run failed', when: 'Auth or network error', View: FinalView, v: { m: null, note: 'Test run failed: status_code: 401, body: invalid x-api-key' } },
);
STATES.find((s) => s.id === 'final/stale').v.stale = true;
