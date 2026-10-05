const MILESTONES = [[0.25, 'a quarter of the way'], [0.5, 'halfway'], [0.75, 'three quarters'], [1, 'done']];
function GoldProgress({ split, done, total, idx, celebrate }) {
  const pct = total ? (done / total) * 100 : 0;
  const left = total - done;
  const complete = left === 0 && total > 0;
  const marks = MILESTONES.map(([f, n]) => [Math.ceil(total * f), n, f]);
  const next = marks.find(([q]) => q > done);
  const hit = marks.find(([q]) => q === done && done > 0);
  const color = complete ? 'var(--success)' : 'var(--primary)';
  const lab = (c) => <div style={{ position: 'absolute', inset: 0, textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden', color: c, fontWeight: 700 }}>{done} / {total}</div>;
  return (
    <div style={{ flex: '0 0 auto', padding: '0 var(--panel-gx, 0px) var(--panel-gap, 0px) 0' }}>
      <div style={{ background: 'var(--surface)', boxShadow: 'inset 0.5ch 0 0 ' + color, padding: 'var(--row) 2ch' }}>
        <div style={{ display: 'flex', gap: '2ch', whiteSpace: 'nowrap', alignItems: 'baseline' }}>
          <span style={{ color, fontWeight: 700 }}>{split} set</span>
          <span style={muted}>item {Math.min(idx + 1, total)}</span>
          <span style={{ flex: 1 }}></span>
          <span style={{ color: complete ? 'var(--success)' : 'var(--fg-strong)', fontWeight: 700 }}>{complete ? 'Complete' : left + ' to go'}</span>
        </div>
        <div style={{ position: 'relative', height: 'var(--row)', background: 'var(--panel)', overflow: 'hidden', margin: 'var(--row) 0 0' }}>
          {lab('var(--fg-muted)')}
          <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: pct + '%', background: color, overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 'calc(100% * 100 / ' + Math.max(pct, 1) + ')' }}>{lab('var(--ink-1)')}</div>
          </div>
          {[25, 50, 75].map((p) => <div key={p} style={{ position: 'absolute', top: 0, bottom: 0, left: p + '%', width: '1px', background: 'var(--surface)' }}></div>)}
        </div>
        <div style={{ display: 'flex', gap: '2ch', whiteSpace: 'nowrap', overflow: 'hidden' }}>
          <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {complete ? <span style={{ color: 'var(--success)' }}>All labelled. Press Finish.</span>
              : celebrate && hit ? <React.Fragment><span style={{ color: 'var(--success)', fontWeight: 700 }}>{hit[1].charAt(0).toUpperCase() + hit[1].slice(1)}.</span><span style={muted}> {left} to go.</span></React.Fragment>
              : next ? <span style={muted}>Next milestone: {next[1]} · {next[0] - done} more</span> : null}
          </span>
          <span style={{ flex: 1 }}></span>
          <span style={{ color: 'var(--fg-muted)' }}>{Math.floor(pct)}%</span>
        </div>
      </div>
    </div>
  );
}
function PoolShort({ split, p }) {
  const row = (k, val, c) => <div style={{ display: 'flex', gap: '2ch' }}><span style={{ flex: '0 0 30ch', textAlign: 'right', ...muted }}>{k}</span><span style={{ flex: '0 0 6ch', textAlign: 'right', fontWeight: 700, color: c || 'var(--fg-strong)' }}>{val}</span></div>;
  const test = split === 'test';
  return (
    <React.Fragment>
      <Notice tone="error" banner>{test ? 'Only ' + p.left + ' unlabelled candidates are left for the test set; it needs ' + p.need + '.' : 'Only ' + p.found + ' candidates were found; the dev set needs ' + p.need + '.'}</Notice>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: 'var(--row)', padding: '0 4ch' }}>
        <div style={{ ...strong, color: 'var(--error)' }}>Your corpus may be too small for this analysis</div>
        <div style={{ ...muted, whiteSpace: 'pre-wrap', maxWidth: '64ch' }}>The gold sets are drawn from the candidates the search found. Without enough of them, the classifier cannot be tuned or tested reliably.</div>
        <div>
          {row('candidates found', p.found)}
          {test ? row('already in the dev set', p.used) : null}
          {test ? row('left to draw', p.left, 'var(--error)') : null}
          {row('needed for the ' + split + ' set', p.need)}
        </div>
        <div style={{ ...muted, whiteSpace: 'pre-wrap', maxWidth: '64ch' }}>Add seeds to find more candidates, or use a larger corpus.</div>
        <div style={{ display: 'flex', gap: '2ch' }}><Button variant="primary"> Add seeds </Button><Button> Project settings F3 </Button></div>
      </div>
      <Footer keys={K()} />
    </React.Fragment>
  );
}
function GoldView({ v, app }) {
  if (v.notReady) return <NotReady text="Finish stage 3 (taxonomy and prompt) first." keys={[['←', 'Back'], ['→', 'Skip'], ['enter', 'Confirm labels'], ['d', 'Draw 10 more'], ['F2', 'Finish']]} />;
  if (v.poolShort) return <PoolShort split={v.split || 'dev'} p={v.poolShort} />;
  const split = v.split || 'dev';
  const mode = v.mode || 'single';
  const total = v.total || 50;
  const done = v.done ?? 17;
  const idx = v.idx ?? done;
  const chosen = v.chosen || [];
  const counts = v.counts || [7, 4, 2, 4];
  const right = Math.min(30, Math.floor(app.cols * 0.36));
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, '--panel-gap': '0px', paddingBottom: app.cols >= 100 ? 'calc(var(--row) / 2)' : 0 }}>
          {v.banner ? <div style={{ paddingRight: 'var(--panel-gx, 0px)', paddingBottom: 'var(--row)' }}><Notice tone="error" banner>{v.banner}</Notice></div> : null}
          <GoldProgress split={split} done={done} total={total} idx={idx} celebrate={v.celebrate} />
          <Panel title={'item ' + (v.id || '7f3a91')} focused grow bg="var(--bg)">
            <div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg-strong)' }}>{v.text || HD.texts[idx % HD.texts.length]}</div>
          </Panel>
          <Panel title={'labels · ' + mode} subtitle={mode === 'single' ? 'press a key to label' : 'keys toggle, enter confirms'}>
            {HD.labels.map((l, i) => <LabelOption key={l.name} k={l.name === 'off_topic' ? '0' : String(i + 1)} name={l.name} description={l.description} color={l.color} mode={mode} checked={chosen.includes(l.name)} />)}
          </Panel>
          {v.note ? <div style={{ padding: '0 1ch', whiteSpace: 'nowrap', overflow: 'hidden', color: 'var(--warning)' }}>{v.note}</div> : null}
        </div>
        <div style={{ flex: '0 0 ' + right + 'ch', display: 'flex', flexDirection: 'column', '--panel-gap': '0px', paddingBottom: app.cols >= 100 ? 'calc(var(--row) / 2)' : 0 }}>
          <Panel title="counts" subtitle={done + ' of ' + total} grow pad={0}>
            <DataTable cursor={-1} columns={[{ label: 'Label', width: 'minmax(0,1fr)' }, { label: 'Count', width: '7ch', align: 'right' }]}
              rows={HD.labels.map((l, i) => [<LabelTag name={l.name} color={l.color} />, String(counts[i])])} />
          </Panel>
          <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--row)', padding: 'var(--row) 0 0 0', paddingRight: 'var(--panel-gx, 0px)' }}>
            <Button variant="success" disabled={done < total}> Finish {split} set F2 </Button>
            <Button> Draw 10 more d </Button>
          </div>
        </div>
      </div>
      <Footer keys={K(['←', 'Back'], ['→', 'Skip'], ['enter', 'Confirm labels'], ['d', 'Draw 10 more'], ['F2', 'Finish']).map((k) => (k.key === 'F2' ? { ...k, disabled: done < total } : k))} />
      {v.modal ? <ConfirmModal q="All items labelled. Continue?" /> : null}
    </React.Fragment>
  );
}
const goldStates = (stage, split) => {
  const s = split + '-';
  const pre = split === 'dev' ? 'gold' : 'test';
  const list = [
    { id: pre + '/single', name: 'Single mode', when: 'Unlabelled item; a key labels and advances', v: { split } },
    { id: pre + '/multi', name: 'Multi mode, toggling', when: 'mode: multi; keys toggle, enter confirms', v: { split, mode: 'multi', chosen: ['layoff_story', 'hiring_freeze'] } },
    { id: pre + '/multi-invalid', name: 'Multi mode, nothing chosen', when: 'enter with no labels toggled', v: { split, mode: 'multi', chosen: [], note: 'Not saved: at least one label is required' } },
    { id: pre + '/exhausted', name: 'Pool exhausted on draw', when: 'd drew fewer than 10 and no candidates are left. Not blocking, since the required rows exist, but shown as an error banner', v: { split, total: 56, banner: 'No more candidates to draw: only 6 were left, so the set has 56 items. If you need more, your corpus may be too small for this analysis.' } },
    { id: pre + '/pool-short', name: 'Not enough candidates', when: split === 'dev' ? 'On mount, fewer than 50 candidates exist to fill the dev set: labelling is blocked' : 'On mount, fewer than 50 unlabelled candidates remain for the test set: labelling is blocked', v: { split, poolShort: split === 'dev' ? { found: 38, need: 50 } : { found: 74, used: 50, left: 24, need: 50 } } },
    { id: pre + '/halfway', name: 'Milestone reached', when: 'A quarter, half or three quarters of the rows are labelled: one-time message in the progress block', v: { split, done: 25, idx: 24, celebrate: true, chosen: ['layoff_story'], counts: [11, 6, 3, 5] } },
    { id: pre + '/almost', name: 'Nearly there', when: 'Few rows left', v: { split, done: 47, idx: 46, counts: [18, 10, 5, 14] } },
    { id: pre + '/confirm', name: 'Finish', when: 'F2 with every item labelled', v: { split, done: 50, idx: 49, chosen: ['off_topic'], counts: [19, 11, 6, 14], modal: true } },
  ];
  if (split === 'dev') list.unshift({ id: 'gold/not-ready', name: 'Not ready', when: 'Reached before stage 3', v: { notReady: true } });
  return list.map((x) => ({ stage, View: GoldView, ...x }));
};
STATES.push(...goldStates(4, 'dev'));
