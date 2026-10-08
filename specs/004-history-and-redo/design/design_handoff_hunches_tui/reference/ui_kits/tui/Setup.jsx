function SetupView({ v }) {
  const fields = [
    ['corpus_dir', v.corpus_dir, 'local: corpus directory'],
    ['s3_bucket', v.s3_bucket, 's3: bucket'],
    ['s3_index', v.s3_index, 's3: index'],
    ['embedding_model', v.embedding_model, 'embedding model (e.g. openai:text-embedding-3-small)'],
    ['smart_model', HD.smart, ''],
    ['cheap_model', HD.cheap, ''],
  ];
  const row = (label, el, i) => (
    <div key={i} style={{ display: 'flex', padding: '0 1ch', gap: '1ch' }}>
      <span style={{ flex: '0 0 16ch', ...muted }}>{label}</span>
      <div style={{ flex: 1, minWidth: 0 }}>{el}</div>
    </div>
  );
  return (
    <React.Fragment>
      <Notice>Set up hunches (writes .hunches/config.toml)</Notice>
      <Panel title="config.toml" focused grow>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'calc(var(--row) * 0)', position: 'relative', zIndex: 2 }}>
          {row('backend', <Select compact value={v.backend} open={v.open} focused={v.focus === 'backend'} options={[{ label: 'Local (numpy)', value: 'local' }, { label: 'S3 Vectors', value: 's3' }]} />, 'b')}
        </div>
        <div style={{ height: 'var(--row)' }}></div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--row)' }}>
          {fields.slice(0, 3).map(([k, val, ph], i) => row(k, <Input compact value={val || ''} placeholder={ph} focused={v.focus === k} />, i))}
        </div>
        <div style={{ height: 'var(--row)' }}></div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--row)' }}>
          {fields.slice(3).map(([k, val, ph], i) => row(k, <Input compact value={val || ''} placeholder={ph} focused={v.focus === k} />, i))}
        </div>
      </Panel>
      <div style={{ display: 'flex', gap: '2ch', alignItems: 'center', padding: '0 1ch', flex: '0 0 auto' }}>
        <Button variant="primary" focused={v.focus === 'save'}>Save</Button>
        {v.error ? <span style={{ color: 'var(--error)' }}>{v.error}</span> : null}
      </div>
      <Footer keys={[{ key: 'tab', label: 'Next field' }, { key: 'q', label: 'Quit' }]} />
    </React.Fragment>
  );
}
STATES.push(
  { stage: 0, id: 'setup/blank', name: 'First run', when: 'No .hunches/config.toml', View: SetupView, v: { backend: 'local', focus: 'corpus_dir' }, go: { Enter: 'setup/error' } },
  { stage: 0, id: 'setup/backend', name: 'Backend select open', when: 'Select focused, enter', View: SetupView, v: { backend: 's3', open: true, focus: 'backend' } },
  { stage: 0, id: 'setup/error', name: 'Missing required', when: 'Save with empty required fields', View: SetupView, v: { backend: 's3', s3_bucket: 'news-vectors', focus: 'save', error: 'Required: s3_index, embedding_model' } },
);
