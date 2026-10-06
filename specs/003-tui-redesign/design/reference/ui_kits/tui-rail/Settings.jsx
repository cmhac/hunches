
// System settings, Projects, New project, Project settings and their modals (app.py, screens/system.py, projects.py, new_project.py, project_settings.py, model_picker.py, paths.py).
const PRICE = { s: '$3.00 in / $15.00 out per 1M tokens', h: '$1.00 in / $5.00 out per 1M tokens', o: '$5.00 in / $25.00 out per 1M tokens', e: '$0.02 in per 1M tokens' };
const NOPRICE = 'no price: cost will show ?';
const SNAP = '2026-09-30';
const Rule = () => <div style={{ color: 'var(--ink-5)', overflow: 'hidden', whiteSpace: 'nowrap', flex: '0 0 auto' }}>{'─'.repeat(160)}</div>;
const Row = ({ label, children, btns, w = 11 }) => (
  <div style={{ display: 'flex', gap: '1ch', alignItems: 'flex-start' }}>
    {label ? <span style={{ flex: '0 0 ' + w + 'ch', ...muted }}>{label}</span> : null}
    <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', display: 'flex', flexWrap: 'wrap', gap: '0 1ch', whiteSpace: 'pre-wrap' }}>{children}</div>
    {btns}
  </div>
);
const CB = ({ on, children }) => <span><span style={{ color: on ? 'var(--primary)' : 'var(--fg-muted)' }}>{on ? '▐X▌' : '▐ ▌'}</span> {children}</span>;
const Scroll = ({ children, gap = 0 }) => <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: gap }}>{children}</div>;
const Actions = ({ children }) => <div style={{ display: 'flex', gap: '1ch', padding: '0 1ch', flex: '0 0 auto' }}>{children}</div>;
const Msg = ({ tone, children }) => (children ? <Notice tone={tone}>{children}</Notice> : null);
const Models = ({ a, c, thinking = 'medium', nopriceFor }) => {
  const mark = (m, rec) => (m === rec ? <span style={{ color: 'var(--success)' }}>RECOMMENDED</span> : <Badge tone="info">DIFFERS FROM RECOMMENDED</Badge>);
  const price = (m) => (nopriceFor === m ? <span style={{ color: 'var(--warning)' }}>{NOPRICE}</span> : <span style={muted}>{PRICE[m.includes('haiku-4') ? 'h' : m.includes('opus') ? 'o' : 's']}</span>);
  return (
    <React.Fragment>
      <Row label="assistant" btns={<Button compact>Change</Button>}><span>{a}</span>{price(a)}{mark(a, 'anthropic:claude-sonnet-5-5')}</Row>
      <div style={{ height: 'var(--row)' }}></div>
      <Row label="thinking"><Select compact value={thinking} options={['provider default', 'minimal', 'low', 'medium', 'high']} /></Row>
      <div style={{ height: 'var(--row)' }}></div>
      <Rule />
      <div style={{ height: 'var(--row)' }}></div>
      <Row label="classifier" btns={<Button compact>Change</Button>}><span>{c}</span>{price(c)}{mark(c, 'anthropic:claude-haiku-4-5')}</Row>
    </React.Fragment>
  );
};

function SystemView({ v }) {
  const st = (s) => <span style={{ flex: '0 0 9ch', color: s === 'MISSING' ? 'var(--warning)' : 'var(--success)' }}>{s}</span>;
  const key = (name, s) => (
    <Row label={name} btns={<React.Fragment><Button compact>Save</Button><Button compact>Remove</Button></React.Fragment>}>
      {st(s)}<Input compact value="" placeholder="paste key" focused={v.focus === name} />
    </Row>
  );
  const model = v.model || 'anthropic:claude-sonnet-5-5';
  const noKeys = (v.anthropic || 'MISSING') === 'MISSING' && (v.openai || 'MISSING') === 'MISSING';
  return (
    <React.Fragment>
      <Scroll>
        <div style={{ padding: '0 1ch', ...strong }}>{v.first ? 'Welcome — set up hunches' : 'Settings'}</div>
        <Panel title="API keys" pad={1}>
          {v.nokeyring ? <Notice tone="warn">WARNING: No system keyring available: set ANTHROPIC_API_KEY / OPENAI_API_KEY in the environment or a git-ignored .env</Notice> : <React.Fragment>{key('Anthropic', v.anthropic || 'MISSING')}{key('OpenAI', v.openai || 'MISSING')}</React.Fragment>}
        </Panel>
        <div style={{ padding: '0 1ch' }}><Row label="Provider"><Select compact value={v.provider || 'Anthropic'} options={['Anthropic', 'OpenAI']} focused={v.focus === 'provider'} /></Row></div>
        <Panel title="Models">
          <Models a={model} c={v.classifier || 'anthropic:claude-haiku-4-5'} thinking={v.thinking} nopriceFor={v.nopriceFor} />
          <div style={{ height: 'var(--row)' }}></div>
          <div><Button compact>Reset to recommended</Button></div>
        </Panel>
        <Panel title="Saved S3 stores">
          {v.stores ? <Row label=""><Input compact value="news-vectors/posts" /><span style={muted}>news-vectors/posts us-east-1</span><Button compact>Delete</Button></Row> : <Notice>No saved stores. They are created from New project.</Notice>}
        </Panel>
        <Notice>Changes here apply to new projects. Existing projects keep their models.</Notice>
        <Notice>Prices from genai-prices as of {SNAP}; the sidebar shows actual spend.</Notice>
      </Scroll>
      <Actions>
        <Button compact variant="success" disabled={noKeys} focused={v.focus === 'save'}>Save</Button>
        {v.first ? null : <Button compact>Cancel</Button>}
        {v.error ? <span style={{ color: 'var(--error)' }}>{v.error}</span> : noKeys ? <span style={muted}>Add at least one API key to save</span> : null}
      </Actions>
      <Footer keys={[{ key: 'tab', label: 'Next field' }, { key: 'q', label: 'Quit' }]} />
    </React.Fragment>
  );
}

function ModelPickerView({ v }) {
  const rows = v.embedding
    ? [['openai:text-embedding-3-small', PRICE.e, 'rec'], ['openai:text-embedding-3-large', '$0.13 in per 1M tokens']]
    : [['anthropic:claude-sonnet-5-5', PRICE.s, 'rec'], ['anthropic:claude-haiku-4-5', PRICE.h, 'rec'], ['anthropic:claude-opus-4-5', PRICE.o], ['anthropic:claude-3-5-haiku-latest', NOPRICE, 'dep']];
  const list = v.nokey ? [] : rows;
  const cur = v.cursor ?? 0;
  const opt = (t, sub, i, on) => (
    <div key={i} style={{ background: on ? 'var(--cursor-bg)' : 'transparent', color: on ? 'var(--cursor-fg)' : 'var(--fg)' }}>
      <div style={{ padding: '0 1ch', fontWeight: on ? 700 : 400 }}>{t}</div>
      {sub ? <div style={{ padding: '0 1ch', color: on ? 'var(--cursor-fg)' : sub === NOPRICE ? 'var(--warning)' : 'var(--fg-muted)' }}>{'  ' + sub}</div> : null}
    </div>
  );
  return (
    <Modal title="Choose a model" width={78} height={22} dense actions={null}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', whiteSpace: 'pre' }}>
        {list.map((r, i) => opt(r[0] + (r[2] === 'rec' ? ' ★ recommended' : '') + (r[2] === 'dep' ? ' DEPRECATED' : ''), r[1], i, i === cur))}
        {opt('Other… (type any provider:model)', null, 99, cur === list.length)}
      </div>
      {v.other ? <Input compact focused value={v.other === true ? '' : v.other} placeholder="provider:model" /> : null}
      {v.nokey ? <Notice tone="warn">No API key set: add one in System settings (F5)</Notice> : null}
      {v.warn ? <Notice tone="warn">WARNING: not in known list (may still be valid)</Notice> : null}
    </Modal>
  );
}

function RecommendationView() {
  const line = (k, text, price, hi) => (
    <div style={{ display: 'grid', gridTemplateColumns: '6ch 28ch 1fr', gap: '0 1ch' }}>
      <span style={muted}>{k}</span>
      <span style={{ color: hi ? 'var(--success)' : 'var(--fg)', fontWeight: hi ? 700 : 400 }}>{text}</span>
      <span style={muted}>{price}</span>
    </div>
  );
  const head = (t, tag) => <div style={{ display: 'flex', gap: '2ch' }}><span style={strong}>{t}</span>{tag ? <span style={muted}>{tag}</span> : null}</div>;
  return (
    <React.Fragment>
      <SystemView v={{ provider: 'Anthropic' }} />
      <Modal title="Recommended models changed" width={80} dense actions={<React.Fragment><Button>Keep mine</Button><Button variant="success" focused>Use new</Button></React.Fragment>}>
        {head('assistant')}
        {line('now', 'anthropic:claude-sonnet-4-5', PRICE.s)}
        {line('new', 'anthropic:claude-sonnet-5-5', PRICE.s, true)}
        <div style={{ height: 'var(--row)' }}></div>
        {head('thinking')}
        {line('now', 'provider default', '')}
        {line('new', 'medium', '', true)}
        <div style={{ height: 'var(--row)' }}></div>
        <Rule />
        <div style={{ height: 'var(--row)' }}></div>
        {head('classifier', 'unchanged')}
        {line('', 'anthropic:claude-haiku-4-5', PRICE.h)}
        <div style={{ height: 'var(--row)' }}></div>
        <Notice>Existing projects keep their models.</Notice>
      </Modal>
    </React.Fragment>
  );
}

const PROJECTS = [
  ['layoffs-2026', 'local', 'data/corpus', 'OK', '2026-10-04'],
  ['wire-stories', 's3', 'news-vectors/posts', 'OK (s3 not checked)', '2026-10-02'],
  ['old-experiment', 'local', 'corpus', 'MISSING CORPUS', '2026-09-18'],
  ['moved-project', '?', '', 'MISSING DIR', '2026-09-01'],
];
function ProjectsView({ v }) {
  const rows = v.empty ? [] : PROJECTS.slice(0, v.healthy ? 2 : 4);
  const bad = rows.filter((r) => !r[3].startsWith('OK')).length;
  const stCell = (s) => <span style={{ color: s.startsWith('OK') ? 'var(--success)' : 'var(--warning)' }}>{s}</span>;
  return (
    <React.Fragment>
      {bad ? <Notice tone="warn" banner>{bad} projects need attention</Notice> : null}
      {v.empty ? (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 'var(--row)' }}>
          <div style={{ color: 'var(--fg-muted)' }}>No projects yet. Press n to create one.</div>
          <Button variant="primary" focused>  New project  n  </Button>
        </div>
      ) : (
        <DataTable zebra cursor={v.cursor ?? 0} columns={[{ label: 'Name', width: '16ch' }, { label: 'Backend', width: '8ch' }, { label: 'Where', width: 'minmax(0,1fr)' }, { label: 'Status', width: '20ch' }, { label: 'Opened', width: '11ch' }]}
          rows={rows.map((r) => [r[0], r[1], r[2], stCell(r[3]), r[4]])} />
      )}
      {v.empty ? null : <Gap />}
      {v.empty ? null : <ActionRow>
        <Button variant="primary"> New project n </Button>
        <Button> Edit e </Button>
        <Button> Remove x </Button>
        <Button disabled={!['MISSING DIR', 'MISSING CORPUS'].includes(rows[v.cursor ?? 0][3])}> Locate l </Button>
        <Button> Refresh r </Button>
      </ActionRow>}
      {v.modal === 'remove' ? <RemoveView v={v} /> : null}
      <Footer keys={[{ key: 'n', label: 'New' }, { key: 'e', label: 'Edit' }, { key: 'r', label: 'Refresh' }, { key: 'x', label: 'Remove' }, { key: 'l', label: 'Locate' }, { key: 'esc', label: 'Back' }, { key: 'q', label: 'Quit' }, { key: 'F3', label: 'Project settings' }, { key: 'F4', label: 'Projects' }, { key: 'F5', label: 'System settings' }]} />
    </React.Fragment>
  );
}

function RemoveView({ v }) {
  const typed = v.typed;
  return (
    <Modal title="Remove old-experiment" width={78} dense>
      <Notice>Remove from list keeps every file. Delete project files removes only this project's .hunches/ folder: never the corpus, never S3. hunches does not run git, so committed history is unaffected.</Notice>
      <div style={{ display: 'flex', gap: '1ch' }}><Button compact focused={!typed}>Remove from list</Button><Button compact>Cancel</Button></div>
      <Input compact focused={!!typed} value={typed || ''} placeholder="type old-experiment to enable delete" />
      <div><Button compact disabled={!(typed === 'old-experiment')} variant={typed === 'old-experiment' ? 'error' : 'default'}>Delete project files</Button></div>
    </Modal>
  );
}

function PathPickerView() {
  const d = (t, on, ind = 0) => <div style={{ paddingLeft: ind + 'ch', background: on ? 'var(--cursor-bg)' : 'transparent', color: on ? 'var(--cursor-fg)' : 'var(--fg)', fontWeight: on ? 700 : 400 }}>{t}</div>;
  return (
    <Modal title="Choose a directory" width={78} height={22} dense>
      <div style={{ display: 'flex', gap: '1ch' }}>
        <div style={{ flex: 1, minWidth: 0 }}><Input compact value="/home/chris/projects" placeholder="path (→ completes)" /></div>
        <Button compact>Up</Button><Button compact variant="primary" focused>Select</Button><Button compact>Cancel</Button>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', whiteSpace: 'pre' }}>
        {d('▼ projects', false)}{d('▶ hunches', false, 2)}{d('▼ layoffs-2026', false, 2)}{d('▼ data', false, 4)}{d('corpus', true, 6)}{d('▶ wire-stories', false, 2)}{d('▶ scratch', false, 2)}
      </div>
    </Modal>
  );
}

function NewProjectView({ v }) {
  const s3 = v.backend === 's3';
  const ready = s3 ? !!(v.bucket && v.index && v.embed) && !v.blocked : !!v.corpus && !v.problem && !v.blocked;
  const msg = v.error ? { t: v.error, err: true } : v.problem ? { t: 'Corpus: ' + v.problem, err: true } : !ready && !v.blocked ? { t: 'Required: ' + (s3 ? 'bucket, index, embedding model' : 'corpus') } : null;
  return (
    <React.Fragment>
      <Scroll>
        <Panel title="location"><Row label="folder" btns={<Button compact>Browse</Button>}><Input compact value="/home/chris/projects/layoffs-2026" placeholder="path (→ completes)" focused={v.focus === 'location'} /></Row></Panel>
        <Panel title="corpus">
          <Row label="backend"><Select compact value={s3 ? 'S3 Vectors' : 'Local (numpy)'} options={['Local (numpy)', 'S3 Vectors']} focused={v.focus === 'backend'} /></Row>
          {s3 ? (
            <React.Fragment>
              <Row label="store"><Select compact value={v.store || 'New store…'} options={['New store…', 'news-vectors/posts']} /></Row>
              <Row label="bucket"><Input compact value={v.bucket || ''} focused={v.focus === 'bucket'} /></Row>
              <Row label="index"><Input compact value={v.index || ''} /></Row>
              <Row label="region"><Input compact value="" placeholder="optional" /></Row>
              <Row label="embedding" btns={<Button compact>Pick</Button>}>{v.embed ? <span>{v.embed}</span> : <span style={{ color: 'var(--warning)' }}>not chosen</span>}</Row>
              <CB on={!v.store}>Save this store for other projects</CB>
              {v.storeStatus ? <span style={{ color: v.storeStatus.startsWith('ERROR') ? 'var(--error)' : 'var(--fg)' }}>{v.storeStatus}</span> : null}
              <div><Button compact>Check store</Button></div>
            </React.Fragment>
          ) : (
            <React.Fragment>
              <Row label="corpus" btns={<Button compact>Browse</Button>}><Input compact value={v.corpus || ''} placeholder="path (→ completes)" focused={v.focus === 'corpus'} /></Row>
              {v.corpus ? <span style={{ color: v.problem ? 'var(--error)' : 'var(--fg)' }}>{v.problem ? 'ERROR: ' + v.problem : 'embedding model: ' + HD.embed + ' (from meta.json)'}</span> : null}
            </React.Fragment>
          )}
        </Panel>
        <Panel title="models">
          <div>assistant: {HD.smart}  <span style={muted}>{PRICE.s}</span></div>
          <div>thinking: medium</div>
          <Rule />
          <div>classifier: {HD.cheap}  <span style={muted}>{PRICE.h}</span></div>
          <div style={muted}>pinned for this project; change later in Project settings</div>
        </Panel>
      </Scroll>
      {v.blocked ? <Notice tone="warn">BLOCKED: missing API key {v.blocked}</Notice> : null}
      <Actions>
        {v.blocked ? <Button compact>System settings</Button> : null}
        <Button compact variant="primary" disabled={!ready} focused={v.focus === 'create'}>Create</Button>
        {v.exists ? <Button compact>Open it</Button> : null}
        {msg ? <span style={{ color: msg.err ? 'var(--error)' : 'var(--fg-muted)' }}>{msg.t}</span> : null}
      </Actions>
      <Footer keys={[{ key: 'tab', label: 'Next field' }, { key: 'q', label: 'Quit' }]} />
    </React.Fragment>
  );
}

function ProjectSettingsView({ v }) {
  const s3 = v.backend === 's3';
  const mark = (rec) => rec ? <span style={{ color: 'var(--success)' }}>RECOMMENDED</span> : <Badge tone="info">DIFFERS FROM RECOMMENDED</Badge>;
  const a = v.assistant || HD.smart;
  return (
    <React.Fragment>
      <Scroll>
        <Panel title="corpus">
          <Row label="backend"><Select compact value={s3 ? 'S3 Vectors' : 'Local (numpy)'} options={['Local (numpy)', 'S3 Vectors']} focused={v.focus === 'backend'} /></Row>
          {s3 ? (
            <React.Fragment>
              <Row label="store"><Select compact value="New store…" options={['New store…', 'news-vectors/posts']} /></Row>
              <Row label="bucket"><Input compact value="news-vectors" /></Row>
              <Row label="index"><Input compact value="posts" /></Row>
              <Row label="region"><Input compact value="us-east-1" /></Row>
              <div><Button compact>Pick embedding model</Button></div>
              {v.storeStatus ? <span>{v.storeStatus}</span> : null}
              <div><Button compact>Check store</Button></div>
            </React.Fragment>
          ) : <Row label="corpus" btns={<Button compact>Browse</Button>}><Input compact value={v.corpus ?? 'data/corpus'} placeholder="path (→ completes)" focused={v.focus === 'corpus'} /></Row>}
          <div style={{ color: v.problem ? 'var(--error)' : 'var(--fg)' }}>embedding: {v.problem ? 'ERROR: ' + v.problem : <React.Fragment>{HD.embed}  <span style={muted}>{PRICE.e}</span></React.Fragment>}</div>
        </Panel>
        <Panel title="models">
          <Row label="" btns={<Button compact>Change</Button>}><span>assistant: {a}  <span style={muted}>{PRICE.s}</span>  {mark(!v.assistant)}</span></Row>
          <Row label="thinking"><Select compact value="medium" options={['provider default', 'minimal', 'low', 'medium', 'high']} /></Row>
          <Rule />
          <Row label="" btns={<Button compact>Change</Button>}><span>classifier: {v.classifier || HD.cheap}  <span style={muted}>{PRICE.h}</span>  {mark(!v.classifier)}</span></Row>
        </Panel>
        <Notice>Prices from genai-prices as of {SNAP}; the sidebar shows actual spend. Changes here affect only this project.</Notice>
      </Scroll>
      {v.nopriceFor ? <Notice tone="warn">WARNING: no price for {v.nopriceFor}: cost will show ?</Notice> : null}
      <Actions>
        <Button compact variant="success" disabled={!!v.problem} focused={v.focus === 'save'}>Save</Button>
        <Button compact>Cancel</Button>
        {v.error ? <span style={{ color: 'var(--error)' }}>{v.error}</span> : null}
      </Actions>
      <Footer keys={[{ key: 'tab', label: 'Next field' }, { key: 'q', label: 'Quit' }]} />
    </React.Fragment>
  );
}

const OVERLAYS = {
  picker: () => <ModelPickerView v={{}} />,
  embedding: () => <ModelPickerView v={{ embedding: true }} />,
  other: () => <ModelPickerView v={{ other: true, cursor: 4 }} />,
  nokey: () => <ModelPickerView v={{ nokey: true }} />,
  path: () => <PathPickerView />,
  confirm: () => <ConfirmModal q={'Candidates were generated from the old corpus (candidates.jsonl): re-run Search (stage 2). Gold labels refer to ids.\n\nClassifier changed: the classifier cache is keyed on the model, so nothing stale is reused; dev, test and threshold numbers are recomputed with the new cost; the test result becomes STALE; results.jsonl (if present) was produced by the old model and is not rewritten.\n\nNothing is deleted.'} />,
};
function Over({ v }) {
  const Base = v.Base;
  return <React.Fragment><Base v={v.bv} />{OVERLAYS[v.over]()}</React.Fragment>;
}
const SW = { stage: 0, title: 'Setup' };
STATES.push(
  { ...SW, id: 'system/first', name: 'System settings, first run', when: 'system.json missing: SystemSettingsScreen pushed on mount, no Cancel', View: SystemView, v: { first: true, focus: 'Anthropic' } },
  { ...SW, id: 'system/nokey', name: 'System: save disabled', when: 'Every key MISSING: Save is greyed out', View: SystemView, v: { first: true, focus: 'save' } },
  { ...SW, id: 'system/edit', name: 'System settings', when: 'F5, system.json exists', View: SystemView, v: { anthropic: 'KEYRING', openai: 'ENV', stores: true } },
  { ...SW, id: 'system/differs', name: 'System: models differ', when: 'Models or thinking differ from RECOMMENDED[provider]', View: SystemView, v: { anthropic: 'KEYRING', model: 'anthropic:claude-opus-4-5', differs: true } },
  { ...SW, id: 'system/noprice', name: 'System: model without price', when: 'price_label(model) == NO_PRICE', View: SystemView, v: { anthropic: 'KEYRING', model: 'anthropic:claude-3-5-haiku-latest', nopriceFor: 'anthropic:claude-3-5-haiku-latest', differs: true } },
  { ...SW, id: 'system/nokeyring', name: 'System: no keyring', when: 'keys.available() is False (headless)', View: SystemView, v: { anthropic: 'ENV', nokeyring: true } },
  { ...SW, id: 'system/recommend', name: 'Recommended models changed', when: 'recommended_changed(system): RECOMMENDED_REVISION > recommendation_seen', View: RecommendationView, v: { modal: true } },
  { ...SW, id: 'picker/list', name: 'Model picker', when: 'Change on a model row; models for every provider with a key', View: Over, v: { modal: true, Base: SystemView, bv: { anthropic: 'KEYRING' }, over: 'picker' } },
  { ...SW, id: 'picker/embedding', name: 'Model picker, embedding', when: 'ModelPicker(embedding=True) from New project / Project settings', View: Over, v: { modal: true, Base: NewProjectView, bv: { backend: 's3' }, over: 'embedding' } },
  { ...SW, id: 'picker/other', name: 'Model picker, Other…', when: 'Other… chosen: provider:model input shown', View: Over, v: { modal: true, Base: SystemView, bv: { anthropic: 'KEYRING' }, over: 'other' } },
  { ...SW, id: 'picker/nokey', name: 'Model picker, no key', when: 'keys.providers() is empty', View: Over, v: { modal: true, Base: SystemView, bv: { anthropic: 'MISSING' }, over: 'nokey' } },
  { ...SW, id: 'projects/list', name: 'Projects', when: 'F4, or startup with no project in the current directory', View: ProjectsView, title: 'Projects', v: {} },
  { ...SW, id: 'projects/healthy', name: 'Projects, all healthy', when: 'every project_status starts with OK: no banner', View: ProjectsView, title: 'Projects', v: { healthy: true } },
  { ...SW, id: 'projects/empty', name: 'Projects, empty', when: 'system.projects_by_recent() is empty', View: ProjectsView, title: 'Projects', v: { empty: true } },
  { ...SW, id: 'projects/remove', name: 'Remove project', when: 'x on a project: RemoveModal, focus on Remove from list', View: ProjectsView, title: 'Projects', v: { cursor: 2, modal: 'remove' } },
  { ...SW, id: 'projects/delete', name: 'Remove project, delete enabled', when: 'Input equals the project name', View: ProjectsView, title: 'Projects', v: { cursor: 2, modal: 'remove', typed: 'old-experiment' } },
  { ...SW, id: 'projects/locate', name: 'Locate project', when: 'l on MISSING DIR or MISSING CORPUS: PathPicker', View: Over, title: 'Projects', v: { modal: true, Base: ProjectsView, bv: { cursor: 3 }, over: 'path' } },
  { ...SW, id: 'new/local', name: 'New project, local', when: 'n on Projects; backend Local', View: NewProjectView, title: 'New project', v: { focus: 'corpus' } },
  { ...SW, id: 'new/corpus-ok', name: 'New project, corpus valid', when: 'check_corpus finds vectors.npy, items.jsonl, meta.json', View: NewProjectView, title: 'New project', v: { corpus: 'data/corpus', focus: 'create' } },
  { ...SW, id: 'new/corpus-bad', name: 'New project, corpus invalid', when: 'check_corpus returns a problem', View: NewProjectView, title: 'New project', v: { corpus: 'data/corpus', problem: 'missing meta.json', focus: 'create' } },
  { ...SW, id: 'new/s3', name: 'New project, S3', when: 'backend S3 Vectors; embedding not chosen', View: NewProjectView, title: 'New project', v: { backend: 's3', focus: 'bucket' } },
  { ...SW, id: 'new/s3-checked', name: 'New project, S3 checked', when: 'Check store returned get_index details', View: NewProjectView, title: 'New project', v: { backend: 's3', bucket: 'news-vectors', index: 'posts', embed: HD.embed, storeStatus: 'dimension 1536, distance metric cosine' } },
  { ...SW, id: 'new/s3-bad', name: 'New project, S3 error', when: 'get_index raised', View: NewProjectView, title: 'New project', v: { backend: 's3', bucket: 'news-vectors', index: 'posts', storeStatus: 'ERROR: The specified index could not be found' } },
  { ...SW, id: 'new/blocked', name: 'New project, blocked', when: 'An API key needed by a pinned model or the embedding is missing', View: NewProjectView, title: 'New project', v: { corpus: 'data/corpus', blocked: 'OPENAI_API_KEY', focus: 'create' } },
  { ...SW, id: 'new/exists', name: 'New project, already exists', when: '<folder>/.hunches/config.toml exists', View: NewProjectView, title: 'New project', v: { corpus: 'data/corpus', exists: true, error: 'Location: already a project - open it instead' } },
  { ...SW, id: 'pset/local', name: 'Project settings, local', when: 'F3 in a project, or e on Projects', View: ProjectSettingsView, title: 'Settings', v: {} },
  { ...SW, id: 'pset/s3', name: 'Project settings, S3', when: 'config.backend == "s3"', View: ProjectSettingsView, title: 'Settings', v: { backend: 's3' } },
  { ...SW, id: 'pset/differs', name: 'Project settings, models differ', when: 'model not in RECOMMENDED values', View: ProjectSettingsView, title: 'Settings', v: { assistant: 'anthropic:claude-opus-4-5', classifier: 'anthropic:claude-3-5-haiku-latest', nopriceFor: 'anthropic:claude-3-5-haiku-latest' } },
  { ...SW, id: 'pset/problem', name: 'Project settings, corpus error', when: 'check_corpus problem on save', View: ProjectSettingsView, title: 'Settings', v: { corpus: 'data/old', problem: 'missing vectors.npy', error: 'Corpus: missing vectors.npy', focus: 'save' } },
  { ...SW, id: 'pset/confirm', name: 'Project settings, confirm changes', when: 'Save with a changed corpus, assistant or classifier', View: Over, title: 'Settings', v: { modal: true, Base: ProjectSettingsView, bv: { classifier: 'anthropic:claude-3-5-haiku-latest' }, over: 'confirm' } },
);
