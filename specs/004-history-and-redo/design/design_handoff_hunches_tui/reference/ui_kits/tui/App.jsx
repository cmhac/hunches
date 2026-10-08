const SIZES = [[80, 24], [100, 30], [120, 36]];

function Screen({ st, cols, rows, unknown, chrome = true }) {
  const app = { cols, rows };
  const View = st.View;
  return (
    <Terminal cols={cols} rows={rows} chrome={chrome} title={'~/' + HD.project}>
      <StatusHeader project={HD.project} stage={st.stage} cost={0.3127} unknownModels={unknown || st.unknownCost ? [HD.cheap] : []} />
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}><View v={st.v} app={app} /></div>
    </Terminal>
  );
}

function App() {
  const saved = JSON.parse(localStorage.getItem('hunches-kit-2') || '{}');
  const [id, setId] = React.useState(STATES.some((s) => s.id === saved.id) ? saved.id : 'brief/seeds');
  const [size, setSize] = React.useState(saved.size ?? 0);
  const [unknown, setUnknown] = React.useState(false);
  const st = STATES.find((s) => s.id === id);
  const [cols, rows] = SIZES[size];
  React.useEffect(() => { localStorage.setItem('hunches-kit-2', JSON.stringify({ id, size })); }, [id, size]);
  const ref = React.useRef();
  ref.current = { id, st };
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const { id, st } = ref.current;
      const i = STATES.findIndex((s) => s.id === id);
      let next = null;
      if (st.go && st.go[e.key]) next = st.go[e.key];
      else if (e.key === ']' || e.key === 'ArrowDown') next = STATES[Math.min(STATES.length - 1, i + 1)].id;
      else if (e.key === '[' || e.key === 'ArrowUp') next = STATES[Math.max(0, i - 1)].id;
      else if (e.key === 'n' || e.key === 'p') {
        const target = Math.max(0, Math.min(9, st.stage + (e.key === 'n' ? 1 : -1)));
        const s = STATES.find((x) => x.stage === target);
        if (s) next = s.id;
      } else if (e.key === 'Escape' && st.v.modal) next = STATES.filter((x) => x.stage === st.stage)[0].id;
      if (next) { e.preventDefault(); setId(next); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const groups = [{ n: 0, name: 'Setup' }, ...STAGES.map((name, i) => ({ n: i + 1, name }))];
  const pill = (on) => ({ font: 'inherit', fontSize: 12, padding: '3px 9px', borderRadius: 4, border: '1px solid var(--ink-4)', background: on ? 'var(--primary)' : 'transparent', color: on ? 'var(--ink-1)' : 'var(--fg-muted)', cursor: 'pointer', fontWeight: on ? 700 : 400, whiteSpace: 'nowrap' });
  const gokeys = st.go ? Object.entries(st.go) : [];
  return (
    <div style={{ display: 'flex', gap: 20, padding: 16, alignItems: 'flex-start', minWidth: 'max-content' }}>
      <div style={{ width: 230, flex: '0 0 230px', fontSize: 12, lineHeight: '18px', maxHeight: 'calc(100vh - 32px)', overflowY: 'auto' }}>
        {groups.map((g) => (
          <div key={g.n} style={{ marginBottom: 8 }}>
            <div style={{ color: 'var(--fg-faint)', fontWeight: 700 }}>{(g.n ? g.n + ' ' : '') + g.name}</div>
            {STATES.filter((s) => s.stage === g.n).map((s) => (
              <div key={s.id} onClick={() => setId(s.id)} style={{ cursor: 'pointer', padding: '0 6px', borderRadius: 3, background: s.id === id ? 'var(--primary)' : 'transparent', color: s.id === id ? 'var(--ink-1)' : 'var(--fg)', fontWeight: s.id === id ? 700 : 400 }}>{s.name}</div>
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          {SIZES.map(([c, r], i) => <button key={i} style={pill(size === i)} onClick={() => setSize(i)}>{c}×{r}</button>)}
          <button style={pill(unknown)} onClick={() => setUnknown(!unknown)}>unknown price</button>
          <a href="states.html" style={{ fontSize: 12, marginLeft: 8 }}>all states →</a>
        </div>
        <div style={{ fontSize: 12, color: 'var(--fg-muted)' }}><span style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>{st.name}</span> · {st.when}</div>
        <Screen st={st} cols={cols} rows={rows} unknown={unknown} />
        <div style={{ color: 'var(--fg-faint)', fontSize: 12 }}>
          ↑↓ or [ ] state · n / p stage{gokeys.length ? ' · ' + gokeys.map(([k, t]) => k + ' → ' + STATES.find((s) => s.id === t).name).join(' · ') : ''}
        </div>
      </div>
    </div>
  );
}

function Gallery() {
  const groups = [{ n: 0, name: 'Setup' }, ...STAGES.map((name, i) => ({ n: i + 1, name }))];
  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 32 }}>
      <div style={{ fontSize: 13, color: 'var(--fg-muted)' }}><span style={{ color: 'var(--primary)', fontWeight: 700 }}>hunches</span> · every screen state, 80×24 · {STATES.length} states · <a href="index.html">interactive →</a></div>
      {groups.map((g) => (
        <section key={g.n}>
          <div style={{ fontWeight: 700, color: 'var(--fg-strong)', marginBottom: 12 }}>{(g.n ? g.n + ' · ' : '') + g.name}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
            {STATES.filter((s) => s.stage === g.n).map((s) => (
              <div key={s.id} style={{ display: 'flex', flexDirection: 'column', gap: 6, width: 'calc(80ch * 0.5 + 8px)' }}>
                <div style={{ zoom: 0.5, boxShadow: '0 0 0 2px var(--ink-4)', borderRadius: 4, overflow: 'hidden', alignSelf: 'flex-start' }}><Screen st={s} cols={80} rows={24} chrome={false} /></div>
                <div style={{ fontSize: 12, lineHeight: '16px' }}><span style={{ color: 'var(--fg-strong)', fontWeight: 700 }}>{s.name}</span><br /><span style={{ color: 'var(--fg-muted)' }}>{s.when}</span></div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
