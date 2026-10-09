function FinalView({ v }) {
  const keys = [['r', 'Re-run'], ['t', 'Back to tuning'], ['F2', 'Accept']];
  if (v.running) return <RunningView label="Running the held-out test set" done={v.running[0]} total={v.running[1]} sub={v.sub} keys={keys} />;
  const m = v.m === undefined ? M_TEST : v.m;
  const tone = v.note && /failed/.test(v.note) ? 'error' : v.note && /^Running|finished/.test(v.note) ? 'note' : 'warn';
  return (
    <React.Fragment>
      {v.stale ? <Notice tone="stale" banner>STALE: prompt.md or classifier model changed since this result was computed. Press r to re-run.</Notice> : null}
      <MetricsPanel title={'test set · held out' + (m ? ' · 2026-10-02 20:41:07Z' : '')} m={m} metric="accuracy" target={0.9}
        top={<div style={{ color: 'var(--fg-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Tuning against test disagreements weakens this held-out result.</div>} />
      <DisView items={m ? HD.dis.slice(1, 6) : []} cursor={v.cursor ?? 0} detailExtra={false} />
      <ActionRow>
        <Button> Re-run r </Button>
        <Button> Back to tuning t </Button>
        <span style={{ flex: 1 }}></span>
        <Button variant="success" disabled={!m || v.stale}> Accept F2 </Button>
      </ActionRow>
      {v.note ? <Notice tone={tone}>{v.note}</Notice> : null}
      <Footer keys={K(...keys)} />
    </React.Fragment>
  );
}
STATES.push(...goldStates(6, 'test').filter((s) => ['test/single', 'test/multi', 'test/confirm', 'test/exhausted', 'test/pool-short', 'test/orphans', 'test/rows', 'test/remove-confirm', 'test/orphans-removed'].includes(s.id)).map((s) => ({ ...s, name: 'Labelling: ' + s.name.toLowerCase() })));
STATES.push(
  { stage: 6, id: 'final/first-run', name: 'First test run', when: 'Test set labelled; the one automatic run', View: FinalView, v: { running: [18, 50], sub: 'classifier ' + HD.cheap } },
  { stage: 6, id: 'final/result', name: 'Result', when: 'test_result.json matches prompt.md', View: FinalView, v: { note: 'Test run finished, cost $0.0158.' }, go: { t: 'tune/below' } },
  { stage: 6, id: 'final/stale', name: 'Stale result', when: 'prompt.md changed since the run', View: FinalView, v: {}, go: { F2: 'final/stale-accept', r: 'final/rerun' } },
  { stage: 6, id: 'final/stale-accept', name: 'Accept while stale', when: 'F2 on a stale result', View: FinalView, v: { stale: true, note: 'The result is stale: re-run (r) before accepting.' } },
  { stage: 6, id: 'final/rerun', name: 'Re-running', when: 'r pressed', View: FinalView, v: { running: [9, 50], sub: 'prompt changed since the last run' } },
  { stage: 6, id: 'final/run-failed', name: 'Test run failed', when: 'Auth or network error', View: FinalView, v: { m: null, note: 'Test run failed: status_code: 401, body: invalid x-api-key' } },
);
STATES.find((s) => s.id === 'final/stale').v.stale = true;
STATES.find((s) => s.id === 'final/stale').marks = STALE_ALL;
