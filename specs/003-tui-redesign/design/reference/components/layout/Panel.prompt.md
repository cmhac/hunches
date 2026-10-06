Bordered region with a title on the top edge; the main building block of every screen.

```jsx
<div style={{ display: 'flex', flex: 1 }}>
  <Panel title="chat" grow focused>…</Panel>
  <Panel title="seeds.csv · 14" grow>…</Panel>
</div>
```

- Consumes 1 cell on each side (2 cols, 2 rows). Two side-by-side panels at 80 cols leave 36 cols of text each.
- Only the focused panel gets the blue border.
