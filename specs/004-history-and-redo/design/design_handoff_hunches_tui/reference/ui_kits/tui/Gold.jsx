function GoldView({ v, app }) {
  if (v.notReady) return <NotReady text="Finish stage 3 (taxonomy and prompt) first." keys={[['←', 'Back'], ['→', 'Skip'], ['enter', 'Confirm labels'], ['d', 'Draw 10 more'], ['F2', 'Finish']]} />;
  const split = v.split || 'dev';
  const mode = v.mode || 'single';
  const total = v.total || 50;
  const done = v.done ?? 17;
  const idx = v.idx ?? done;
  const chosen = v.chosen || [];
  const counts = v.counts || [7, 4, 2, 4];
  const right = Math.min(30, Math.floor(app.cols * 0.36));
  const p = v.pred;
  let predEl = null;
  if (p === 'not') predEl = <span style={muted}>Model: (not classified)</span>;
  else if (p === 'classifying') predEl = <span style={muted}>Model: classifying...</span>;
  else if (p === 'failed') predEl = <span style={{ color: 'var(--error)' }}>Model: failed (status_code: 429, rate_limit_error)</span>;
  else if (p) predEl = <span style={{ display: 'inline-flex', gap: '1ch' }}><span style={muted}>Model:</span><Labels names={p.labels} />{p.agrees ? <span style={{ color: 'var(--success)' }}>✓ agrees</span> : <Badge tone="info">DIFFERS</Badge>}</span>;
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ display: 'flex', gap: '2ch', padding: '0 1ch', whiteSpace: 'nowrap' }}>
            <span style={{ color: 'var(--primary)', fontWeight: 700 }}>{split} set</span>
            <span><span style={muted}>item </span><span style={strong}>{idx + 1}</span><span style={muted}>/{total}, </span><span style={strong}>{done}</span><span style={muted}> labelled</span></span>
            <span style={{ flex: 1 }}></span>
          </div>
          <Panel title={'item ' + (v.id || '7f3a91')} focused grow>
            <div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg-strong)' }}>{v.text || HD.texts[idx % HD.texts.length]}</div>
          </Panel>
          <Panel title={'labels · ' + mode} subtitle={mode === 'single' ? 'press a key to label' : 'keys toggle, enter confirms'}>
            {HD.labels.map((l, i) => <LabelOption key={l.name} k={l.name === 'off_topic' ? '0' : String(i + 1)} name={l.name} description={l.description} color={l.color} mode={mode} checked={chosen.includes(l.name)} />)}
          </Panel>
          <div style={{ padding: '0 1ch', whiteSpace: 'nowrap', overflow: 'hidden', minHeight: 'var(--row)' }}>{predEl}</div>
          <div style={{ padding: '0 1ch', whiteSpace: 'nowrap', overflow: 'hidden', color: 'var(--warning)', minHeight: 'var(--row)' }}>{v.note || ''}</div>
        </div>
        <div style={{ flex: '0 0 ' + right + 'ch', display: 'flex', flexDirection: 'column' }}>
          <Panel title="counts" subtitle={done + ' of ' + total} grow pad={0}>
            <DataTable cursor={-1} columns={[{ label: 'Label', width: 'minmax(0,1fr)' }, { label: 'Count', width: '7ch', align: 'right' }]}
              rows={HD.labels.map((l, i) => [<LabelTag name={l.name} color={l.color} />, String(counts[i])])} />
          </Panel>
        </div>
      </div>
      <Footer keys={K(['←', 'Back'], ['→', 'Skip'], ['enter', 'Confirm labels'], ['d', 'Draw 10 more'], ['F2', 'Finish'])} />
      {v.modal ? <ConfirmModal q="All items labelled. Continue?" /> : null}
    </React.Fragment>
  );
}
const goldStates = (stage, split) => {
  const s = split + '-';
  const pre = split === 'dev' ? 'gold' : 'test';
  const list = [
    { id: pre + '/single', name: 'Single mode', when: 'Unlabelled item; a key labels and advances', v: { split }, go: { '1': pre + '/agrees' } },
    { id: pre + '/classifying', name: 'Model classifying', when: 'Back (←) to an item just labelled', v: { split, idx: 16, chosen: ['layoff_story'], pred: 'classifying' } },
    { id: pre + '/agrees', name: 'Model agrees', when: 'Labelled item, prediction matches', v: { split, idx: 16, chosen: ['layoff_story'], pred: { labels: ['layoff_story'], agrees: true } } },
    { id: pre + '/differs', name: 'Model differs', when: 'Labelled item, prediction differs', v: { split, idx: 16, chosen: ['layoff_fear'], pred: { labels: ['off_topic'], agrees: false } } },
    { id: pre + '/pred-failed', name: 'Model failed', when: 'Classification call errored', v: { split, idx: 16, chosen: ['layoff_story'], pred: 'failed' } },
    { id: pre + '/not-classified', name: 'Not classified', when: 'Item labelled in an earlier session', v: { split, idx: 3, chosen: ['hiring_freeze'], pred: 'not' } },
    { id: pre + '/multi', name: 'Multi mode, toggling', when: 'mode: multi; keys toggle, enter confirms', v: { split, mode: 'multi', chosen: ['layoff_story', 'hiring_freeze'] } },
    { id: pre + '/multi-invalid', name: 'Multi mode, nothing chosen', when: 'enter with no labels toggled', v: { split, mode: 'multi', chosen: [], note: 'Not saved: at least one label is required' } },
    { id: pre + '/exhausted', name: 'Pool exhausted', when: 'd drew fewer than 10', v: { split, total: 56, note: 'Only 6 unlabelled candidates were left to draw.' } },
    { id: pre + '/unfinished', name: 'Finish too early', when: 'F2 with unlabelled items', v: { split, note: '33 items still unlabelled.' } },
    { id: pre + '/confirm', name: 'Finish', when: 'F2 with every item labelled', v: { split, done: 50, idx: 49, chosen: ['off_topic'], pred: { labels: ['off_topic'], agrees: true }, counts: [19, 11, 6, 14], modal: true } },
  ];
  if (split === 'dev') list.unshift({ id: 'gold/not-ready', name: 'Not ready', when: 'Reached before stage 3', v: { notReady: true } });
  return list.map((x) => ({ stage, View: GoldView, ...x }));
};
STATES.push(...goldStates(4, 'dev'));
