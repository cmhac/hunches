Smart-model chat: log of turns plus a message input.

```jsx
<ChatPanel model="claude-sonnet-4-5" focused messages={[
  { role: 'user', text: 'Find posts where someone describes being laid off.' },
  { role: 'agent', text: 'First-person accounts only, or reporting too?' },
  { role: 'tool', text: 'propose_seeds · added 6 seeds' },
]} />
```

- Gutters: › user (blue), │ agent (teal), ↳ tool call (muted), Error: (red). One blank row between turns.
- Streaming text is teal with a block cursor until the reply completes.
