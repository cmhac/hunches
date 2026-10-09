const BRIEF_MSGS = [
  { role: 'user', text: 'Find posts where someone says they were laid off.' },
  { role: 'agent', text: 'Should second-hand accounts count, like "my partner was let go"?' },
  { role: 'user', text: 'No. Only the author.' },
];
function BriefView({ v }) {
  const seeds = v.seeds || [];
  const focus = v.focus || 'seeds';
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <ChatPanel title="chat · brief" model={HD.smart} focused={focus === 'chat'} messages={v.msgs || []} streaming={v.streaming} input={v.chat || ''} />
        <Panel title={'seeds.csv · ' + seeds.length} focused={focus !== 'chat'} grow pad={0}>
          {seeds.length ? (
            <DataTable focused={focus === 'seeds'} cursor={v.cursor ?? 0} style={{ flex: 1 }} columns={[{ label: 'Seed phrases', width: 'minmax(0,1fr)' }]} rows={seeds.slice(0, 12).map((s) => [s])} />
          ) : <div style={{ flex: 1, ...muted, padding: '0 1ch', whiteSpace: 'pre-wrap' }}>No seeds yet. Describe what to find in the chat, or press a to add one.</div>}
          <Input value={v.input || ''} placeholder="a: add, e: edit, then Enter" focused={focus === 'input'} />
          {v.status ? <Notice tone="warn">{v.status}</Notice> : null}
        </Panel>
      </div>
      <Footer keys={K(['a', 'Add seed'], ['e', 'Edit seed'], ['d', 'Delete seed'], ['F2', 'Approve seeds'])} />
      {v.modal ? <ConfirmModal q={'Approve ' + seeds.length + ' seeds and continue to search?'} /> : null}
    </React.Fragment>
  );
}
const SEEDS10 = HD.seeds.slice(0, 10);
STATES.push(
  { stage: 1, id: 'brief/empty', name: 'Empty', when: 'New project; chat and seeds.csv empty', View: BriefView, v: { focus: 'chat', msgs: [], seeds: [] }, go: { F2: 'brief/no-seeds' } },
  { stage: 1, id: 'brief/no-seeds', name: 'Approve with no seeds', when: 'F2 while seeds.csv is empty', View: BriefView, v: { focus: 'seeds', msgs: [], seeds: [], status: 'Add at least one seed first.' } },
  { stage: 1, id: 'brief/streaming', name: 'Agent replying', when: 'Reply streams into the live line', View: BriefView, v: { focus: 'chat', msgs: BRIEF_MSGS, streaming: 'Got it. Adding seeds for first-person accounts', seeds: [] } },
  { stage: 1, id: 'brief/seeds', name: 'Seeds proposed', when: 'propose_seeds appended rows; seeds focused', View: BriefView, v: { focus: 'seeds', cursor: 2, msgs: [...BRIEF_MSGS, { role: 'agent', text: 'Added 10 seeds. Edit or delete any that miss.' }], seeds: SEEDS10 }, go: { F2: 'brief/confirm', e: 'brief/editing' } },
  { stage: 1, id: 'brief/editing', name: 'Editing a seed', when: 'e on a row: input holds its text', View: BriefView, v: { focus: 'input', cursor: 2, input: 'My position was eliminated last week', msgs: BRIEF_MSGS, seeds: SEEDS10 } },
  { stage: 1, id: 'brief/error', name: 'Chat error', when: 'Network or auth error during a reply', View: BriefView, v: { focus: 'chat', msgs: [...BRIEF_MSGS, { role: 'error', text: 'status_code: 401, model_name: claude-sonnet-5-5, body: invalid x-api-key' }], seeds: SEEDS10 } },
  { stage: 1, id: 'brief/confirm', name: 'Approve seeds', when: 'F2 with seeds', View: BriefView, v: { focus: 'seeds', cursor: 2, msgs: BRIEF_MSGS, seeds: SEEDS10, modal: true } },
);
