One-row key bar at the bottom of every screen (Textual Footer, themed).

```jsx
<Footer keys={[{ key: 'a', label: 'Add' }, { key: 'F2', label: 'Approve seeds' }, { key: 'q', label: 'Quit' }]} />
```

- Order: screen actions → F2 gate → n/p → q. Truncates on the right at 80 cols, so put essentials first.
- Labels are verbs in sentence case, 1–2 words.
