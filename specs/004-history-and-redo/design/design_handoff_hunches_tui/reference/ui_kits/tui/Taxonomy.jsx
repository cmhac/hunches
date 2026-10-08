const TAX_MSGS = [
  { role: 'agent', text: 'Is there one thing to find, or several kinds of post?' },
  { role: 'user', text: 'Three: own layoff, fear of one, hiring freeze.' },
  { role: 'agent', text: 'Can a post get more than one of those?' },
  { role: 'user', text: 'No, pick the main one.' },
  { role: 'tool', text: 'write_taxonomy · Taxonomy written.' },
  { role: 'tool', text: 'write_prompt · Prompt written.' },
];
function TaxonomyView({ v }) {
  const focus = v.focus ?? 0;
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <ChatPanel title="chat · taxonomy" model={HD.smart} focused={focus === 0} messages={v.msgs || []} streaming={v.streaming} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <TextArea title="taxonomy.yaml (editable)" language="yaml" text={v.taxonomy ?? ''} focused={focus === 1} cursorLine={focus === 1 ? (v.cursorLine ?? 2) : -1} />
          <TextArea title="prompt.md (editable)" language="markdown" text={v.prompt ?? ''} focused={focus === 2} cursorLine={focus === 2 ? 0 : -1} />
        </div>
      </div>
      {v.status ? <Notice tone="warn">{v.status}</Notice> : null}
      <Footer keys={K(['F2', 'Approve'])} />
      {v.modal ? <ConfirmModal q="Approve taxonomy (single, 3 labels) and prompt?" /> : null}
    </React.Fragment>
  );
}
STATES.push(
  { stage: 3, id: 'taxonomy/start', name: 'Interview starts', when: 'No taxonomy.yaml or prompt.md yet', View: TaxonomyView, v: { focus: 0, msgs: [], streaming: 'Is there one thing to find, or several kinds of post?' } },
  { stage: 3, id: 'taxonomy/drafted', name: 'Files written', when: 'Agent called write_taxonomy and write_prompt', View: TaxonomyView, v: { focus: 1, msgs: TAX_MSGS, taxonomy: HD.taxonomy, prompt: HD.prompt }, go: { F2: 'taxonomy/confirm' } },
  { stage: 3, id: 'taxonomy/invalid', name: 'Invalid yaml edit', when: 'Hand edit fails validation; file not written', View: TaxonomyView, v: { focus: 1, cursorLine: 2, msgs: TAX_MSGS, taxonomy: HD.taxonomy.replace('- name: layoff_story', '- name: off_topic'), prompt: HD.prompt, status: "taxonomy.yaml not saved: 1 validation error for Taxonomy" } },
  { stage: 3, id: 'taxonomy/cannot', name: 'Cannot approve', when: 'F2 with no labels or empty prompt.md', View: TaxonomyView, v: { focus: 2, msgs: TAX_MSGS.slice(0, 5), taxonomy: HD.taxonomy, prompt: '', status: 'Cannot approve: need at least one label and a prompt.' } },
  { stage: 3, id: 'taxonomy/missing', name: 'No valid taxonomy', when: 'F2 with missing or unreadable taxonomy.yaml', View: TaxonomyView, v: { focus: 0, msgs: TAX_MSGS.slice(0, 2), taxonomy: '', prompt: '', status: "Cannot approve: no valid taxonomy.yaml ([Errno 2] No such file or directory: '.hunches/taxonomy.yaml')" } },
  { stage: 3, id: 'taxonomy/confirm', name: 'Approve', when: 'F2 with a valid taxonomy and prompt', View: TaxonomyView, v: { focus: 1, msgs: TAX_MSGS, taxonomy: HD.taxonomy, prompt: HD.prompt, modal: true } },
);
