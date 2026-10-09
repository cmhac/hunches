function ThresholdView({ v }) {
  if (v.notReady) return <NotReady text="Finish stage 3 (taxonomy and prompt) first." keys={[['F2', 'Save cutoff']]} />;
  if (v.running) return <RunningView label="Sampling each similarity band" done={v.running[0]} total={v.running[1]} sub="30 items per band" keys={[['F2', 'Save cutoff']]} />;
  const sampled = v.sampled || HD.bands.map(() => 30);
  const rows = HD.bands.map((b, i) => {
    const n = Math.min(sampled[i], i === 6 ? 30 : 30);
    const off = Math.round((HD.offTopic[i] * n) / 30);
    const label = (v.selected === i ? '● ' : '  ') + (i === HD.bands.length - 1 ? b.toFixed(3) + '+' : b.toFixed(3));
    return [label, fmt(HD.bandCounts[i]), String(n), n ? Math.round((off / n) * 100) + '% (n=' + n + ')' : '-', fmt(HD.bandCounts.slice(i).reduce((a, x) => a + x, 0))];
  });
  const tone = v.note && /failed/.test(v.note) ? 'error' : 'note';
  return (
    <React.Fragment>
      {v.stale ? <Notice tone="stale" banner>STALE: prompt.md changed since the cutoff 0.650 was saved. The rates below are for the current prompt. Choose a band and save the cutoff again. F9 shows the redo plan.</Notice> : null}
      <div style={{ ...muted, padding: '0 1ch', whiteSpace: 'pre-wrap' }}>{'Off-topic = predicted exactly {off_topic}. Small samples are noisy; mind n. Enter on a row chooses its lower bound as the cutoff.'}</div>
      <Panel title={'off-topic rate by band · ' + HD.cheap} subtitle={v.subtitle} focused>
        <DataTable cursor={v.cursor ?? 2} focused columns={[{ label: 'Band', width: '10ch' }, { label: 'Candidates', width: '12ch', align: 'right' }, { label: 'Sampled', width: '9ch', align: 'right' }, { label: 'Off-topic rate', width: 'minmax(0,1fr)', align: 'right' }, { label: 'Cumulative ≥ lower', width: '20ch', align: 'right' }]} rows={rows} />
      </Panel>
      <div style={{ display: 'flex', gap: '2ch', alignItems: 'center', justifyContent: 'center', flex: '0 0 auto' }}>
        {v.selected != null ? <span style={strong}>Cutoff {HD.bands[v.selected].toFixed(3)}</span> : <span style={muted}>No cutoff chosen</span>}
        <Button variant="primary" disabled={v.selected == null}> Save cutoff F2 </Button>
      </div>
      {v.note ? <Notice tone={tone}>{v.note}</Notice> : null}
      <Gap />
      <Footer keys={K(['enter', 'Choose band'], ['F2', 'Save cutoff'])} />
    </React.Fragment>
  );
}
STATES.push(
  { stage: 7, id: 'threshold/not-ready', name: 'Not ready', when: 'Reached before stage 3', View: ThresholdView, v: { notReady: true } },
  { stage: 7, id: 'threshold/sampling', name: 'Sampling', when: 'On mount: classifying 30 per band; rows fill in', View: ThresholdView, v: { running: [112, 210] } },
  { stage: 7, id: 'threshold/sampled', name: 'Sampled', when: 'All bands classified', View: ThresholdView, v: { note: 'Sampled 210 items in 48.3s, cost $0.0651.' }, go: { Enter: 'threshold/picked' } },
  { stage: 7, id: 'threshold/picked', name: 'Band picked', when: 'Enter or a click on a row chooses its lower bound; Save cutoff enabled', View: ThresholdView, v: { selected: 2, cursor: 2 } },
  { stage: 7, id: 'threshold/stale', name: 'Stale cutoff', when: 'A cutoff was saved, but its approval digest no longer matches (prompt.md or the candidates changed). Banner until Save cutoff is pressed again', marks: STALE_ALL, View: ThresholdView, v: { stale: true, selected: 2, cursor: 2 } },
  { stage: 7, id: 'threshold/failed', name: 'Sampling failed', when: 'Error mid-sample; finished rows kept', View: ThresholdView, v: { sampled: [30, 30, 14, 0, 0, 0, 0], note: 'Sampling failed: status_code: 429, rate_limit_error' } },
);
