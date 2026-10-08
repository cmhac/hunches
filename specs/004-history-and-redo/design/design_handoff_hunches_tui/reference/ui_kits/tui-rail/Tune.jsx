
function ProposalModal({ app }) {
  return (
    <Modal title="Proposed prompt change" dense width={app.cols - 4} height={app.rows - 2}
      actions={<React.Fragment><Button>Reject</Button><Button variant="success" focused>Accept</Button></React.Fragment>}>
      <div style={{ color: 'var(--fg-muted)', padding: '0 1ch' }}>Built from 7 disagreements. Edit the proposal below; the diff follows.</div>
      <Panel title="diff · current → proposed" grow pad={0} bg="var(--bg)"><Diff text={HD.diff} /></Panel>
      <TextArea title="proposal (editable)" language="markdown" text={HD.proposed} focused cursorLine={4} />
    </Modal>
  );
}
function PromptEditModal({ app, changed, undone, canU }) {
  return (
    <Modal title="Edit prompt" dense width={app.cols - 4} height={app.rows - 2}
      actions={<React.Fragment><Button>Cancel Esc</Button><Button variant="success" focused={changed || undone} disabled={!changed && !undone}>{undone && !changed ? 'Re-run F2' : 'Save and re-run F2'}</Button></React.Fragment>}>
      <div style={{ color: 'var(--fg-muted)', padding: '0 1ch' }}>{undone ? 'prompt.md · version 1, restored by Undo. The dev set has not run with it yet.' : changed ? 'Edited: 2 lines changed. Nothing is saved until you choose Save and re-run.' : 'prompt.md · version 1. Edit the text; the dev set re-runs when you save.'}</div>
      <TextArea title="prompt.md (editable)" language="markdown" text={changed ? HD.proposed : HD.prompt} focused cursorLine={changed ? 7 : 4} />
      <div style={{ display: 'flex', gap: '1ch', alignItems: 'center', flex: '0 0 auto', padding: '0 1ch' }}>
        <UndoRedo compact canUndo={canU} canRedo={undone} disabled={changed} />
        <span style={{ color: 'var(--fg-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{undone ? 'Undid: Prompt: edited by the user' : changed ? 'Typing is undone with ctrl+z. Undo F6 is off until you save or discard.' : 'F6 steps back through saved versions of prompt.md.'}</span>
      </div>
      <Notice>Saving writes prompt.md and re-runs the dev set. Items whose prompt text is unchanged are not re-charged.</Notice>
    </Modal>
  );
}
const NOREPLY_T = ['', '# Instructions', 'No reply needed. Treat this as the current state in your next turn.'];
const T_EDIT_MANUAL = { role: 'context', edit: true, summary: 'Prompt: edited by the user', body: ['# What changed', 'You edited the prompt yourself (no proposal):', '  ~ line 5', '    was: - layoff_story: the author lost their own job.', '    now: - layoff_story: the author lost their own job, including', '    contracts not renewed and voluntary redundancy.', '  ~ line 8', '    was: - off_topic: the item matches none of the labels.', '    now: - off_topic: the item matches none of the labels. Layoffs', '    of friends, family or other companies are off_topic.', '', '# Current prompt', '…full text follows…', ...NOREPLY_T].join('\n') };
const dline = (d, i) => (i + 1) + '. gold ' + d.gold.join(',') + ' → ' + (d.pred === 'failed' ? 'failed' : d.pred.join(',')) + '  ' + d.text.slice(0, 44) + '…' + (d.reason ? '\n     reasoning: ' + d.reason : '');
const T_CTX = { role: 'context', summary: 'Context · dev 0.860 · 7 disagreements', body: ['# Dev set', 'accuracy 0.860 (target 0.90) · macro-F1 0.825 · micro-F1 0.860 · n=50', '', '# Per label', ...PER.dev.map(([n, p, r, f, g]) => n.padEnd(14) + ' P ' + p.toFixed(2) + '  R ' + r.toFixed(2) + '  F1 ' + f.toFixed(2) + '  gold ' + g), '', '# Disagreements (7)', ...HD.dis.map(dline), '', '# Current prompt', '…full text follows…', '# Taxonomy', 'mode: single · 3 labels', '', '# Instructions', 'Reply in two or three sentences: where the classifier stands against the target and the main pattern in the errors. Offer to propose a prompt edit. Call propose_prompt only when the user asks or agrees.'].join('\n') };
const T_AG = { role: 'agent', text: 'The dev set scores 0.860 against a 0.90 target. Most errors are posts about other people\'s layoffs labelled layoff_story, and fear posts predicted as off_topic. I can propose a prompt edit that addresses both.' };
const T_Q = { role: 'user', text: 'Why did "Leadership keeps saying the roadmap is under review" go to off_topic?' };
const T_TOOL = { role: 'tool', name: 'get_disagreements', summary: 'layoff_fear · 3 items', body: '# arguments\nlabel: layoff_fear\nlimit: 5\n# result\n3 items\n  1. Leadership keeps saying the roadmap…\n     gold layoff_fear → off_topic\n     reasoning: ' + HD.dis[1].reason + '\n  2. Watching my friends get laid off…\n     gold off_topic → layoff_fear\n     reasoning: ' + HD.dis[4].reason + '\n  3. I was told my contract will not be renewed…\n     gold layoff_story → layoff_fear\n     reasoning: ' + HD.dis[2].reason };
const T_A1 = { role: 'agent', text: 'The prompt only describes layoff_fear as the author worrying they will lose their job. The classifier reasoning says the remark about a roadmap never mentions jobs, so it treats it as unrelated. Naming indirect signals such as reviews, restructures and freezes would help, but it risks pulling in ordinary corporate chatter.' };
const T_ASK = { role: 'user', text: 'Propose a prompt edit based on the current disagreements.' };
const T_PTOOL = { role: 'tool', name: 'propose_prompt', summary: 'Proposal ready for review', body: '# arguments\nrationale: Count non-renewals and voluntary redundancy as layoff_story; treat layoffs of friends, family or other companies as off_topic.\nprompt: # Classifier\n  You label one social media post. …\n# result\nProposal ready for review.' };
const T_PAG = { role: 'agent', text: 'I changed two lines: layoff_story now includes contracts that were not renewed and voluntary redundancy, and off_topic now covers layoffs of friends, family and other companies. Review the diff and edit it if needed.' };
const T_EDIT_PROMPT = { role: 'context', edit: true, summary: 'Prompt: proposal accepted with edits', body: ['# What changed', 'You accepted the proposal and edited it:', '  ~ line 8', '    was: of friends, family or other companies are off_topic.', '    now: of friends, family or other companies are off_topic, even if', '    the author is anxious about their own job.', '', '# Current prompt', '…full text follows…', ...NOREPLY_T].join('\n') };
const T_EDIT_TARGET = { role: 'context', edit: true, summary: 'Target: macro_f1 ≥ 0.85', body: ['# What changed', 'target metric: accuracy → macro_f1', 'target score: 0.90 → 0.85', ...NOREPLY_T].join('\n') };
const T_CTX_UP = { role: 'context', updated: true, summary: 'Dev run · accuracy 0.860 → 0.920', body: ['# Dev set (prompt version 2)', 'accuracy 0.920 (target 0.90): target met', 'macro-F1 0.908 · micro-F1 0.920 · n=50', '', '# Disagreements (4)', ...HD.dis.slice(0, 4).map(dline), '', '# Instructions', 'Reply in two or three sentences: what changed since the last run and whether the target is met.'].join('\n') };
const T_AG_UP = { role: 'agent', text: 'Accuracy rose from 0.860 to 0.920, which meets the 0.90 target. Four disagreements remain, mostly off_topic items labelled layoff_story. You can finish tuning or ask me for another pass.' };

const Tabs = ({ tab, unread }) => (
  <div style={{ display: 'flex', gap: '1ch', padding: '0', flex: '0 0 auto', margin: '0 0 calc(var(--row) / 2)', background: 'var(--surface)' }}>
    {[['chat', 'Chat'], ['results', 'Results']].map(([k, l]) => { const on = tab === k; return <span key={k} style={{ background: on ? 'var(--panel)' : 'transparent', boxShadow: on ? 'inset 0.5ch 0 0 var(--primary)' : 'none', color: on ? 'var(--fg-strong)' : 'var(--fg-muted)', fontWeight: on ? 700 : 400, padding: '0 1ch 0 2ch', whiteSpace: 'pre' }}>{l}{k === 'chat' && unread && !on ? <span style={{ color: 'var(--accent)' }}> ●</span> : null}</span>; })}
  </div>
);
function TuneView({ v, app }) {
  const wide = app.cols >= 120;
  const keys = [...(v.stale ? [['r', 'Re-run']] : []), ['e', 'Propose edit'], ['o', 'Edit prompt'], ['m', 'Target metric'], ['F2', 'Done']];
  const fkeys = v.running ? [v.stopped ? ['s', 'Resume'] : ['x', 'Stop']] : wide ? keys : [['c', 'Chat'], ...(v.stale ? [['r', 'Re-run']] : []), ['e', 'Propose'], ['o', 'Prompt'], ['m', 'Metric'], ['F2', 'Done']];
  if (v.notReady) return <NotReady text="Finish stage 3 (taxonomy and prompt) first." keys={keys} />;
  const metric = v.metric || 'accuracy';
  const target = v.target ?? 0.9;
  const m = v.m === undefined ? M_DEV : v.m;
  const items = v.dis ?? HD.dis;
  const running = !!v.running;
  const tab = v.tab || 'results';
  const busy = !!v.streaming;
  const tone = v.noteTone || (v.note && /failed/.test(v.note) ? 'error' : v.note && /^Running|finished/.test(v.note) ? 'note' : 'warn');
  const results = running ? (
    <RunningView bare stopped={v.stopped} label="Running the dev set" done={v.running[0]} total={v.running[1]} sub={v.sub} eta={v.eta} />
  ) : (
    <React.Fragment>
      {v.stale ? <Notice tone="stale" banner>{'STALE: prompt.md changed outside hunches since the dev set ran. These results are from the earlier prompt. Press r to re-run, then approve again. F9 shows the redo plan.'}</Notice> : null}
      <MetricsPanel title="dev set" m={m} metric={metric} target={target} subtitle={'target ' + metric + ' ≥ ' + target.toFixed(2)} trend={v.trend} />
      <DisView stacked={wide} items={m ? items : []} cursor={v.cursor ?? 0} focused={!v.chatFocus} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'calc(var(--row) / 2)', justifyContent: 'center', height: 'calc(var(--row) * 3.5)', flex: '0 0 auto' }}>
      <ActionRow flush justify="center">
        <div style={{ flex: '0 0 14ch' }}><Select compact value={metric} options={['accuracy', 'macro_f1', 'micro_f1', 'exact_match']} /></div>
        <Button compact>−</Button><span style={strong}>{target.toFixed(2)}</span><Button compact>+</Button>
      </ActionRow>
      <ActionRow flush justify="center">
        {v.stale ? <Button compact variant="primary">Re-run r</Button> : null}
        <Button compact disabled={!m || !items.length || busy}>Propose edit e</Button>
        <Button compact disabled={!m || busy}>Edit prompt o</Button>
        <Button compact variant={m && targetValue(m, metric) >= target ? 'success' : 'default'} disabled={!m || !!v.stale}>Done F2</Button>
      </ActionRow>
      </div>
      {v.note ? <Notice tone={tone}>{v.note}</Notice> : null}
    </React.Fragment>
  );
  const chat = (
    <div style={{ flex: wide ? '0 0 42ch' : 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', paddingBottom: 'calc(var(--row) / 2)', '--panel-gap': '0px', opacity: running ? 0.4 : 1, pointerEvents: running ? 'none' : 'auto' }}>
      <ChatPanel title="chat · tuning" model={HD.smart} focused={!!v.chatFocus} messages={v.msgs || []} streaming={v.streaming} input={v.chat || ''} empty="The assistant gets the results when the dev run finishes." />
    </div>
  );
  const col = (el) => <div style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>{el}</div>;
  return (
    <React.Fragment>
      {running ? <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>{col(results)}</div> : wide ? <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>{chat}{col(results)}</div> : (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <Tabs tab={tab} unread={!!v.unread || !!v.streaming} />
          {tab === 'chat' ? chat : col(results)}
        </div>
      )}
      <Footer keys={K(...fkeys)} />
      {v.modal === 'proposal' ? <ProposalModal app={app} /> : null}
      {v.modal === 'editprompt' ? <PromptEditModal app={app} changed={!!v.changed} undone={!!v.undone} canU={!!v.canU} /> : null}
      {v.modal === 'removegold' ? <RemoveGoldModal split="dev" o={{ n: 6, labelled: 4 }} by="assistant" /> : null}
      {v.modal === 'confirm' ? <ConfirmModal q={metric + ' ' + targetValue(m, metric).toFixed(3) + ' is below the target ' + target.toFixed(2) + '. Accept tuning anyway?'} /> : null}
    </React.Fragment>
  );
}
const T_CTX_S = { role: 'context', updated: true, summary: 'Status · 4 stages stale · 6 of 50 dev rows orphaned', body: ['# Status', 'stage 3  Taxonomy and prompt   current', 'stage 4  Gold dev set          current', 'stage 5  Tuning loop           STALE: prompt changed', 'stage 6  Gold test set         STALE: prompt changed', 'stage 7  Threshold             STALE: prompt changed, seeds changed', 'stage 8  Full run              STALE: prompt changed', '', '# Gold coverage', 'dev   50 rows · 44 in the pool · 6 orphaned (4 labelled)', 'test  50 rows · 50 in the pool · 0 orphaned', '', '# Instructions', 'Reply in one or two sentences: which stages are stale and why. Do not call remove_gold unless the user asks or agrees.'].join('\n') };
const T_AG_S = { role: 'agent', text: 'Four stages are stale because the prompt changed, and six of your 50 dev rows are no longer in the candidate pool. Re-run the dev set first; I can look at the new disagreements afterwards.' };
const T_GQ = { role: 'user', text: 'Some of my gold items disappeared after I changed the seeds. What should I do?' };
const T_GT = { role: 'tool', name: 'get_gold_coverage', summary: 'dev 6 orphaned · test 0 orphaned', body: '# arguments\nsplit: all\n# result\ndev   50 rows · 44 in the pool · 6 orphaned (4 labelled)\n  orphaned ids: 7f3a91, 0c2b44, 91d0e7, a3f81c, 0b19e4, 5d7710\ntest  50 rows · 50 in the pool · 0 orphaned' };
const T_GA = { role: 'agent', text: 'Six of your 50 dev rows are no longer in the candidate pool because the seeds changed. Four are labelled, so removing them discards four labels. After that you can draw six replacements on the Gold screen. Should I remove them?' };
const T_GR = { role: 'tool', name: 'remove_gold', summary: 'waiting for your confirmation', body: '# arguments\nsplit: dev\nids: 7f3a91, 0c2b44, 91d0e7, a3f81c, 0b19e4, 5d7710\n# result\nWaiting for the user to confirm.' };
const BASE = [T_CTX, T_AG];
const Q2 = { role: 'user', text: 'Propose something that handles the friends and family cases.' };
STATES.push(
  { stage: 5, id: 'tune/not-ready', name: 'Not ready', when: 'Reached before stage 3', View: TuneView, v: { notReady: true } },
  { stage: 5, id: 'tune/first-run', name: 'First dev run', when: 'On mount: dev set classified, no metrics yet; chat waits for the results', View: TuneView, v: { running: [23, 50], eta: '14s', sub: 'classifier ' + HD.cheap, msgs: [] } },
  { stage: 5, id: 'tune/below', name: 'Below target', when: 'Run finished; FAIL; context sent, assistant summarised', View: TuneView, v: { msgs: BASE, unread: true }, go: { e: 'tune/asking', o: 'tune/edit-prompt', F2: 'tune/confirm', m: 'tune/metric', c: 'tune/chat-tab' } },
  { stage: 5, id: 'tune/chat-tab', name: 'Chat tab (under 120 columns)', when: 'Below 120 columns the chat is a tab; c switches to it', View: TuneView, v: { tab: 'chat', msgs: BASE, chatFocus: true, chat: 'Which label has the most errors?' } },
  { stage: 5, id: 'tune/chat-focus', name: 'Typing to the assistant', when: 'Focus in the chat input; single-letter keys type instead of acting', View: TuneView, v: { chatFocus: true, chat: 'Which label has the most errors?', msgs: BASE } },
  { stage: 5, id: 'tune/chatting', name: 'Question answered', when: 'User asked; assistant read more disagreements with get_disagreements', View: TuneView, v: { msgs: [...BASE, T_Q, T_TOOL, T_A1], chatFocus: true } },
  { stage: 5, id: 'tune/tool-open', name: 'Tool call expanded', when: 'get_disagreements opened: arguments and result', View: TuneView, v: { msgs: [...BASE, T_Q, { ...T_TOOL, open: true }, T_A1] } },
  { stage: 5, id: 'tune/failed-item', name: 'Failed item selected', when: 'Cursor on a row whose call failed', View: TuneView, v: { cursor: 5, msgs: BASE } },
  { stage: 5, id: 'tune/metric', name: 'Other target metric', when: 'm cycles metrics (or the select); the change is sent to the assistant', View: TuneView, v: { metric: 'macro_f1', target: 0.85, msgs: [...BASE, T_EDIT_TARGET] } },
  { stage: 5, id: 'tune/asking', name: 'Propose edit pressed', when: 'e or the button sends a canned user turn; the assistant streams', View: TuneView, v: { msgs: [...BASE, T_ASK], streaming: 'Looking at the seven disagreements. Two patterns account for five of them' }, go: { e: 'tune/proposal' } },
  { stage: 5, id: 'tune/proposal', name: 'Prompt proposal', when: 'Assistant called propose_prompt; diff + editable proposal; card pending in the chat', View: TuneView, v: { modal: 'proposal', msgs: [...BASE, Q2, T_PTOOL, T_PAG, { role: 'proposal', status: 'pending', plus: 4, minus: 2 }] }, go: { Enter: 'tune/rerun' } },
  { stage: 5, id: 'tune/proposal-pending', name: 'Proposal pending in chat', when: 'Modal dismissed; Review reopens it', View: TuneView, v: { msgs: [...BASE, Q2, T_PTOOL, T_PAG, { role: 'proposal', status: 'pending', plus: 4, minus: 2 }], chatFocus: true } },
  { stage: 5, id: 'tune/edit-prompt', name: 'Edit prompt (manual)', when: 'o or the Edit prompt button; Save and re-run disabled until the text changes', View: TuneView, v: { modal: 'editprompt', msgs: BASE }, go: { Enter: 'tune/edit-prompt-changed' } },
  { stage: 5, id: 'tune/edit-prompt-undone', name: 'Edit prompt, after Undo', when: 'Undo F6 inside the editor stepped prompt.md back one saved version; the box shows it, Redo is on, and the primary button re-runs the dev set', View: TuneView, v: { modal: 'editprompt', undone: true, canU: true, msgs: BASE } },
  { stage: 5, id: 'tune/edit-prompt-changed', name: 'Edit prompt, changed', when: 'Text differs from prompt.md; Save and re-run enabled', View: TuneView, v: { modal: 'editprompt', changed: true, msgs: BASE }, go: { F2: 'tune/rerun-manual' } },
  { stage: 5, id: 'tune/rerun-manual', name: 'Re-running after manual edit', when: 'Saved; prompt.md written; the edit is sent to the assistant as context; chat hidden during the run', View: TuneView, v: { running: [14, 50], eta: '11s', sub: 'prompt version 2', trend: [0.86], msgs: [...BASE, T_EDIT_MANUAL] } },
  { stage: 5, id: 'tune/stale', name: 'Stale: prompt changed outside', when: 'prompt.md differs from the prompt of the last dev run (outside edit, undo, or a taxonomy-side edit). Done is disabled until the dev set is re-run', marks: STALE_ALL, View: TuneView, v: { stale: true, msgs: BASE } },
  { stage: 5, id: 'tune/status-context', name: 'Assistant told what is stale', when: 'New context sections: # Status and # Gold coverage arrive as the usual context line, then a short reply', marks: STALE_ALL, View: TuneView, v: { stale: true, msgs: [T_CTX, T_AG, { ...T_CTX_S, open: true }, T_AG_S] } },
  { stage: 5, id: 'tune/gold-coverage', name: 'Gold coverage tool', when: 'The assistant read gold coverage with a new read-only tool', View: TuneView, v: { msgs: [...BASE, T_GQ, { ...T_GT, open: true }, T_GA] } },
  { stage: 5, id: 'tune/remove-gold', name: 'Assistant asks to remove gold', when: 'remove_gold does nothing until the user confirms in this modal; the tool line shows it is waiting', View: TuneView, v: { modal: 'removegold', msgs: [...BASE, T_GQ, T_GT, T_GA, { role: 'user', text: 'Yes, remove them.' }, T_GR] } },
  { stage: 5, id: 'tune/stopped', name: 'Dev run stopped', when: 'x pressed during a dev run; finished items are cached, Resume continues', View: TuneView, v: { running: [23, 50], stopped: true, sub: 'classifier ' + HD.cheap, msgs: [] } },
  { stage: 5, id: 'tune/rerun', name: 'Re-running after accept', when: 'Accepted proposal; prompt.md written; chat waits', View: TuneView, v: { running: [31, 50], eta: '9s', sub: 'prompt version 2', trend: [0.86], msgs: [...BASE, Q2, T_PTOOL, T_PAG, { role: 'proposal', status: 'accepted', plus: 4, minus: 2, note: 'dev set re-running' }, T_EDIT_PROMPT] } },
  { stage: 5, id: 'tune/pass', name: 'Target met', when: 'PASS; UPDATED context line and a short assistant reply', View: TuneView, v: { m: M_DEV2, dis: HD.dis.slice(0, 4), trend: [0.86, 0.92], msgs: [T_PTOOL, T_PAG, { role: 'proposal', status: 'accepted', plus: 4, minus: 2 }, T_EDIT_PROMPT, T_CTX_UP, T_AG_UP] } },
  { stage: 5, id: 'tune/rejected', name: 'Proposal rejected', when: 'Reject in the modal or the card; the assistant is told', View: TuneView, v: { msgs: [...BASE, Q2, T_PTOOL, { role: 'proposal', status: 'rejected', plus: 4, minus: 2 }, { role: 'agent', text: 'Understood, I will leave the prompt as it is. Tell me what to change and I can try again.' }] } },
  { stage: 5, id: 'tune/no-dis', name: 'No disagreements', when: 'e with nothing to learn from', View: TuneView, v: { m: { exact_match: 1, macro_f1: 1, micro_f1: 1, n: 50, per: PER.dev2.map(([n, , , , g]) => [n, 1, 1, 1, g]) }, dis: [], note: 'No disagreements to learn from.', msgs: [T_CTX, { role: 'agent', text: 'The classifier agrees with every gold label on the dev set, so there is nothing to tune. You can finish.' }] } },
  { stage: 5, id: 'tune/run-failed', name: 'Dev run failed', when: 'Auth or network error during the run', View: TuneView, v: { m: null, note: 'Dev run failed: status_code: 401, body: invalid x-api-key', msgs: [] } },
  { stage: 5, id: 'tune/proposal-failed', name: 'Assistant error', when: 'Assistant call errored; shown in the chat as an error line', View: TuneView, v: { msgs: [...BASE, T_ASK, { role: 'error', text: 'status_code: 529, overloaded_error' }] } },
  { stage: 5, id: 'tune/confirm', name: 'Accept below target', when: 'F2 while FAIL', View: TuneView, v: { modal: 'confirm', msgs: BASE } },
);
