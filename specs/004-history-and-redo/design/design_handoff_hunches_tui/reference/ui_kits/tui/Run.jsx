function RunView({ v, app }) {
  const keys = [['s', 'Start/resume'], ['x', 'Stop']];
  if (v.notReady) return <NotReady text="Finish stages 3 and 7 first." keys={keys} />;
  const total = v.total ?? 3612;
  return (
    <React.Fragment>
      <Panel title="estimate">
        <div style={{ whiteSpace: 'pre-wrap' }}>{v.estimate}</div>
      </Panel>
      {v.warn ? <Notice tone="warn" banner>{v.warn}</Notice> : null}
      <Panel title="run · results.jsonl" subtitle={v.subtitle} focused grow>
        <ProgressBar value={v.done || 0} total={total} width={Math.max(10, app.cols - 24)} eta={v.eta} />
        <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: v.live && /failed/.test(v.live) ? 'var(--error)' : 'var(--fg)' }}>{v.live || ''}</div>
        {v.errors ? (
          <React.Fragment>
            <div style={{ height: 'var(--row)' }}></div>
            <div style={{ color: 'var(--warning)', fontWeight: 700 }}>Failed (retried next run):</div>
            {v.errors.map((e, i) => <div key={i} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...muted }}>{e}</div>)}
          </React.Fragment>
        ) : null}
      </Panel>
      <Footer keys={K(...keys)} />
    </React.Fragment>
  );
}
const EST = '3612 items to classify; time ~14m41s at 4.10 items/s; cost ~$1.1194';
STATES.push(
  { stage: 8, id: 'run/not-ready', name: 'Not ready', when: 'Reached before stages 3 and 7', View: RunView, v: { notReady: true } },
  { stage: 8, id: 'run/idle', name: 'Ready to start', when: 'Estimate from sample timings and usage', View: RunView, v: { estimate: EST, subtitle: 'not started' }, go: { s: 'run/running' } },
  { stage: 8, id: 'run/no-samples', name: 'No estimate yet', when: 'No timings or usage recorded', View: RunView, v: { estimate: '3612 items to classify; time no timing samples yet, so no time estimate; cost no sample usage yet, so no cost estimate', subtitle: 'not started' } },
  { stage: 8, id: 'run/price-unknown', name: 'Price unknown', when: 'genai-prices has no price for the model', unknownCost: true, View: RunView, v: { estimate: '3612 items to classify; time ~14m41s at 4.10 items/s; cost cost ? (WARNING: price unknown for this model)', subtitle: 'not started' } },
  { stage: 8, id: 'run/untested', name: 'Untested prompt', when: 's when prompt.md differs from the tested prompt', View: RunView, v: { estimate: EST, warn: 'WARNING: prompt.md differs from the tested prompt (or was never tested). Press s again to start anyway.', subtitle: 'not started' } },
  { stage: 8, id: 'run/running', name: 'Running', when: 'Live progress, cost, rate, ETA', View: RunView, v: { estimate: EST, done: 1841, live: '1841/3612 | cost $0.5707 | 4.18 items/s | ETA 7m04s', subtitle: 'running' }, go: { x: 'run/stopped' } },
  { stage: 8, id: 'run/stopped', name: 'Stopped, with failures', when: 'x pressed; failed items listed', View: RunView, v: { estimate: '1774 items to classify; time ~7m13s at 4.10 items/s; cost ~$0.5499', done: 1841, live: '1841/3612 | cost $0.5707 | 4.18 items/s | ETA 7m04s', errors: ['a3f81c: status_code: 429, rate_limit_error', '0b19e4: Exceeded maximum retries (1) for output validation'], subtitle: 'stopped · resumable' } },
  { stage: 8, id: 'run/complete', name: 'Complete', when: 'Every candidate ≥ threshold has a result', View: RunView, v: { estimate: 'Nothing to classify; every candidate at or above the threshold is done.', done: 3612, live: '3612/3612 | cost $1.1203 | 4.11 items/s | ETA 0m00s', subtitle: 'complete' } },
  { stage: 8, id: 'run/failed', name: 'Run failed', when: 'Auth or network error', View: RunView, v: { estimate: '3405 items to classify; time ~13m51s at 4.10 items/s; cost ~$1.0553', done: 207, live: 'Run failed: status_code: 401, body: invalid x-api-key', subtitle: 'stopped · resumable' } },
);
