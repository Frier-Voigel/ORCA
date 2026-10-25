import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom/client';

function App() {
  const [state, setState] = useState(null);

  useEffect(() => {
    const fetchState = async () => {
      try {
        const res = await fetch('/api/state');
        if (res.ok) {
          const data = await res.json();
          setState(data);
        }
      } catch (e) {
        console.error("Failed to fetch state:", e);
      }
    };
    fetchState();
    const interval = setInterval(fetchState, 1000);
    return () => clearInterval(interval);
  }, []);

  if (!state) {
    return (
      <div style={{ padding: 32, background: '#0b0f19', color: '#fff', minHeight: '100vh', fontFamily: 'sans-serif' }}>
        <h2>Connecting to Cascading Failure Predictor API...</h2>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, background: '#0b0f19', color: '#fff', minHeight: '100vh', fontFamily: 'sans-serif' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
        <h1>Cascading Failure Predictor</h1>
        <div>Tick: {state.tick} | Health: {Math.round(state.system_health * 100)}%</div>
      </header>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        <div style={{ background: '#111827', padding: 20, borderRadius: 12 }}>
          <h3>Services ({state.metrics?.length || 0})</h3>
          <ul>
            {state.metrics?.map(m => (
              <li key={m.service} style={{ margin: '8px 0', color: m.status === 'healthy' ? '#10b981' : '#ef4444' }}>
                {m.service}: {m.status} (latency: {Math.round(m.latency_p95_ms)}ms, error_rate: {(m.error_rate * 100).toFixed(1)}%)
              </li>
            ))}
          </ul>
        </div>
        <div style={{ background: '#111827', padding: 20, borderRadius: 12 }}>
          <h3>Root Cause</h3>
          {state.root_cause?.candidates?.length ? (
            <div>
              <p style={{ color: '#ef4444', fontWeight: 'bold' }}>{state.root_cause.candidates[0].service}</p>
              <p style={{ fontSize: 13, color: '#9ca3af' }}>{state.root_cause.candidates[0].explanation}</p>
            </div>
          ) : (
            <p style={{ color: '#10b981' }}>Healthy</p>
          )}
        </div>
      </div>
    </div>
  );
}

const rootElem = document.getElementById('root');
if (rootElem) {
  ReactDOM.createRoot(rootElem).render(<App />);
}
