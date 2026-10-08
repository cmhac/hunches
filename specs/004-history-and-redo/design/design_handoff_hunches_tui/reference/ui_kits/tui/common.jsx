const STATES = [];
const GLOBAL_KEYS = [{ key: 'q', label: 'Quit' }, { key: 'n', label: 'Next stage' }, { key: 'p', label: 'Previous stage' }];
const K = (...pairs) => [...pairs.map(([key, label]) => ({ key, label })), ...GLOBAL_KEYS];
const muted = { color: 'var(--fg-muted)' };
const strong = { color: 'var(--fg-strong)', fontWeight: 700 };
const Gap = () => <div style={{ flex: 1, minHeight: 0 }}></div>;

function NotReady({ text, keys = [] }) {
  return (
    <React.Fragment>
      <Notice tone="warn">{text}</Notice>
      <Gap />
      <Footer keys={K(...keys)} />
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
          <div style={{ display: 'flex', gap: '2ch', whiteSpace: 'nowrap', overflow: 'hidden' }}>
            <span><span style={muted}>{metric} </span><span style={strong}>{f(v)}</span></span>
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
function DisView({ items = [], cursor = 0, focused = true, detailExtra }) {
  const it = items[cursor];
  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <Panel title={'disagreements · ' + items.length} focused={focused} grow={3} pad={0}>
        {items.length ? (
          <DataTable cursor={cursor} focused={focused} columns={[{ label: 'Text', width: 'minmax(0,1fr)' }, { label: 'Gold', width: '15ch' }, { label: 'Predicted', width: '15ch' }]}
            rows={items.map((d) => [d.text, <Labels names={d.gold} />, <Labels names={d.pred} />])} />
        ) : <div style={{ ...muted, padding: '0 1ch' }}>None.</div>}
      </Panel>
      <Panel title="text" grow={2}>
        <div style={{ whiteSpace: 'pre-wrap', color: 'var(--fg-strong)' }}>{it ? it.text : ''}</div>
        {it && it.pred === 'failed' && detailExtra !== false ? <div style={{ whiteSpace: 'pre-wrap', color: 'var(--error)', marginTop: 'var(--row)' }}>{'Model failed: ' + it.error}</div> : null}
      </Panel>
    </div>
  );
}
