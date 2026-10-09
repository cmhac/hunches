function ProposalModal({ app }) {
  return (
    <Modal title="Proposed prompt change" dense width={app.cols - 4} height={app.rows - 2}
      actions={<React.Fragment><Button>Reject</Button><Button variant="success" focused>Accept</Button></React.Fragment>}>
      <div style={{ color: 'var(--fg-muted)', padding: '0 1ch' }}>Built from 7 disagreements. Edit the proposal below; the diff follows.</div>
      <Panel title="diff · current → proposed" grow pad={0} bg="var(--surface)"><Diff text={HD.diff} /></Panel>
      <TextArea title="proposal (editable)" language="markdown" text={HD.proposed} focused cursorLine={4} />
    </Modal>
  );
}
function TuneView({ v, app }) {
  const keys = [['e', 'Propose prompt edit'], ['m', 'Target metric'], ['+', 'Target +'], ['-', 'Target -'], ['F2', 'Done']];
  if (v.notReady) return <NotReady text="Finish stage 3 (taxonomy and prompt) first." keys={keys} />;
  const metric = v.metric || 'accuracy';
  const target = v.target ?? 0.9;
  const m = v.m === undefined ? M_DEV : v.m;
  const items = v.dis ?? HD.dis;
  const tone = v.noteTone || (v.note && /failed/.test(v.note) ? 'error' : v.note && /^Running|^Asking|finished/.test(v.note) ? 'note' : 'warn');
  return (
    <React.Fragment>
      <MetricsPanel title="dev set" m={m} metric={metric} target={target} subtitle={'target ' + metric + ' ≥ ' + target.toFixed(2) + ' · m metric · +/- score'} trend={v.trend} />
      <DisView items={m ? items : []} cursor={v.cursor ?? 0} />
      <Notice tone={tone}>{v.note || ''}</Notice>
      <Footer keys={K(...keys)} />
      {v.modal === 'proposal' ? <ProposalModal app={app} /> : null}
      {v.modal === 'confirm' ? <ConfirmModal q={metric + ' ' + targetValue(m, metric).toFixed(3) + ' is below the target ' + target.toFixed(2) + '. Accept tuning anyway?'} /> : null}
    </React.Fragment>
  );
}
STATES.push(
  { stage: 5, id: 'tune/not-ready', name: 'Not ready', when: 'Reached before stage 3', View: TuneView, v: { notReady: true } },
  { stage: 5, id: 'tune/first-run', name: 'First dev run', when: 'On mount: dev set classified, no metrics yet', View: TuneView, v: { m: null, note: 'Running dev set 23/50...' } },
  { stage: 5, id: 'tune/below', name: 'Below target', when: 'Run finished; FAIL', View: TuneView, v: { note: 'Dev run finished, cost $0.0154.' }, go: { e: 'tune/asking', F2: 'tune/confirm', m: 'tune/metric' } },
  { stage: 5, id: 'tune/failed-item', name: 'Failed item selected', when: 'Cursor on a row whose call failed', View: TuneView, v: { cursor: 5 } },
  { stage: 5, id: 'tune/metric', name: 'Other target metric', when: 'm cycles accuracy → macro_f1 → micro_f1 → exact_match', View: TuneView, v: { metric: 'macro_f1', target: 0.85 } },
  { stage: 5, id: 'tune/asking', name: 'Asking smart model', when: 'e pressed', View: TuneView, v: { note: 'Asking the smart model...' }, go: { e: 'tune/proposal' } },
  { stage: 5, id: 'tune/proposal', name: 'Prompt proposal', when: 'Smart model replied; diff + editable proposal', View: TuneView, v: { modal: 'proposal' }, go: { Enter: 'tune/rerun' } },
  { stage: 5, id: 'tune/rerun', name: 'Re-running after accept', when: 'Accepted proposal; prompt.md written', View: TuneView, v: { note: 'Running dev set 31/50...', trend: [0.86] } },
  { stage: 5, id: 'tune/pass', name: 'Target met', when: 'PASS, with trend across prompt versions', View: TuneView, v: { m: M_DEV2, dis: HD.dis.slice(0, 4), trend: [0.86, 0.92], note: 'Dev run finished, cost $0.0021.' } },
  { stage: 5, id: 'tune/no-dis', name: 'No disagreements', when: 'e with nothing to learn from', View: TuneView, v: { m: { exact_match: 1, macro_f1: 1, micro_f1: 1, n: 50, per: PER.dev2.map(([n, , , , g]) => [n, 1, 1, 1, g]) }, dis: [], note: 'No disagreements to learn from.' } },
  { stage: 5, id: 'tune/run-failed', name: 'Dev run failed', when: 'Auth or network error during the run', View: TuneView, v: { m: null, note: 'Dev run failed: status_code: 401, body: invalid x-api-key' } },
  { stage: 5, id: 'tune/proposal-failed', name: 'Proposal failed', when: 'Smart model call errored', View: TuneView, v: { note: 'Proposal failed: status_code: 529, overloaded_error' } },
  { stage: 5, id: 'tune/confirm', name: 'Accept below target', when: 'F2 while FAIL', View: TuneView, v: { modal: 'confirm' } },
);
