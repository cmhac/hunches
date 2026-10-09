Terminal viewport sized in character cells; wrap every mocked hunches screen in one.

```jsx
<Terminal cols={80} rows={24} title="~/layoffs">
  <StatusHeader project="layoffs" stage={2} cost={0.0412} />
  <div style={{ flex: 1 }}>…</div>
  <Footer keys={[{ key: 'r', label: 'Run search' }]} />
</Terminal>
```

- Body is a flex column; header and footer take one row each, give the middle `flex: 1`.
- Design at 80×24 first, then check 120×36. Content must never assume more than 80 columns.
- `chrome={false}` for a bare cell grid.
