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
          {v.orphans ? (
            <div style={{ paddingRight: 'var(--panel-gx, 0px)', paddingBottom: 'var(--row)' }}>
              <Notice tone="warn" banner>{'ORPHANED: ' + v.orphans.n + ' of ' + total + ' ' + split + ' rows are no longer in the candidate pool (' + v.orphans.labelled + ' labelled).'}</Notice>
              <div style={{ display: 'flex', gap: '1ch', padding: '0 1ch' }}><Button> Remove stale rows x </Button></div>
            </div>
          ) : null}
          {v.info ? <div style={{ paddingRight: 'var(--panel-gx, 0px)', paddingBottom: 'var(--row)' }}><Notice tone="warn" banner>{v.info}</Notice></div> : null}
          <GoldProgress split={split} done={done} total={total} idx={idx} celebrate={v.celebrate} />
          <Panel title={'item ' + (v.id || '7f3a91')} subtitle={v.itemOrphan ? <Badge tone="stale">ORPHANED</Badge> : null} focused grow bg="var(--bg)">
            <div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg-strong)' }}>{v.text || HD.texts[idx % HD.texts.length]}</div>
          </Panel>
          <Panel title={'labels · ' + mode} subtitle={mode === 'single' ? 'press a key to label' : 'keys toggle, enter confirms'}>
            {HD.labels.map((l, i) => <LabelOption key={l.name} k={l.name === 'off_topic' ? '0' : String(i + 1)} name={l.name} description={l.description} color={l.color} mode={mode} checked={chosen.includes(l.name)} />)}
          </Panel>
          {v.note ? <div style={{ padding: '0 1ch', whiteSpace: 'nowrap', overflow: 'hidden', color: 'var(--warning)' }}>{v.note}</div> : null}
        </div>
        <div style={{ flex: '0 0 ' + right + 'ch', display: 'flex', flexDirection: 'column', '--panel-gap': '0px', paddingBottom: app.cols >= 100 ? 'calc(var(--row) / 2)' : 0 }}>
          <Panel title="counts" subtitle={done + ' of ' + total + (v.orphans ? ' · ' + v.orphans.n + ' orphaned' : '')} grow pad={0}>
            <DataTable cursor={-1} columns={[{ label: 'Label', width: 'minmax(0,1fr)' }, { label: 'Count', width: '7ch', align: 'right' }]}
              rows={HD.labels.map((l, i) => [<LabelTag name={l.name} color={l.color} />, String(counts[i])])} />
          </Panel>
          <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--row)', padding: 'var(--row) 0 0 0', paddingRight: 'var(--panel-gx, 0px)' }}>
            <Button variant="success" disabled={done < total}> Finish {split} set F2 </Button>
            <Button variant={v.replace ? 'primary' : 'default'}> {v.replace ? 'Draw ' + v.replace + ' replacements d' : 'Draw 10 more d'} </Button>
            <Button> Rows r </Button>
          </div>
        </div>
      </div>
      <Footer keys={K(['←', 'Back'], ['→', 'Skip'], ['enter', 'Confirm labels'], ['d', v.replace ? 'Draw replacements' : 'Draw 10 more'], ['r', 'Rows'], ...(v.orphans ? [['x', 'Remove stale rows']] : []), ['F2', 'Finish']).map((k) => (k.key === 'F2' ? { ...k, disabled: done < total } : k))} />
      {v.modal === true ? <ConfirmModal q="All items labelled. Continue?" /> : null}
      {v.modal === 'rows' ? <GoldRowsModal split={split} app={app} o={v.orphans} /> : null}
      {v.modal === 'remove' ? <RemoveGoldModal split={split} o={v.orphans} /> : null}
    </React.Fragment>
  );
}
const GR_ORPH = [1, 4, 6, 11, 12, 13];
function GoldRowsModal({ split, app, o }) {
  const orph = GR_ORPH.slice(0, o ? o.n : 0);
  const rows = HD.texts.concat(HD.texts.slice(0, 4)).map((t, i) => ({ n: i + 1, text: t, lab: i < 12 ? [['layoff_story'], ['layoff_fear'], ['hiring_freeze'], ['off_topic']][i % 4] : null, orphan: orph.includes(i) }));
  const lab = rows.filter((r) => r.lab).length;
  return (
    <Modal title={split + ' set rows'} dense width={app.cols - 4} height={app.rows - 2}
      actions={<React.Fragment><Button variant="error">Remove row Del</Button><Button disabled={!orph.length}>Remove stale rows x</Button><Button focused>Close Esc</Button></React.Fragment>}>
      <div style={{ color: 'var(--fg-muted)', padding: '0 1ch' }}>{rows.length} rows · {lab} labelled · {orph.length} orphaned. Orphaned rows are not in the candidate pool any more.</div>
      <Panel title="rows" grow pad={0} focused bg="var(--bg)">
        <DataTable cursor={4} columns={[{ label: '#', width: '4ch', align: 'right' }, { label: 'Pool', width: '11ch' }, { label: 'Labels', width: '16ch' }, { label: 'Text', width: 'minmax(0,1fr)' }]}
          rows={rows.map((r) => [String(r.n), r.orphan ? <Badge tone="stale">ORPHANED</Badge> : 'in pool', r.lab ? <Labels names={r.lab} /> : <span style={{ color: 'var(--fg-faint)' }}>unlabelled</span>, r.text])} />
      </Panel>
    </Modal>
  );
}
// Confirmation for removing gold rows. Used by the Gold screen (x, Del) and by the assistant's remove_gold tool (by="assistant").
function RemoveGoldModal({ split, o, by }) {
  const test = split === 'test';
  const n = o ? o.n : 1, lab = o ? o.labelled : 1;
  return (
    <Modal title={by === 'assistant' ? 'The assistant wants to remove ' + n + ' ' + split + ' rows' : 'Remove ' + n + ' stale ' + split + ' rows?'} dense width={70}
      actions={<React.Fragment><Button focused>{by === 'assistant' ? 'Reject Esc' : 'Cancel Esc'}</Button><Button variant="error">{'Remove ' + n + ' rows'}</Button></React.Fragment>}>
      <div style={{ whiteSpace: 'pre-wrap' }}>{n + ' rows are no longer in the candidate pool. ' + lab + ' of them are labelled; those ' + lab + ' labels are discarded. The rows are kept in gold_removed.jsonl and are never drawn again.'}</div>
      {test ? <div style={{ whiteSpace: 'pre-wrap', color: 'var(--warning)', marginTop: 'var(--row)' }}>{'Test rows are held out so that the test result is an honest estimate. Replacing labelled test rows changes the items the result is measured on, and the test evaluation has to be run again. Do not remove rows because the classifier got them wrong.'}</div> : null}
    </Modal>
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
    { id: pre + '/orphans', name: 'Rows no longer in the pool', when: 'Seeds changed and search was rerun: some rows are missing from candidates.jsonl (orphaned_gold). They stay labelled until removed', marks: {}, v: { split, done: split === 'dev' ? 42 : 31, idx: 41, orphans: split === 'dev' ? { n: 6, labelled: 4 } : { n: 2, labelled: 1 }, itemOrphan: true, counts: [14, 8, 5, 15] } },
    { id: pre + '/rows', name: 'Rows list', when: 'r: every row with its pool status; Del removes the selected row after confirmation', v: { split, done: split === 'dev' ? 42 : 31, idx: 41, orphans: split === 'dev' ? { n: 6, labelled: 4 } : { n: 2, labelled: 1 }, modal: 'rows' } },
    { id: pre + '/remove-confirm', name: 'Confirm removing rows', when: split === 'dev' ? 'x on orphaned rows: says how many labels are discarded' : 'x on orphaned test rows: same, plus the held-out warning', v: { split, done: split === 'dev' ? 42 : 31, idx: 41, orphans: split === 'dev' ? { n: 6, labelled: 4 } : { n: 2, labelled: 1 }, modal: 'remove' } },
    { id: pre + '/orphans-removed', name: 'Rows removed, replacements needed', when: 'After removal the set is below ' + 50 + ' rows: Finish is disabled, Draw replacements is primary; the stage is marked incomplete', marks: { [stage]: ['incomplete', split === 'dev' ? '44 of 50 rows' : '48 of 50 rows'] }, v: split === 'dev' ? { split, total: 44, done: 38, idx: 38, replace: 6, info: 'Removed 6 stale rows (4 labels discarded). The set has 44 of 50 rows. Draw 6 replacements to continue.' } : { split, total: 48, done: 30, idx: 30, replace: 2, info: 'Removed 2 stale rows (1 label discarded). The set has 48 of 50 rows. Draw 2 replacements to continue. The test result is stale until you re-run it.' } },
    { id: pre + '/halfway', name: 'Milestone reached', when: 'A quarter, half or three quarters of the rows are labelled: one-time message in the progress block', v: { split, done: 25, idx: 24, celebrate: true, chosen: ['layoff_story'], counts: [11, 6, 3, 5] } },
    { id: pre + '/almost', name: 'Nearly there', when: 'Few rows left', v: { split, done: 47, idx: 46, counts: [18, 10, 5, 14] } },
    { id: pre + '/confirm', name: 'Finish', when: 'F2 with every item labelled', v: { split, done: 50, idx: 49, chosen: ['off_topic'], counts: [19, 11, 6, 14], modal: true } },
  ];
  if (split === 'dev') list.unshift({ id: 'gold/not-ready', name: 'Not ready', when: 'Reached before stage 3', v: { notReady: true } });
  return list.map((x) => ({ stage, View: GoldView, ...x }));
};
STATES.push(...goldStates(4, 'dev'));
