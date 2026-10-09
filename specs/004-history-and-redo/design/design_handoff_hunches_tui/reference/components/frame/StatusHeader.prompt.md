One-row header shown on every screen: `hunches`, project, stepper ●●◉○○○○○○, stage name and total cost.

```jsx
<StatusHeader project="layoffs" stage={3} cost={0.4213} />
<StatusHeader project="layoffs" stage={5} unknownModels={['openai:gpt-9-mini']} />
```

- Cost is always 4 decimals. If any model is unpriced, the cost block turns amber and reads `cost ?`; never show $0.
- Stepper: ● done (muted), ◉ current (primary), ○ upcoming (faint).
