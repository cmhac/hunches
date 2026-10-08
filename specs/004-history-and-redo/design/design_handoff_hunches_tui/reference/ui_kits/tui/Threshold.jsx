function ThresholdView({ v }) {
  if (v.notReady) return <NotReady text="Finish stage 3 (taxonomy and prompt) first." keys={[['F2', 'Save cutoff']]} />;
  const sampled = v.sampled || HD.bands.map(() => 30);
  const rows = HD.bands.map((b, i) => {
    const n = Math.min(sampled[i], i === 6 ? 30 : 30);
    const off = Math.round((HD.offTopic[i] * n) / 30);
    const label = i === HD.bands.length - 1 ? b.toFixed(3) + '+' : b.toFixed(3);
    return [label, fmt(HD.bandCounts[i]), String(n), n ? Math.round((off / n) * 100) + '% (n=' + n + ')' : '-', fmt(HD.bandCounts.slice(i).reduce((a, x) => a + x, 0))];
  });
  const tone = v.note && /failed/.test(v.note) ? 'error' : v.note && /^Sampled/.test(v.note) ? 'note' : 'warn';
  return (
    <React.Fragment>
      <div style={{ ...muted, padding: '0 1ch', whiteSpace: 'pre-wrap' }}>{'Off-topic = predicted exactly {off_topic}. Small samples are noisy; mind n. Enter on a row picks its lower bound.'}</div>
      <Panel title={'off-topic rate by band · ' + HD.cheap} subtitle={v.subtitle} focused={v.focus !== 'input'}>
        <DataTable cursor={v.cursor ?? 2} focused={v.focus !== 'input'} columns={[{ label: 'Band', width: '8ch' }, { label: 'Candidates', width: '12ch', align: 'right' }, { label: 'Sampled', width: '9ch', align: 'right' }, { label: 'Off-topic rate', width: 'minmax(0,1fr)', align: 'right' }, { label: 'Cumulative ≥ lower', width: '20ch', align: 'right' }]} rows={rows} />
      </Panel>
      <Input value={v.cutoff || ''} placeholder="cutoff, e.g. 0.65 (F2 saves)" focused={v.focus === 'input'} />
      <Notice tone={tone}>{v.note || ''}</Notice>
      <Gap />
      <Footer keys={K(['F2', 'Save cutoff'])} />
    </React.Fragment>
  );
}
STATES.push(
  { stage: 7, id: 'threshold/not-ready', name: 'Not ready', when: 'Reached before stage 3', View: ThresholdView, v: { notReady: true } },
  { stage: 7, id: 'threshold/sampling', name: 'Sampling', when: 'On mount: classifying 30 per band; rows fill in', View: ThresholdView, v: { sampled: [30, 30, 30, 22, 0, 0, 0], subtitle: 'sampling 112/210' } },
  { stage: 7, id: 'threshold/sampled', name: 'Sampled', when: 'All bands classified', View: ThresholdView, v: { note: 'Sampled 210 items in 48.3s, cost $0.0651.' }, go: { Enter: 'threshold/picked' } },
  { stage: 7, id: 'threshold/picked', name: 'Band picked', when: 'Enter on a row fills the cutoff', View: ThresholdView, v: { cutoff: '0.65', focus: 'input' } },
  { stage: 7, id: 'threshold/invalid', name: 'Invalid cutoff', when: 'F2 with a non-number', View: ThresholdView, v: { cutoff: 'sixty', focus: 'input', note: 'Enter a number or pick a band with Enter.' } },
  { stage: 7, id: 'threshold/failed', name: 'Sampling failed', when: 'Error mid-sample; finished rows kept', View: ThresholdView, v: { sampled: [30, 30, 14, 0, 0, 0, 0], note: 'Sampling failed: status_code: 429, rate_limit_error' } },
);
