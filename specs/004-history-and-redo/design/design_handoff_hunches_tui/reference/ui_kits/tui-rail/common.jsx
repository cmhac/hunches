const STATES = [];
const GLOBAL_KEYS = [{ key: 'q', label: 'Quit' }, { key: 'n', label: 'Next stage' }, { key: 'p', label: 'Previous stage' }, { key: 'F3', label: 'Project settings' }, { key: 'F4', label: 'Projects' }, { key: 'F5', label: 'System settings' }];
// pairs: [key, label, disabled?]. F8 History is global but unavailable while an editor is open; F9 Redo plan only when a stage is stale or incomplete.
const K = (...pairs) => [...pairs.map(([key, label, disabled]) => ({ key, label, disabled })), ...GLOBAL_KEYS, { key: 'F8', label: 'History', disabled: !!window.__noHistory }, ...(window.__marks ? [{ key: 'F9', label: 'Redo plan' }] : [])];
const muted = { color: 'var(--fg-muted)' };
const strong = { color: 'var(--fg-strong)', fontWeight: 700 };
const Gap = () => <div style={{ flex: 1, minHeight: 0 }}></div>;

// Undo F6 / Redo F7 for one editor; disabled when can_undo / can_redo is false, or while that editor has a draft open.
function UndoRedo({ canUndo, canRedo, disabled, compact }) {
  return (
    <React.Fragment>
      <Button compact={compact} disabled={disabled || !canUndo}>{compact ? 'Undo F6' : ' Undo F6 '}</Button>
      <Button compact={compact} disabled={disabled || !canRedo}>{compact ? 'Redo F7' : ' Redo F7 '}</Button>
    </React.Fragment>
  );
}
// One line after an undo or redo, naming what changed.
const HistNote = ({ children }) => (children ? <Notice tone="note">{children}</Notice> : null);

// Shown once when history.sync() finds an outside edit.
function ExternalNotice({ file }) {
  return (
    <div style={{ flex: '0 0 auto', background: 'var(--warning-muted)', boxShadow: 'inset 0.5ch 0 0 var(--warning)', padding: '0 2ch', marginBottom: 'calc(var(--row) / 2)', minWidth: 0 }}>
      <div style={{ color: 'var(--warning)', fontWeight: 700, whiteSpace: 'normal' }}>{file} changed outside hunches.</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0 1ch' }}><Button compact>Undo F6</Button><Button compact>History F8</Button><Button compact>Dismiss Esc</Button></div>
    </div>
  );
}
// Source badges for History rows. Words, never colour alone.
const H_TONE = { YOU: 'neutral', ASSISTANT: 'accent', EXTERNAL: 'stale', UNDO: 'info', REDO: 'info', RESTORE: 'info', BASELINE: 'muted', APPROVAL: 'pass', VERSION: 'primary' };
const STALE_ALL = { 5: ['stale', 'prompt changed'], 6: ['stale', 'prompt changed'], 7: ['stale', 'prompt changed'], 8: ['stale', 'prompt changed'] };

function NotReady({ text, keys = [] }) {
  return (
    <React.Fragment>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--warning)', whiteSpace: 'pre-wrap', padding: '0 2ch' }}>{text}</div>
      <Footer keys={K(...keys)} />
    </React.Fragment>
  );
}

function ActionRow({ children, justify = 'flex-start', flush }) {
  return <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0 1ch', alignItems: 'center', justifyContent: justify, padding: '0 1ch', flex: '0 0 auto', margin: flush ? 0 : 'var(--row) 0', minWidth: 0 }}>{children}</div>;
}

function RunIndicator({ label, done, total, sub, eta, extra, children }) {
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 'var(--row)' }}>
      <div style={strong}>{label}</div>
      <ProgressBar value={done} total={total} width={36} />
      <div style={muted}>{done} of {total}{eta ? ' · about ' + eta + ' left' : ''}{sub ? ' · ' + sub : ''}</div>
      {extra ? <div style={{ color: extra.error ? 'var(--error)' : 'var(--fg)' }}>{extra.text}</div> : null}
      {children}
    </div>
  );
}

function RunningView({ label, done, total, sub, eta, keys = [], bare, stopped }) {
  return (
    <React.Fragment>
      <RunIndicator label={stopped ? label + ' · stopped' : label} done={done} total={total} sub={sub} eta={stopped ? null : eta}>
        {stopped ? <Button variant="primary"> Resume s </Button> : <Button variant="error"> Stop x </Button>}
      </RunIndicator>
      {bare ? null : <Footer keys={K(stopped ? ['s', 'Resume'] : ['x', 'Stop'], ...keys)} />}
    </React.Fragment>
  );
}

function ConfirmModal({ q }) {
  return (
    <Modal title="Confirm" width={58} actions={<React.Fragment><Button>Cancel</Button><Button variant="success" focused>Approve</Button></React.Fragment>}>
      {q}
    </Modal>
  );
}

function Labels({ names }) {
  if (names === 'failed') return <span style={{ color: 'var(--error)', fontWeight: 700 }}>failed</span>;
  return (
    <span style={{ display: 'inline-flex', gap: '1ch' }}>
      {names.map((n) => <LabelTag key={n} name={n} color={labelColor(n)} />)}
    </span>
  );
}

const PER = {
  dev: [['layoff_story', 0.88, 0.92, 0.9, 19], ['layoff_fear', 0.8, 0.73, 0.76, 11], ['hiring_freeze', 1.0, 0.67, 0.8, 6], ['off_topic', 0.83, 0.86, 0.84, 14]],
  dev2: [['layoff_story', 0.95, 0.95, 0.95, 19], ['layoff_fear', 0.83, 0.91, 0.87, 11], ['hiring_freeze', 1.0, 0.83, 0.91, 6], ['off_topic', 0.87, 0.93, 0.9, 14]],
  test: [['layoff_story', 0.93, 0.93, 0.93, 15], ['layoff_fear', 0.82, 0.9, 0.86, 10], ['hiring_freeze', 1.0, 0.75, 0.86, 8], ['off_topic', 0.84, 0.89, 0.86, 17]],
};
const M_DEV = { exact_match: 0.86, macro_f1: 0.825, micro_f1: 0.86, n: 50, per: PER.dev };
const M_DEV2 = { exact_match: 0.92, macro_f1: 0.908, micro_f1: 0.92, n: 50, per: PER.dev2 };
const M_TEST = { exact_match: 0.9, macro_f1: 0.878, micro_f1: 0.9, n: 50, per: PER.test };
const targetValue = (m, metric) => (metric === 'accuracy' ? m.exact_match : m[metric]);

// Tune (stage 5) and Final (stage 6): metric line, per-label table, optional trend.
function MetricsPanel({ title, m, metric = 'accuracy', target = 0.9, subtitle, top, trend }) {
  const v = m ? targetValue(m, metric) : null;
  const f = (x) => x.toFixed(3);
  const others = m ? [['exact-match', m.exact_match], ['macro-F1', m.macro_f1], ['micro-F1', m.micro_f1]].filter(([k]) => !(k === 'exact-match' && (metric === 'accuracy' || metric === 'exact_match')) && !(k === 'macro-F1' && metric === 'macro_f1') && !(k === 'micro-F1' && metric === 'micro_f1')) : [];
  return (
    <Panel title={title} subtitle={subtitle || 'target ' + metric + ' ≥ ' + target.toFixed(2)}>
      {top}
      {m ? (
        <React.Fragment>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0 2ch', overflow: 'hidden' }}>
            <span style={{ whiteSpace: 'nowrap' }}><span style={muted}>{metric} </span><span style={strong}>{f(v)}</span></span>
            <Badge tone={v >= target ? 'pass' : 'fail'}>{v >= target ? 'PASS' : 'FAIL'}</Badge>
            <span style={muted}>n={m.n}</span>
            {others.map(([k, x]) => <span key={k}><span style={muted}>{k} </span>{f(x)}</span>)}
          </div>
          <DataTable columns={[{ label: 'Label', width: 'minmax(0,1fr)' }, { label: 'P', width: '6ch', align: 'right' }, { label: 'R', width: '6ch', align: 'right' }, { label: 'F1', width: '6ch', align: 'right' }, { label: 'gold', width: '6ch', align: 'right' }]}
            rows={m.per.map(([n, p, r, f1, g]) => [<LabelTag name={n} color={labelColor(n)} />, p.toFixed(2), r.toFixed(2), f1.toFixed(2), String(g)])} />
          {trend ? <div style={{ whiteSpace: 'nowrap', overflow: 'hidden' }}><span style={muted}>trend </span>{trend.map(f).join(' → ')}</div> : null}
        </React.Fragment>
      ) : null}
    </Panel>
  );
}

// Disagreement table + full-text detail (Tune, Final)
function DisView({ items = [], cursor = 0, focused = true, detailExtra, stacked = false }) {
  const it = items[cursor];
  return (
    <div style={{ display: 'flex', flexDirection: stacked ? 'column' : 'row', flex: 1, minHeight: 0 }}>
      <Panel title={'disagreements · ' + items.length} focused={focused} grow={stacked ? 5 : 3} pad={0} style={stacked ? undefined : { '--panel-gx': '1ch', '--panel-gap': '0px' }}>
        {items.length ? (
          <DataTable cursor={cursor} focused={focused} columns={[{ label: 'Text', width: 'minmax(0,1fr)' }, { label: 'Gold', width: '15ch' }, { label: 'Predicted', width: '15ch' }]}
            rows={items.map((d) => [d.text, <Labels names={d.gold} />, <Labels names={d.pred} />])} />
        ) : <div style={{ ...muted, padding: '0 1ch' }}>None.</div>}
      </Panel>
      <Panel title="text · classifier reasoning" grow={stacked ? 4 : 2} style={{ '--panel-gap': '0px' }}>
        <div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg-strong)' }}>{it ? it.text : ''}</div>
        {it && it.reason ? <React.Fragment><div style={{ color: 'var(--accent)', fontWeight: 700, marginTop: 'var(--row)' }}>classifier reasoning</div><div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg)' }}>{it.reason}</div></React.Fragment> : null}
        {it && it.pred === 'failed' && detailExtra !== false ? <div style={{ whiteSpace: 'pre-wrap', color: 'var(--error)', marginTop: 'var(--row)' }}>{'Model failed: ' + it.error}</div> : null}
      </Panel>
    </div>
  );
}
