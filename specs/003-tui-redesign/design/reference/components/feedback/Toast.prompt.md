Transient notification for things the user didn't ask to see: autosaves, cache hits, a background run finishing.

```jsx
<Toast severity="success" title="Saved" message="prompt.md written" />
```

- Not for errors the user must act on; those go in a Notice next to the thing that failed.
