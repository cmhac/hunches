const BRIEF_MSGS = [
  { role: 'user', text: 'Find posts where someone says they were laid off.' },
  { role: 'agent', text: 'Should second-hand accounts count, like "my partner was let go"?' },
  { role: 'user', text: 'No. Only the author.' },
];
const BRIEF_TOOL = { role: 'tool', name: 'propose_seeds', summary: 'Added 10 seeds.', body: '# arguments\nseeds:\n  - The author says they were laid off\n  - I lost my job in a round of layoffs\n  - My position was eliminated last week\n  … 7 more\n# result\nAdded 10 seeds.' };
const brBar = (c) => 'inset 0.5ch 0 0 ' + c;
const brCaret = <span style={{ background: 'var(--primary)', color: 'var(--ink-1)' }}> </span>;
function BriefView({ v }) {
  const seeds = v.seeds || [];
  const focus = v.focus || 'seeds';
  const editing = v.editing != null;
  const adding = !!v.adding;
  const busy = editing || adding;
  const text = v.input || '';
  const dirty = busy && text !== (editing ? seeds[v.editing] : '');
  const row = (n, children, o = {}) => (
    <div style={{ display: 'flex', gap: '1ch', padding: '0 1ch', flex: '0 0 auto', background: o.bg || 'transparent', boxShadow: o.bar ? brBar(o.bar) : 'none', opacity: o.dim ? 0.45 : 1, color: o.color || 'var(--fg)' }}>
      <span style={{ flex: '0 0 3ch', textAlign: 'right', color: 'var(--fg-faint)' }}>{n}</span>
      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{children}</span>
    </div>
  );
  const editor = (n) => row(n, text ? <React.Fragment>{text}{brCaret}</React.Fragment> : <React.Fragment>{brCaret}<span style={{ color: 'var(--fg-faint)' }}>Type a seed phrase</span></React.Fragment>, { bg: 'var(--boost)', bar: 'var(--primary)', color: 'var(--fg-strong)' });
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <ChatPanel title="chat · brief" model={HD.smart} focused={focus === 'chat'} messages={v.msgs || []} streaming={v.streaming} input={v.chat || ''} empty="Describe what concepts you want to search for and the assistant will help you generate seed phrases" />
        <Panel title="Seeds" subtitle={seeds.length + (seeds.length === 1 ? ' seed' : ' seeds')} focused={focus !== 'chat'} grow pad={0}>
          {seeds.length || adding ? (
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              {seeds.slice(0, 12).map((s, i) => {
                if (editing && v.editing === i) return <React.Fragment key={i}>{editor(i + 1)}</React.Fragment>;
                const sel = !busy && focus === 'seeds' && i === (v.cursor ?? 0);
                return <React.Fragment key={i}>{row(i + 1, s, { dim: busy, bg: sel ? 'var(--boost)' : null, bar: sel ? 'var(--primary)' : null, color: sel ? 'var(--fg-strong)' : null })}</React.Fragment>;
              })}
              {adding ? editor(seeds.length + 1) : null}
            </div>
          ) : <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--fg-muted)', whiteSpace: 'pre-wrap', padding: 'calc(var(--row) * 2) 2ch 0' }}>No seeds yet. Describe what to find in the chat, or press a to add one.</div>}
          {busy ? (
            <div style={{ flex: '0 0 auto', margin: 'var(--row) 0', background: 'var(--panel)', boxShadow: brBar('var(--primary)'), padding: '0 2ch', minWidth: 0, overflow: 'hidden' }}>
              <div style={{ display: 'flex', gap: '2ch' }}>
                <span style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>{editing ? 'Editing seed ' + (v.editing + 1) : 'New seed'}</span>
                {dirty ? <Badge tone="stale">UNSAVED</Badge> : null}
              </div>
              {editing ? <div style={{ color: 'var(--fg-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>was: {seeds[v.editing]}</div> : null}
              <div style={{ display: 'flex', gap: '1ch', flexWrap: 'wrap', margin: 'var(--row) 0' }}>
                <Button variant="success" disabled={!text || !dirty}> {editing ? 'Save' : 'Add'} Enter </Button>
                <Button> Discard Esc </Button>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: '0 1ch', minWidth: 0, padding: '0 1ch', flex: '0 0 auto', margin: 'var(--row) 0' }}>
              <Button> Add seed a </Button>
              <Button disabled={!seeds.length}> Edit e </Button>
              <Button disabled={!seeds.length}> Delete d </Button>
              <Button variant="success" disabled={!seeds.length}> Approve seeds F2 </Button>
            </div>
          )}
        </Panel>
      </div>
      <Footer keys={busy ? K(['enter', editing ? 'Save' : 'Add seed'], ['esc', 'Discard']) : K(['a', 'Add seed'], ['e', 'Edit seed'], ['d', 'Delete seed'], ['F2', 'Approve seeds'])} />
      {v.modal ? <ConfirmModal q={'Approve ' + seeds.length + ' seeds and start searching?'} /> : null}
    </React.Fragment>
  );
}
const NOREPLY_B = ['', '# Instructions', 'No reply needed. Treat this as the current state in your next turn.'];
const SEED_EDITS = [
  { role: 'context', edit: true, summary: 'Seed 3 edited', body: ['# What changed', '  ~ 3', '    was: My position was eliminated last week', '    now: My position was eliminated last week, along with my whole team', ...NOREPLY_B].join('\n') },
  { role: 'context', edit: true, summary: 'Seed added: The author lost their job when the compa…', body: ['# What changed', '  + 11  The author lost their job when the company shut down', ...NOREPLY_B].join('\n') },
  { role: 'context', edit: true, summary: 'Seed 7 deleted', body: ['# What changed', '  - 7  Rumours of layoffs at my company', ...NOREPLY_B].join('\n') },
];
const SEEDS10 = HD.seeds.slice(0, 10);
STATES.push(
  { stage: 1, id: 'brief/empty', name: 'Empty', when: 'New project; chat and seeds.csv empty', View: BriefView, v: { focus: 'chat', msgs: [], seeds: [] } },
  { stage: 1, id: 'brief/streaming', name: 'Agent replying', when: 'Reply streams into the live line', View: BriefView, v: { focus: 'chat', msgs: BRIEF_MSGS, streaming: 'Got it. Adding seeds for first-person accounts', seeds: [] } },
  { stage: 1, id: 'brief/seeds', name: 'Seeds proposed', when: 'propose_seeds appended rows; seeds focused', View: BriefView, v: { focus: 'seeds', cursor: 2, msgs: [...BRIEF_MSGS, BRIEF_TOOL, { role: 'agent', text: 'Added 10 seeds. Edit or delete any that miss.' }], seeds: SEEDS10 }, go: { F2: 'brief/confirm', e: 'brief/editing' } },
  { stage: 1, id: 'brief/tool-open', name: 'Tool call expanded', when: 'Tool line opened: arguments and result shown', View: BriefView, v: { focus: 'chat', cursor: 2, msgs: [...BRIEF_MSGS, { ...BRIEF_TOOL, open: true }, { role: 'agent', text: 'Added 10 seeds. Edit or delete any that miss.' }], seeds: SEEDS10 } },
  { stage: 1, id: 'brief/edits-sent', name: 'Your seed edits sent to the assistant', when: 'Each Save, Add or delete appends a context line to the chat history; no model call', View: BriefView, v: { focus: 'seeds', cursor: 2, msgs: [...BRIEF_MSGS, BRIEF_TOOL, { role: 'agent', text: 'Added 10 seeds. Edit or delete any that miss.' }, ...SEED_EDITS], seeds: [...SEEDS10.slice(0, 2), 'My position was eliminated last week, along with my whole team', ...SEEDS10.slice(3, 6), ...SEEDS10.slice(7), 'The author lost their job when the company shut down'] } },
  { stage: 1, id: 'brief/editing', name: 'Editing a seed', when: 'e on a row: the row becomes an input; Save and Discard shown, other rows dimmed', View: BriefView, v: { focus: 'input', editing: 2, input: 'My position was eliminated last week, along with my whole team', msgs: BRIEF_MSGS, seeds: SEEDS10 } },
  { stage: 1, id: 'brief/adding', name: 'Adding a seed', when: 'a: an empty row is added at the end', View: BriefView, v: { focus: 'input', adding: true, input: 'The author lost their job when the company shut down', msgs: BRIEF_MSGS, seeds: SEEDS10 } },
  { stage: 1, id: 'brief/error', name: 'Chat error', when: 'Network or auth error during a reply', View: BriefView, v: { focus: 'chat', msgs: [...BRIEF_MSGS, { role: 'error', text: 'status_code: 401, model_name: claude-sonnet-5-5, body: invalid x-api-key' }], seeds: SEEDS10 } },
  { stage: 1, id: 'brief/confirm', name: 'Approve seeds', when: 'F2 with seeds', View: BriefView, v: { focus: 'seeds', cursor: 2, msgs: BRIEF_MSGS, seeds: SEEDS10, modal: true } },
);
