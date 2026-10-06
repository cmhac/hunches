Row-cursor table for seeds, bands, disagreements and results.

```jsx
<DataTable
  columns={[{ label: 'Band', width: '12ch' }, { label: 'Candidates', width: '12ch', align: 'right' }, { label: '', width: '1fr' }]}
  rows={[['0.60–0.625', '1,204', <Bar value={0.8} width={20} />], { cells: ['Total', '4,812', ''], strong: true }]}
  cursor={0}
/>
```

- Numbers right-aligned with thousands separators. Text columns truncate with … ; full text goes in a detail pane.
- Cursor row is blue with ink text when the table has focus.
