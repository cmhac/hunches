const SUMMARY = 'I read the seed conversation and the search results. 12 seeds found 3,612 candidates, 1,050 of them from "The author says they were laid off". I am ready to start building the taxonomy. Is there one thing to find, or several kinds of post?';
const ctxBody = () => [
  '# Brief conversation',
  ...BRIEF_MSGS.map((m) => (m.role === 'user' ? 'user: ' : 'assistant: ') + m.text),
  '',
  '# Seeds and results (items won)',
  ...HD.won.map(([n, i]) => fmt(n).padStart(6) + '  ' + HD.seeds[i]),
  '',
  '# Search',
  '3,612 candidates at or above 0.60',
  HD.bands.map((b, i) => b + ': ' + fmt(HD.bandCounts[i])).join(' · '),
  '',
  '# Instructions',
  'Reply in two or three sentences: where things stand, and that you are ready to start building the taxonomy. Then begin the interview. Draft the prompt from the seeds and the best matches as the answers come in.',
].join('\n');
const CTX = { role: 'context', summary: 'Context · 12 seeds · 3,612 candidates', body: ctxBody() };
const CTX_UP = { role: 'context', updated: true, summary: 'Seeds changed · 4,019 candidates (+407)', body: ['# What changed', 'seeds: 2 added, 1 removed', '  + The author lost their job when their company shut down', '  + The author took voluntary redundancy', '  - Rumours of layoffs at my company', 'candidates: 3,612 → 4,019', '', '# Seeds and results (items won)', '  1,198  The author says they were laid off', '    …', '', '# Instructions', 'Reply in one or two sentences: what changed and whether it affects the conversation so far. Then continue where you left off.'].join('\n') };
const NOREPLY = ['', '# Instructions', 'No reply needed. Treat this as the current state in your next turn.'];
const EDIT_LABELS = { role: 'context', edit: true, summary: 'Labels: layoff_fear description', body: ['# What changed', 'labels: 1 edited', '  ~ layoff_fear', '    was: Author worries about losing their job', '    now: Author worries they will lose their job soon', '', '# Current taxonomy', 'mode: single', 'labels:', '  - layoff_story: Author describes losing their own job', '  - layoff_fear: Author worries they will lose their job soon', "  - hiring_freeze: Author's employer stopped hiring", ...NOREPLY].join('\n') };
const EDIT_MODE = { role: 'context', edit: true, summary: 'Mode: one label → several labels', body: ['# What changed', 'mode: single → multi', '', '# Current taxonomy', 'mode: multi', 'labels: layoff_story, layoff_fear, hiring_freeze', ...NOREPLY].join('\n') };
const EDIT_PROMPT = { role: 'context', edit: true, summary: 'Prompt: 1 line changed', body: ['# What changed', '- - layoff_story: the author lost their own job.', '+ - layoff_story: the author lost their own job, including contracts not renewed.', '', '# Current prompt', '…full text follows…', ...NOREPLY].join('\n') };
const AG = { role: 'agent', text: SUMMARY };
const TAX_MSGS = [
  CTX, AG,
  { role: 'user', text: 'Three: own layoff, fear of one, hiring freeze.' },
  { role: 'agent', text: 'Can a post get more than one of those?' },
  { role: 'user', text: 'No, pick the main one.' },
  { role: 'tool', name: 'write_taxonomy', summary: 'Taxonomy written.', body: '# arguments\nmode: single\nlabels:\n  - layoff_story: Author describes losing their own job\n  - layoff_fear: Author worries about losing their job\n  - hiring_freeze: Author\'s employer stopped hiring\n# result\nTaxonomy written.' },
  { role: 'tool', name: 'write_prompt', summary: 'Prompt written.', body: '# arguments\nprompt: # Classifier\n  You label one social media post. …\n# result\nPrompt written.' },
];
const txBar = (c) => 'inset 0.5ch 0 0 ' + c;
const txCaret = <span style={{ background: 'var(--primary)', color: 'var(--ink-1)' }}> </span>;
const txClip = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 };
const MODE_OPTS = [{ label: 'One label per item', value: 'single' }, { label: 'Several labels per item', value: 'multi' }];
const ModeSwitch = ({ mode, open }) => (
  <div style={{ flex: '0 0 auto' }}>
    <div style={{ display: 'flex', gap: '1ch', alignItems: 'center' }}>
      <span style={{ flex: '0 0 6ch', color: 'var(--fg-muted)' }}>mode</span>
      <div style={{ flex: '0 1 28ch', minWidth: 0 }}><Select compact value={mode || 'Choose…'} options={MODE_OPTS} open={open} focused={open} /></div>
    </div>
  </div>
);
const TX_LABELS = HD.labels.slice(0, 3);
function renderPrompt(src) {
  return src.split('\n').map((l, i) => {
    if (l.indexOf('# ') === 0) return <div key={i} style={{ color: 'var(--primary)', fontWeight: 700 }}>{l.slice(2)}</div>;
    if (l.indexOf('## ') === 0) return <div key={i} style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>{l.slice(3)}</div>;
    const m = /^- ([a-z_]+): (.*)$/.exec(l);
    if (m) return <div key={i} style={{ display: 'flex', gap: '1ch' }}><span style={{ color: 'var(--fg-faint)' }}>•</span><span style={{ minWidth: 0, whiteSpace: 'pre-wrap' }}><LabelTag name={m[1]} color={labelColor(m[1])} /><span style={{ color: 'var(--fg-muted)' }}>: </span>{m[2]}</span></div>;
    if (/^ {2}\S/.test(l)) return <div key={i} style={{ paddingLeft: '2ch', whiteSpace: 'pre-wrap' }}>{l.trim()}</div>;
    return <div key={i} style={{ whiteSpace: 'pre-wrap', minHeight: 'var(--row)' }}>{l}</div>;
  });
}
function EditBar({ dirty, err, save }) {
  return (
    <div style={{ flex: '0 0 auto', marginTop: 'var(--row)', minWidth: 0 }}>
      <div style={{ display: 'flex', gap: '1ch', flexWrap: 'wrap' }}>
        <Button variant="success" disabled={!dirty || !!err}> {save} ^s </Button>
        <Button> Discard Esc </Button>
      </div>
      {err ? <div style={{ color: 'var(--error)', ...txClip }}>{err}</div> : null}
    </div>
  );
}
function TaxonomyView({ v }) {
  const focus = v.focus ?? 0;
  const has = !!v.taxonomy, hasP = !!v.prompt;
  const editL = v.edit === 'labels', editP = v.edit === 'prompt';
  const mode = v.mode || 'single';
  const labels = v.draftLabels || (has ? TX_LABELS : []);
  const dup = labels.find((l) => l.name === 'off_topic');
  const lerr = dup ? 'off_topic is built in; do not list it' : null;
  const upd = (k) => (v.updated === k || v.updated === 'both' ? <Badge tone="info">UPDATED BY ASSISTANT</Badge> : null);
  const promptSrc = v.draftPrompt || HD.prompt;
  const lines = promptSrc.split('\n');
  const empty = (t) => <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--fg-muted)', whiteSpace: 'pre-wrap', padding: '0 2ch' }}>{t}</div>;
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <ChatPanel title="chat · taxonomy" model={HD.smart} focused={focus === 0 && !v.edit} messages={v.msgs || []} streaming={v.streaming} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <Panel title="Labels" subtitle={editL ? <Badge tone="stale">{v.dirty ? 'UNSAVED' : 'EDITING'}</Badge> : has ? <span style={{ whiteSpace: 'pre' }}>{upd('labels') || <span style={{ color: 'var(--fg-muted)' }}>{mode} · {labels.length} labels</span>}</span> : null} focused={focus === 1 || editL} grow style={{ opacity: editP ? 0.45 : 1 }}>
            {!has ? <React.Fragment><ModeSwitch mode={null} />{empty('No labels yet. The assistant will propose them as you talk.')}</React.Fragment> : editL ? (
              <React.Fragment>
                <ModeSwitch mode={mode} />
                <div style={{ height: 'var(--row)', flex: '0 0 auto' }}></div>
                {labels.map((l, i) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '15ch minmax(0,1fr) 3ch', gap: '0 1ch', alignItems: 'center', flex: '0 0 auto', boxShadow: l.name === 'off_topic' ? txBar('var(--error)') : 'none' }}>
                    <Input value={l.name} focused={v.editFocus === i} />
                    <Input value={l.description} />
                    <span style={{ color: 'var(--fg-faint)', textAlign: 'center' }}>✕</span>
                  </div>
                ))}
                <div style={{ flex: '0 0 auto', marginTop: 'var(--row)' }}><Button>  + Add label  a  </Button></div>
                <div style={{ flex: 1 }}></div>
                <EditBar dirty={v.dirty} err={lerr} save="Save" />
              </React.Fragment>
            ) : (
              <React.Fragment>
                <ModeSwitch mode={mode} open={v.modeOpen} />
                <div style={{ height: 'var(--row)', flex: '0 0 auto' }}></div>
                {labels.map((l) => (
                  <div key={l.name} style={{ display: 'grid', gridTemplateColumns: '16ch minmax(0,1fr)', gap: '0 1ch', flex: '0 0 auto' }}>
                    <LabelTag name={l.name} color={labelColor(l.name)} /><span style={{ color: 'var(--fg-muted)', ...txClip }}>{l.description}</span>
                  </div>
                ))}
                <div style={{ display: 'grid', gridTemplateColumns: '16ch minmax(0,1fr)', gap: '0 1ch', flex: '0 0 auto' }}>
                  <LabelTag name="off_topic" color="var(--label-off)" /><span style={{ color: 'var(--fg-faint)', ...txClip }}>built in · matches none of the labels</span>
                </div>
                <div style={{ flex: 1 }}></div>
                <div style={{ flex: '0 0 auto' }}><Button>  Edit labels  e  </Button></div>
              </React.Fragment>
            )}
          </Panel>
          <Panel title="Prompt" subtitle={editP ? <Badge tone="stale">{v.dirty ? 'UNSAVED' : 'EDITING'}</Badge> : hasP ? (upd('prompt') || <span style={{ color: 'var(--fg-muted)' }}>classifier prompt</span>) : null} focused={focus === 2 || editP} grow={1.3} style={{ opacity: editL ? 0.45 : 1 }}>
            {!hasP ? empty('No prompt yet. The assistant writes the first draft once the labels are set.') : editP ? (
              <React.Fragment>
                <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', background: 'var(--panel)', boxShadow: txBar('var(--primary)') }}>
                  {lines.map((l, i) => (
                    <div key={i} style={{ display: 'flex', gap: '1ch', padding: '0 1ch', whiteSpace: 'pre', background: i === (v.cursorLine ?? 4) ? 'var(--boost)' : 'transparent' }}>
                      <span style={{ flex: '0 0 3ch', textAlign: 'right', color: 'var(--fg-faint)' }}>{i + 1}</span>
                      <span style={{ ...txClip, color: l[0] === '#' ? 'var(--primary)' : 'var(--fg-strong)', fontWeight: l[0] === '#' ? 700 : 400 }}>{l}{i === (v.cursorLine ?? 4) ? txCaret : null}</span>
                    </div>
                  ))}
                </div>
                <EditBar dirty={v.dirty} save="Save" />
              </React.Fragment>
            ) : (
              <React.Fragment>
                <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>{renderPrompt(promptSrc)}</div>
                <div style={{ flex: '0 0 auto', marginTop: 'var(--row)' }}><Button>  Edit prompt  e  </Button></div>
              </React.Fragment>
            )}
          </Panel>
          <div style={{ display: 'flex', justifyContent: 'center', padding: '0 1ch', flex: '0 0 auto', marginTop: 'var(--row)', marginBottom: 'var(--row)' }}>
            <Button variant="success" disabled={!(has && hasP) || !!v.edit}> Approve  F2 </Button>
          </div>
        </div>
      </div>
      <Footer keys={v.edit ? K(['^s', 'Save'], ['esc', 'Discard']) : K(['e', 'Edit panel'], ['m', 'Mode'], ['F2', 'Approve'])} />
      {v.modal ? <ConfirmModal q="Approve taxonomy (single, 3 labels) and prompt, and start labelling?" /> : null}
    </React.Fragment>
  );
}
STATES.push(
  { stage: 3, id: 'taxonomy/start', name: 'Context sent, agent replying', when: 'No taxonomy.yaml or prompt.md yet: context message sent on mount, summary streams', View: TaxonomyView, v: { focus: 0, msgs: [CTX], streaming: 'I read the seed conversation and the search results. 12 seeds found 3,612 candidates, 1,050 of them from' } },
  { stage: 3, id: 'taxonomy/ready', name: 'Agent ready', when: 'Summary complete; assistant says it is ready to build the taxonomy', View: TaxonomyView, v: { focus: 0, msgs: [CTX, AG] }, go: { Enter: 'taxonomy/context-open' } },
  { stage: 3, id: 'taxonomy/context-open', name: 'Context expanded', when: 'Context line opened: brief transcript, seeds with results, instructions', View: TaxonomyView, v: { focus: 0, msgs: [{ ...CTX, open: true }, AG] } },
  { stage: 3, id: 'taxonomy/context-updated', name: 'Context updated', when: 'Seeds or candidates.jsonl changed since the last context message: new context line, then a short agent reply', View: TaxonomyView, v: { focus: 0, msgs: [CTX, AG, { role: 'user', text: 'Three: own layoff, fear of one, hiring freeze.' }, { role: 'agent', text: 'Can a post get more than one of those?' }, CTX_UP, { role: 'agent', text: 'Two seeds were added and one removed, and the search now returns 4,019 candidates. Nothing in the new seeds changes the three kinds of post you described. Back to my last question: can a post get more than one of them?' }] }, go: { Enter: 'taxonomy/context-updated-open' } },
  { stage: 3, id: 'taxonomy/context-updated-open', name: 'Context update expanded', when: 'Update line opened: what changed, new results, instructions', View: TaxonomyView, v: { focus: 0, msgs: [CTX, AG, { role: 'user', text: 'Three: own layoff, fear of one, hiring freeze.' }, { ...CTX_UP, open: true }, { role: 'agent', text: 'Two seeds were added and one removed, and the search now returns 4,019 candidates. Nothing in the new seeds changes the three kinds of post you described.' }] } },
  { stage: 3, id: 'taxonomy/drafted', name: 'Files written', when: 'Agent called write_taxonomy and write_prompt; panels show the saved files, tagged as updated by the assistant', View: TaxonomyView, v: { focus: 1, msgs: TAX_MSGS, taxonomy: true, prompt: true, updated: 'both' }, go: { F2: 'taxonomy/confirm', e: 'taxonomy/edit-labels' } },
  { stage: 3, id: 'taxonomy/edit-labels', name: 'Editing labels', when: 'e on Labels: mode, names and descriptions become inputs; prompt panel and Approve are inactive', View: TaxonomyView, v: { focus: 1, edit: 'labels', dirty: true, editFocus: 1, msgs: TAX_MSGS, taxonomy: true, prompt: true, draftLabels: [TX_LABELS[0], { ...TX_LABELS[1], description: 'Author worries they will lose their job soon' }, TX_LABELS[2]] }, go: { e: 'taxonomy/edit-prompt' } },
  { stage: 3, id: 'taxonomy/mode-open', name: 'Mode dropdown open', when: 'Select open on the mode: One label per item / Several labels per item', View: TaxonomyView, v: { focus: 1, modeOpen: true, msgs: TAX_MSGS, taxonomy: true, prompt: true } },
  { stage: 3, id: 'taxonomy/mode-changed', name: 'Mode changed', when: 'm (or a click) on the single/several switch: enters labels edit mode with the new mode in the draft', View: TaxonomyView, v: { focus: 1, edit: 'labels', dirty: true, mode: 'multi', msgs: TAX_MSGS, taxonomy: true, prompt: true } },
  { stage: 3, id: 'taxonomy/edit-labels-invalid', name: 'Labels: invalid edit', when: 'Draft fails files.Taxonomy validation (off_topic listed): Save disabled, message shown', View: TaxonomyView, v: { focus: 1, edit: 'labels', dirty: true, editFocus: 2, msgs: TAX_MSGS, taxonomy: true, prompt: true, draftLabels: [TX_LABELS[0], TX_LABELS[1], { name: 'off_topic', description: TX_LABELS[2].description }] } },
  { stage: 3, id: 'taxonomy/edit-prompt', name: 'Editing the prompt', when: 'e on Prompt: raw markdown with line numbers; Save and Discard shown', View: TaxonomyView, v: { focus: 2, edit: 'prompt', dirty: true, msgs: TAX_MSGS, taxonomy: true, prompt: true, cursorLine: 4, draftPrompt: HD.prompt.replace('the author lost their own job.', 'the author lost their own job, including contracts not renewed.') } },
  { stage: 3, id: 'taxonomy/edits-sent', name: 'Your edits sent to the assistant', when: 'Save on Labels, mode or Prompt: a context line is appended to the chat history; no model call', View: TaxonomyView, v: { focus: 0, msgs: [...TAX_MSGS.slice(0, 7), EDIT_MODE, EDIT_LABELS, EDIT_PROMPT], taxonomy: true, prompt: true } },
  { stage: 3, id: 'taxonomy/edits-sent-open', name: 'Edit line expanded', when: 'Edit line opened: what changed, current state, instruction', View: TaxonomyView, v: { focus: 0, msgs: [...TAX_MSGS.slice(0, 7), { ...EDIT_LABELS, open: true }], taxonomy: true, prompt: true } },
  { stage: 3, id: 'taxonomy/tool-open', name: 'Tool call expanded', when: 'Tool line opened: arguments and result shown', View: TaxonomyView, v: { focus: 0, msgs: [...TAX_MSGS.slice(0, 5), { ...TAX_MSGS[5], open: true }, TAX_MSGS[6]], taxonomy: true, prompt: true } },
  { stage: 3, id: 'taxonomy/confirm', name: 'Approve', when: 'F2 with a valid taxonomy and prompt', View: TaxonomyView, v: { focus: 1, msgs: TAX_MSGS, taxonomy: true, prompt: true, modal: true } },
);
