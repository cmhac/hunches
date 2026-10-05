Centered dialog over a dimmed screen; used for approval gates and the prompt-edit proposal.

```jsx
<Modal title="Approve" actions={<><Button>Cancel</Button><Button variant="success" focused>Approve</Button></>}>
  Approve 14 seeds and continue to search?
</Modal>
```

- Question is one sentence ending in "?" with the count in it. Enter = focused button, Esc = cancel.
