import React, { useState, useEffect, useCallback, useRef } from 'react';
import './index.css';
import SensorChart from './components/SensorChart';
import RiskBadge from './components/RiskBadge';
import ValueMetric from './components/ValueMetric';
import BatchCard from './components/BatchCard';
import FaultControl from './components/FaultControl';
import CompressorHealth from './components/CompressorHealth';
import RecoveryExchange from './components/RecoveryExchange';

const API_BASE = 'http://localhost:8000';
const POLL_INTERVAL_MS = 4000;

const PRODUCE_ORDER = ['leafy_greens', 'tomatoes', 'potatoes'];

const PRODUCE_CONFIG = {
  leafy_greens: { display_name: 'Leafy Greens', emoji: '🥬', ideal_temp: 3.0, ideal_humidity: 92.0 },
  tomatoes: { display_name: 'Tomatoes', emoji: '🍅', ideal_temp: 13.0, ideal_humidity: 87.0 },
  potatoes: { display_name: 'Potatoes', emoji: '🥔', ideal_temp: 7.0, ideal_humidity: 87.0 },
};

const BATCH_META = {
  leafy_greens: { batch_weight_kg: 120, value_per_kg: 3.50 },
  tomatoes: { batch_weight_kg: 200, value_per_kg: 2.20 },
  potatoes: { batch_weight_kg: 350, value_per_kg: 0.90 },
};

/* ─── Core data hook ─────────────────────────────────────────────────────────── */
function useColdSense() {
  const [readings, setReadings] = useState({});
  const [predictions, setPredictions] = useState({});
  const [history, setHistory] = useState({});
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
      setLastUpdated(new Date());
      setConnected(true);
      setError(null);
    } catch (e) {
      setConnected(false);
      setError(e.message);
    }
  }, []);

  return { readings, predictions, history, lastUpdated, error, connected, fetchAll };
}

/* ─── Compressor data hook ───────────────────────────────────────────────────── */
function useCompressor() {
  const [compressor, setCompressor] = useState(null);

  const fetchCompressor = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/compressor`);
      if (res.ok) {
        const data = await res.json();
        setCompressor(data);
      }
    } catch (_) {
      // Non-critical — keep last known value
    }
  }, []);

  return { compressor, fetchCompressor };
}

/* ─── Recovery Exchange data hook ────────────────────────────────────────────── */
function useRecovery() {
  const [listings, setListings] = useState([]);
  const [buyers, setBuyers] = useState([]);

  const fetchRecovery = useCallback(async () => {
    try {
      const [listRes, buyerRes] = await Promise.all([
        fetch(`${API_BASE}/api/recovery/listings`),
        fetch(`${API_BASE}/api/recovery/buyers`),
      ]);
      if (listRes.ok) {
        const listData = await listRes.json();
        setListings(listData.listings ?? []);
      }
      if (buyerRes.ok) {
        const buyerData = await buyerRes.json();
        setBuyers(buyerData.buyers ?? []);
      }
    } catch (_) {
      // Non-critical
    }
  }, []);

  return { listings, buyers, fetchRecovery };
}

/* ─── Recovery buyer interest merge ──────────────────────────────────────────── */
/**
 * Merges buyer interest states from the active listings into the buyer list.
 * Uses the first active listing's buyer states for display.
 * If multiple listings are active, shows interest for the highest-risk one.
 */
function mergeBuyerInterest(buyers, listings) {
  if (!listings || listings.length === 0) return buyers;
  // Pick the highest-risk listing (first, since API returns sorted by remaining_hours)
  const topListing = listings[0];
  if (!topListing || !topListing.buyer_states) return buyers;
  return buyers.map(b => ({
    ...b,
    interest_status: topListing.buyer_states?.[b.buyer_id] ?? b.interest_status ?? 'PENDING',
  }));
}

/* ─── App ───────────────────────────────────────────────────────────────────── */
export default function App() {
  const [activeProduce, setActiveProduce] = useState('leafy_greens');
  const { readings, predictions, history, lastUpdated, error, connected, fetchAll } = useColdSense();
  const { compressor, fetchCompressor } = useCompressor();
  const { listings, buyers, fetchRecovery } = useRecovery();
  const intervalRef = useRef(null);
  const [faultBanner, setFaultBanner] = useState(null);

  const poll = useCallback(() => {
    fetchAll(activeProduce);
    fetchCompressor();
    fetchRecovery();
  }, [fetchAll, activeProduce, fetchCompressor, fetchRecovery]);

  useEffect(() => {
    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [poll]);

  const handleFaultTriggered = useCallback(() => {
    setFaultBanner('COOLING FAULT INJECTED — DRIFT IN PROGRESS');
    setTimeout(() => setFaultBanner(null), 6000);
    setTimeout(poll, 600);
  }, [poll]);

  const activeReading = readings[activeProduce] ?? {};
  const activePred = predictions[activeProduce] ?? {};
  const activeHistory = history[activeProduce] ?? [];
  const doorOpen = activeReading.door_open_event === 1;

  // Enrich buyers with interest status from the most critical listing's buyer data
  // The backend returns buyer states via /recovery/listings/{batch_id}/buyers
  // For simplicity, the recovery hook fetches the general buyers list,
  // and the listing objects contain listing_status. Interest per-buyer is
  // fetched via the listing endpoint when needed.
  // Display buyers from the base buyer dataset; interest column shows from listing.
  const enrichedBuyers = buyers;

  return (
    <div className="app">

      {/* ── Top bar ── */}
      <header className="topbar" role="banner">
        <div className="topbar-logo">
          <div className="logo-icon" aria-hidden="true">❄</div>
          <div>
            <div className="logo-text">ColdSense</div>
            <div className="logo-subtitle">Cold-Storage Monitor</div>
          </div>
        </div>

        <div className="topbar-right">
          <div className={`live-badge ${connected ? '' : 'offline'}`} role="status">
            <div className="live-dot" />
            {connected ? 'LIVE' : 'OFFLINE'}
          </div>
          <div className="last-updated" aria-label="Last updated">
            {lastUpdated ? lastUpdated.toLocaleTimeString() : '--:--:--'}
          </div>
        </div>
      </header>

      {/* ── Fault banner ── */}
      {faultBanner && (
        <div className="fault-banner" role="alert">
          ⚡ {faultBanner}
        </div>
      )}

      {/* ── Error state ── */}
      {error && !connected && (
        <div className="error-overlay" role="alert">
          <div className="error-icon">⚡</div>
          <div className="error-title">Backend Unreachable</div>
          <div className="error-msg">
            Cannot reach <code>localhost:8000</code>. Start the backend:
            <br /><br />
            <code>cd coldsense/backend</code>
            <br />
            <code>uvicorn main:app --port 8000</code>
          </div>
        </div>
      )}

      {/* ── Main layout ── */}
      {!error && (
        <main className="main-layout">

          {/* ══ LEFT PANEL ══ */}
          <aside className="left-panel">

            {/* Batch selector */}
            <div className="hmi-card">
              <div className="hmi-section-title">Produce Batches</div>
              <div className="batch-tabs" role="tablist">
                {PRODUCE_ORDER.map(pt => {
                  const pred = predictions[pt];
                  const risk = pred?.risk_level ?? 'Safe';
                  const reading = readings[pt] ?? {};
                  const isFault = reading.fault_active;
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
                        <div className="tab-batch-id">{reading.batch_id ?? '---'}</div>
                      </div>
                      <div className={`tab-risk-dot ${risk}`} title={risk} />
                    </button>
                  );
                })}
              </div>
            </div>

            {/* All-batch overview */}
            <div className="hmi-card">
              <div className="hmi-section-title">All Batches</div>
              <div className="quick-stats">
                {PRODUCE_ORDER.map(pt => {
                  const pred = predictions[pt];
                  const risk = pred?.risk_level ?? '—';
                  const hours = pred?.hours_remaining;
                  return (
                    <div key={pt} className="quick-stat">
                      <span className="qs-label">
                        {PRODUCE_CONFIG[pt].emoji} {PRODUCE_CONFIG[pt].display_name}
                      </span>
                      <span className={`qs-value ${risk}`}>
                        {hours != null ? `${hours.toFixed(0)}h` : '—'} · {risk}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── Compressor Health (new — uses existing free left-panel space) ── */}
            <CompressorHealth data={compressor} />

          </aside>

          {/* ══ CENTER PANEL ══ */}
          <section className="center-panel" aria-label="Sensor readings">

            {/* Telemetry tiles */}
            <div className="readings-row">
              <div className={`reading-card temp-card`}>
                <div className="reading-label">Temperature</div>
                <div className="reading-value temp">
                  {activeReading.temperature?.toFixed(1) ?? '--'}
                  <span className="reading-unit">°C</span>
                </div>
                <div className="reading-sub">
                  Ideal {PRODUCE_CONFIG[activeProduce].ideal_temp}°C
                </div>
              </div>

              <div className="reading-card hum-card">
                <div className="reading-label">Humidity</div>
                <div className="reading-value hum">
                  {activeReading.humidity?.toFixed(1) ?? '--'}
                  <span className="reading-unit">%</span>
                </div>
                <div className="reading-sub">
                  Ideal {PRODUCE_CONFIG[activeProduce].ideal_humidity}%
                </div>
              </div>

              <div className={`reading-card door-card ${doorOpen ? 'door-open' : ''}`}>
                <div className="reading-label">Door Status</div>
                <div className={`reading-value ${doorOpen ? 'door-open' : 'door-closed'}`}>
                  {doorOpen ? 'OPEN' : 'SEALED'}
                </div>
                <div className="reading-sub">
                  {doorOpen ? 'Heat ingress event' : 'Secure'}
                </div>
              </div>
            </div>

            {/* Trend chart */}
            <SensorChart
              history={activeHistory}
              produceConfig={PRODUCE_CONFIG[activeProduce]}
            />

            {/* ── Risk Stock / Recovery Exchange (new — below chart, existing center space) ── */}
            <RecoveryExchange
              listings={listings}
              buyers={enrichedBuyers}
            />

          </section>

          {/* ══ RIGHT PANEL ══ */}
          <aside className="right-panel" aria-label="Prediction and controls">
            <RiskBadge prediction={activePred} />
            <ValueMetric value={activePred.value} />
            <BatchCard metadata={{
              ...activeReading,
              display_name: PRODUCE_CONFIG[activeProduce].display_name,
              emoji: PRODUCE_CONFIG[activeProduce].emoji,
              batch_weight_kg: BATCH_META[activeProduce].batch_weight_kg,
              value_per_kg: BATCH_META[activeProduce].value_per_kg,
            }} />
            <FaultControl
              activeProduce={activeProduce}
              allMeta={readings}
              onFaultTriggered={handleFaultTriggered}
            />
          </aside>

        </main>
      )}

      {/* ── Status bar ── */}
      <footer className="statusbar">
        <div className="statusbar-left">
          <div className="sb-item">
            <div className={`sb-dot ${connected ? '' : 'offline'}`} />
            {connected ? 'localhost:8000 — connected' : 'disconnected'}
          </div>
          <div className="sb-item">
            Model: GBR · Poll: {POLL_INTERVAL_MS / 1000}s
          </div>
          <div className="sb-item">
            Active: {PRODUCE_CONFIG[activeProduce].emoji} {PRODUCE_CONFIG[activeProduce].display_name}
          </div>
        </div>
        <div>ColdSense · Technova 2026 · Simulation</div>
      </footer>

    </div>
  );
}
