import React, { useState, useEffect, useCallback, useRef } from 'react';
import './index.css';
import SensorChart from './components/SensorChart';
import RiskBadge from './components/RiskBadge';
import ValueMetric from './components/ValueMetric';
import BatchCard from './components/BatchCard';
import FaultControl from './components/FaultControl';

const API_BASE = 'http://localhost:8000';
const POLL_INTERVAL_MS = 4000;  // poll every 4s

const PRODUCE_ORDER = ['leafy_greens', 'tomatoes', 'potatoes'];

const PRODUCE_CONFIG = {
  leafy_greens: { display_name: 'Leafy Greens', emoji: '🥬', ideal_temp: 3.0, ideal_humidity: 92.0 },
  tomatoes:     { display_name: 'Tomatoes',     emoji: '🍅', ideal_temp: 13.0, ideal_humidity: 87.0 },
  potatoes:     { display_name: 'Potatoes',     emoji: '🥔', ideal_temp: 7.0,  ideal_humidity: 87.0 },
};

function useColdSense() {
  const [readings, setReadings] = useState({});
  const [predictions, setPredictions] = useState({});
  const [history, setHistory] = useState({});
  const [metadata, setMetadata] = useState({});
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [connected, setConnected] = useState(false);

  const fetchAll = useCallback(async (activeProduce) => {
    try {
      const [readRes, predRes, histRes] = await Promise.all([
        fetch(`${API_BASE}/api/readings`),
        fetch(`${API_BASE}/api/prediction`),
        fetch(`${API_BASE}/api/history/${activeProduce}?n=40`),
      ]);

      if (!readRes.ok || !predRes.ok) throw new Error('Backend error');

      const [readData, predData, histData] = await Promise.all([
        readRes.json(),
        predRes.json(),
        histRes.json(),
      ]);

      setReadings(readData);
      setPredictions(predData);
      setHistory(prev => ({ ...prev, [activeProduce]: histData.readings ?? [] }));

      // Extract metadata from readings
      const meta = {};
      for (const [pt, r] of Object.entries(readData)) {
        meta[pt] = {
          batch_id: r.batch_id,
          display_name: r.display_name,
          emoji: r.emoji,
          fault_active: r.fault_active,
          fault_speed: r.fault_speed,
          storage_since: r.storage_since,
          batch_weight_kg: PRODUCE_CONFIG[pt] ? undefined : 100,
          value_per_kg: PRODUCE_CONFIG[pt] ? undefined : 1,
        };
        // Merge value from prediction
        if (predData[pt]?.value) {
          meta[pt].batch_weight_kg = predData[pt].value.total_batch_value_usd /
            (PRODUCE_CONFIG[pt] ? 1 : 1); // approximate
        }
      }
      setMetadata(prev => ({ ...prev, ...meta }));

      setLastUpdated(new Date());
      setConnected(true);
      setError(null);
    } catch (e) {
      setConnected(false);
      setError(e.message);
    }
  }, []);

  return { readings, predictions, history, metadata, lastUpdated, error, connected, fetchAll };
}

export default function App() {
  const [activeProduce, setActiveProduce] = useState('leafy_greens');
  const { readings, predictions, history, metadata, lastUpdated, error, connected, fetchAll } = useColdSense();
  const intervalRef = useRef(null);
  const [faultBanner, setFaultBanner] = useState(null);

  const poll = useCallback(() => {
    fetchAll(activeProduce);
  }, [fetchAll, activeProduce]);

  useEffect(() => {
    poll(); // immediate fetch on mount / produce change
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [poll]);

  const handleFaultTriggered = useCallback(() => {
    setFaultBanner('⚡ Cooling fault injected — watching for drift…');
    setTimeout(() => setFaultBanner(null), 6000);
    // Force immediate repoll
    setTimeout(poll, 500);
  }, [poll]);

  const activeReading = readings[activeProduce] ?? {};
  const activePred = predictions[activeProduce] ?? {};
  const activeHistory = history[activeProduce] ?? [];
  const activeMeta = {
    ...(metadata[activeProduce] ?? {}),
    ...(activeReading ?? {}),
    batch_weight_kg: activePred.value?.total_batch_value_usd
      ? undefined
      : undefined,
    display_name: PRODUCE_CONFIG[activeProduce]?.display_name,
    emoji: PRODUCE_CONFIG[activeProduce]?.emoji,
  };

  const doorStatus = activeReading.door_open_event === 1;

  return (
    <div className="app">
      {/* ── Top Bar ── */}
      <header className="topbar" role="banner">
        <div className="topbar-logo">
          <div className="logo-icon" aria-hidden="true">❄️</div>
          <div>
            <div className="logo-text">ColdSense</div>
            <div className="logo-subtitle">Cold-Storage Intelligence</div>
          </div>
        </div>

        <div className="topbar-right">
          {connected ? (
            <div className="live-badge" role="status" aria-live="polite">
              <div className="live-dot" />
              LIVE
            </div>
          ) : (
            <div className="live-badge" style={{ color: 'var(--coral)', borderColor: 'rgba(255,71,87,0.3)', background: 'rgba(255,71,87,0.08)' }}>
              <div className="live-dot" style={{ background: 'var(--coral)', animation: 'none' }} />
              OFFLINE
            </div>
          )}
          <div className="last-updated" aria-label="Last updated">
            {lastUpdated ? lastUpdated.toLocaleTimeString() : '--:--:--'}
          </div>
        </div>
      </header>

      {/* ── Fault Banner ── */}
      {faultBanner && (
        <div className="fault-banner" role="alert">
          {faultBanner}
        </div>
      )}

      {/* ── Error state ── */}
      {error && !connected && (
        <div className="error-overlay" role="alert">
          <div className="error-icon">⚡</div>
          <div className="error-title">Backend Not Reachable</div>
          <div className="error-msg">
            Cannot connect to <code>localhost:8000</code>. Please start the backend:
            <br /><br />
            <code>cd backend &amp;&amp; uvicorn main:app --port 8000</code>
          </div>
        </div>
      )}

      {/* ── Main Layout ── */}
      {!error && (
        <main className="main-layout">
          {/* ── LEFT PANEL ── */}
          <aside className="left-panel">
            <div className="glass-card">
              <div className="panel-title">Produce Batches</div>
              <div className="batch-tabs" role="tablist">
                {PRODUCE_ORDER.map(pt => {
                  const pred = predictions[pt];
                  const risk = pred?.risk_level ?? 'Safe';
                  const meta = readings[pt] ?? {};
                  const isFault = meta.fault_active;
                  return (
                    <button
                      key={pt}
                      id={`tab-${pt}`}
                      role="tab"
                      aria-selected={activeProduce === pt}
                      className={`batch-tab ${activeProduce === pt ? 'active' : ''} ${isFault ? 'fault-tab' : ''}`}
                      onClick={() => setActiveProduce(pt)}
                    >
                      <span className="tab-emoji">{PRODUCE_CONFIG[pt].emoji}</span>
                      <div className="tab-info">
                        <div className="tab-name">{PRODUCE_CONFIG[pt].display_name}</div>
                        <div className="tab-batch-id">{meta.batch_id ?? '...'}</div>
                      </div>
                      <div className={`tab-risk-dot ${risk}`} title={risk} />
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Quick all-batches overview */}
            <div className="glass-card">
              <div className="panel-title">All Batches</div>
              <div className="quick-stats">
                {PRODUCE_ORDER.map((pt, i) => {
                  const pred = predictions[pt];
                  const risk = pred?.risk_level ?? '—';
                  const hours = pred?.hours_remaining;
                  return (
                    <React.Fragment key={pt}>
                      {i > 0 && <div className="qs-divider" />}
                      <div className="quick-stat">
                        <span className="qs-label">{PRODUCE_CONFIG[pt].emoji} {PRODUCE_CONFIG[pt].display_name}</span>
                        <span className="qs-value" style={{
                          color: risk === 'Safe' ? 'var(--safe)' : risk === 'Watch' ? 'var(--watch)' : 'var(--critical)'
                        }}>
                          {hours != null ? `${hours.toFixed(0)}h` : '—'} · {risk}
                        </span>
                      </div>
                    </React.Fragment>
                  );
                })}
              </div>
            </div>
          </aside>

          {/* ── CENTER PANEL ── */}
          <section className="center-panel" aria-label="Sensor readings for active batch">
            {/* Current readings row */}
            <div className="readings-row">
              <div className="reading-card glass-card temp-card">
                <div className="reading-label">Temperature</div>
                <div className="reading-value temp">
                  {activeReading.temperature?.toFixed(1) ?? '--'}
                  <span className="reading-unit">°C</span>
                </div>
                <div className="reading-sub">
                  Ideal: {PRODUCE_CONFIG[activeProduce]?.ideal_temp}°C
                </div>
              </div>

              <div className="reading-card glass-card hum-card">
                <div className="reading-label">Humidity</div>
                <div className="reading-value hum">
                  {activeReading.humidity?.toFixed(1) ?? '--'}
                  <span className="reading-unit">%</span>
                </div>
                <div className="reading-sub">
                  Ideal: {PRODUCE_CONFIG[activeProduce]?.ideal_humidity}%
                </div>
              </div>

              <div className="reading-card glass-card door-card">
                <div className="reading-label">Door Status</div>
                <div className={`reading-value ${doorStatus ? 'door-open' : 'door-closed'}`}>
                  {doorStatus ? '🔓' : '🔒'}
                </div>
                <div className="reading-sub">
                  {doorStatus ? 'Door open — heat ingress' : 'Door sealed'}
                </div>
              </div>
            </div>

            {/* Trend chart */}
            <SensorChart
              history={activeHistory}
              produceConfig={PRODUCE_CONFIG[activeProduce]}
            />
          </section>

          {/* ── RIGHT PANEL ── */}
          <aside className="right-panel" aria-label="Prediction and controls">
            <RiskBadge prediction={activePred} />
            <ValueMetric value={activePred.value} />
            <BatchCard metadata={{
              ...activeReading,
              batch_id: activeReading.batch_id,
              display_name: PRODUCE_CONFIG[activeProduce].display_name,
              emoji: PRODUCE_CONFIG[activeProduce].emoji,
              batch_weight_kg: (() => {
                if (activeProduce === 'leafy_greens') return 120;
                if (activeProduce === 'tomatoes') return 200;
                return 350;
              })(),
              value_per_kg: (() => {
                if (activeProduce === 'leafy_greens') return 3.50;
                if (activeProduce === 'tomatoes') return 2.20;
                return 0.90;
              })(),
            }} />
            <FaultControl
              activeProduce={activeProduce}
              allMeta={readings}
              onFaultTriggered={handleFaultTriggered}
            />
          </aside>
        </main>
      )}

      {/* ── Status Bar ── */}
      <footer className="statusbar">
        <div className="statusbar-left">
          <div className="sb-item">
            <div className={`sb-dot ${connected ? '' : 'offline'}`} />
            Backend: {connected ? 'localhost:8000' : 'disconnected'}
          </div>
          <div className="sb-item">
            Model: GBR (pre-trained) · Poll: {POLL_INTERVAL_MS / 1000}s
          </div>
          <div className="sb-item">
            Active: {PRODUCE_CONFIG[activeProduce]?.emoji} {PRODUCE_CONFIG[activeProduce]?.display_name}
          </div>
        </div>
        <div>
          ColdSense · Technova 2026 · Simulation Mode
        </div>
      </footer>
    </div>
  );
}
