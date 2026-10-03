import React, { useState, useEffect, useCallback, useRef } from 'react';
import './index.css';
import EnergyPanel from './components/EnergyPanel';
import SensorChart from './components/SensorChart';
import RiskBadge from './components/RiskBadge';
import ValueMetric from './components/ValueMetric';
import BatchCard from './components/BatchCard';
import FaultControl from './components/FaultControl';
import CompressorHealth from './components/CompressorHealth';
import RecoveryExchange from './components/RecoveryExchange';
import SmartSellPanel from './components/SmartSellPanel';
import RateSettingsModal from './components/RateSettingsModal';

const API_BASE = 'http://localhost:8000';
const POLL_INTERVAL_MS = 4000;

const PRODUCE_ORDER = ['spinach', 'tomato', 'strawberry'];

const PRODUCE_CONFIG = {
  spinach:    { display_name: 'Spinach',    ideal_temp: 2.0,  ideal_humidity: 95.0 },
  tomato:     { display_name: 'Tomato',     ideal_temp: 13.0, ideal_humidity: 88.0 },
  strawberry: { display_name: 'Strawberry', ideal_temp: 1.5,  ideal_humidity: 92.0 },
  // Backward compatibility
  leafy_greens: { display_name: 'Spinach',    ideal_temp: 2.0,  ideal_humidity: 95.0 },
  tomatoes:     { display_name: 'Tomato',     ideal_temp: 13.0, ideal_humidity: 88.0 },
  milk:         { display_name: 'Strawberry', ideal_temp: 1.5,  ideal_humidity: 92.0 },
};

const BATCH_META = {
  spinach:    { batch_weight_kg: 120, value_per_kg: 3.50 },
  tomato:     { batch_weight_kg: 200, value_per_kg: 2.20 },
  strawberry: { batch_weight_kg: 80,  value_per_kg: 5.50 },
  // Backward compatibility
  leafy_greens: { batch_weight_kg: 120, value_per_kg: 3.50 },
  tomatoes:     { batch_weight_kg: 200, value_per_kg: 2.20 },
  milk:         { batch_weight_kg: 80,  value_per_kg: 5.50 },
};

/* ─── Core data hook ─────────────────────────────────────────────────────────── */
function useArctiq() {
  const [readings, setReadings]         = useState({});
  const [predictions, setPredictions]   = useState({});
  const [history, setHistory]           = useState({});
  const [lastUpdated, setLastUpdated]   = useState(null);
  const [error, setError]               = useState(null);
  const [connected, setConnected]       = useState(false);

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
      // Non-critical
    }
  }, []);

  return { compressor, fetchCompressor };
}

/* ─── Recovery Exchange data hook ────────────────────────────────────────────── */
function useRecovery() {
  const [listings, setListings] = useState([]);
  const [buyers, setBuyers]     = useState([]);

  const fetchRecovery = useCallback(async () => {
    try {
      const [listRes, buyerRes] = await Promise.all([
        fetch(`${API_BASE}/api/recovery/listings`),
        fetch(`${API_BASE}/api/recovery/buyers`),
      ]);
      if (listRes.ok) {
        const d = await listRes.json();
        setListings(d.listings ?? []);
      }
      if (buyerRes.ok) {
        const d = await buyerRes.json();
        setBuyers(d.buyers ?? []);
      }
    } catch (_) {
      // Non-critical
    }
  }, []);

  return { listings, buyers, fetchRecovery };
}

/* ─── SmartSell data hook ────────────────────────────────────────────────────── */
function useSmartSell() {
  const [recommendations, setRecommendations] = useState([]);
  const [ssLoading, setSsLoading]             = useState(true);

  const fetchSmartSell = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/smartsell/recommendations`);
      if (res.ok) {
        const data = await res.json();
        setRecommendations(data.recommendations ?? []);
        setSsLoading(false);
      }
    } catch (_) {
      // Non-critical
    }
  }, []);

  return { recommendations, ssLoading, fetchSmartSell };
}

/* ─── Energy data hook ────────────────────────────────────────────────────────── */
function useEnergy() {
  const [energyData, setEnergyData] = useState(null);

  const fetchEnergy = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/power`);
      if (res.ok) {
        const data = await res.json();
        setEnergyData(data);
      }
    } catch (_) {
      // Non-critical: EnergyPanel has graceful calculation fallback
    }
  }, []);

  return { energyData, fetchEnergy };
}

/* ─── Unified Inventory Row ─────────────────────────────────────────────────── */
const STAGE_COLOR_MAP = {
  LOW:           'var(--risk-safe)',
  MEDIUM:        'var(--risk-watch)',
  HIGH:          'var(--risk-high)',
  SAFE:          'var(--risk-safe)',
  MONITOR:       'var(--risk-safe)',
  WATCH:         'var(--risk-watch)',
  EARLY_WARNING: 'var(--risk-watch)',
  HIGH_RISK:     'var(--risk-high)',
  CRITICAL:      'var(--risk-critical)',
  SPOILED:       'var(--color-neutral-600)',
};

function InventoryBatchCard({ pt, predictions, readings, ssRec, isActive, onSelect }) {
  const pred    = predictions[pt] ?? {};
  const reading = readings[pt]    ?? {};
  const stage   = pred.warning_stage ?? (pred.risk_level ?? 'SAFE');
  const stageColor = STAGE_COLOR_MAP[stage] ?? 'var(--color-neutral-400)';
  const cfg        = PRODUCE_CONFIG[pt];
  const priColor = {
    'SELL NOW':  'var(--risk-critical)',
    'SELL SOON': 'var(--risk-high)',
    'PROMOTE':   'var(--risk-watch)',
    'HOLD':      'var(--risk-safe)',
  }[ssRec?.priority_action] || 'var(--color-neutral-400)';

  return (
    <div
      className={`inv-card ${isActive ? 'active' : ''}`}
      onClick={() => onSelect(pt)}
      role="button"
      tabIndex={0}
    >
      <div className="inv-card-header">
        <div>
          <div className="inv-card-name">{cfg.display_name}</div>
          <div className="inv-card-id">{reading.batch_id ?? pt}</div>
        </div>
        <div className="inv-card-status" style={{ color: stageColor, borderColor: stageColor }}>
          {stage.replace('_', ' ')}
        </div>
      </div>

      <div className="inv-card-metrics">
        <div className="inv-metric-col">
          <span className="inv-metric-lbl">MODEL HRS</span>
          <span className="inv-metric-val">
            {pred.model_hours_remaining != null
              ? `${pred.model_hours_remaining.toFixed(1)}h`
              : (pred.hours_remaining != null ? `${pred.hours_remaining.toFixed(1)}h` : '--')}
          </span>
        </div>
        <div className="inv-metric-col">
          <span className="inv-metric-lbl">PROJ. HRS</span>
          <span className="inv-metric-val" style={{ color: 'var(--risk-watch)' }}>
            {pred.projected_risk_horizon_hours != null
              ? `~${Math.round(pred.projected_risk_horizon_hours)}h`
              : '--'}
          </span>
        </div>
        <div className="inv-metric-col">
          <span className="inv-metric-lbl">STOCK / DEMAND</span>
          <span className="inv-metric-val">
            {reading.quantity_kg != null ? `${Math.round(reading.quantity_kg)}kg` : '--'}
            <span className="inv-metric-sub"> · {reading.demand_score != null ? `${Math.round(reading.demand_score)}/100` : '--'}</span>
          </span>
        </div>
      </div>

      <div className="inv-card-footer">
        <div className="inv-pri-pill" style={{ color: priColor, borderColor: priColor }}>
          {ssRec ? `${ssRec.priority_action} (${Math.round(ssRec.sell_priority_score)}/100)` : 'HOLD'}
        </div>
        <div className="inv-price-tag">
          {ssRec ? `Rs ${Math.round(ssRec.recommended_price_per_kg)}/kg` : '--'}
        </div>
      </div>
    </div>
  );
}

/* ─── App ───────────────────────────────────────────────────────────────────── */
export default function App() {
  const [activeProduce, setActiveProduce] = useState('spinach');
  const [electricityRate, setElectricityRate] = useState(() => {
    const saved = localStorage.getItem('electricityRate');
    return saved ? Number(saved) : 8.0;
  });
  const [isRateModalOpen, setIsRateModalOpen] = useState(false);

  const handleSaveRate = (newRate) => {
    setElectricityRate(newRate);
    localStorage.setItem('electricityRate', String(newRate));
  };

  const { readings, predictions, history, lastUpdated, error, connected, fetchAll } = useArctiq();
  const { compressor, fetchCompressor } = useCompressor();
  const { energyData, fetchEnergy } = useEnergy();
  const { listings, buyers, fetchRecovery } = useRecovery();
  const { recommendations, ssLoading, fetchSmartSell } = useSmartSell();
  const intervalRef = useRef(null);
  const [faultBanner, setFaultBanner] = useState(null);

  const poll = useCallback(() => {
    fetchAll(activeProduce);
    fetchCompressor();
    fetchEnergy();
    fetchRecovery();
    fetchSmartSell();
  }, [fetchAll, activeProduce, fetchCompressor, fetchEnergy, fetchRecovery, fetchSmartSell]);

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

  const activeReading = readings[activeProduce]     ?? {};
  const activePred    = predictions[activeProduce]  ?? {};
  const activeHistory = history[activeProduce]      ?? [];
  const doorOpen      = activeReading.door_open_event === 1;

  // Build a map of produce_type -> smartsell recommendation for inventory table
  const ssMap = {};
  recommendations.forEach(r => { ssMap[r.produce_type] = r; });

  return (
    <div className="app">

      {/* Top bar */}
      <header className="topbar" role="banner">
        <div className="topbar-logo">
          <div className="logo-icon" aria-hidden="true">AQ</div>
          <div>
            <div className="logo-text">Arctiq</div>
            <div className="logo-subtitle">Smart Inventory + Pricing System</div>
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

      {/* Fault banner */}
      {faultBanner && (
        <div className="fault-banner" role="alert">
          {faultBanner}
        </div>
      )}

      {/* Error state */}
      {error && !connected && (
        <div className="error-overlay" role="alert">
          <div className="error-icon">!</div>
          <div className="error-title">Backend Unreachable</div>
          <div className="error-msg">
            Cannot reach <code>localhost:8000</code>. Start the backend:
            <br /><br />
            <code>cd Arctiq/backend</code>
            <br />
            <code>uvicorn main:app --port 8000</code>
          </div>
        </div>
      )}

      {/* Main layout */}
      {!error && (
        <main className="main-layout">

          {/* ── 1. MAIN HERO SECTION (Left/Center, grid-column: 1 / 3): Energy Consumption & Optimization ── */}
          <section className="energy-section" aria-label="Energy Consumption & Optimization">
            <EnergyPanel
              energyData={energyData}
              compressorData={compressor}
              electricityRate={electricityRate}
              onOpenRateSettings={() => setIsRateModalOpen(true)}
            />

            {/* Chamber Telemetry Tiles */}
            <div className="readings-row">
              <div className="reading-card temp-card">
                <div className="reading-label">Temperature</div>
                <div className="reading-value temp">
                  {activeReading.temperature?.toFixed(1) ?? '--'}
                  <span className="reading-unit"> °C</span>
                </div>
                <div className="reading-sub">
                  Ideal {PRODUCE_CONFIG[activeProduce].ideal_temp} °C
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

            {/* Sensor Trend Chart */}
            <SensorChart
              history={activeHistory}
              produceConfig={PRODUCE_CONFIG[activeProduce]}
            />

            {/* Dynamic Pricing / SmartSell Panel */}
            <SmartSellPanel
              recommendations={recommendations}
              loading={ssLoading && recommendations.length === 0}
            />

            {/* Risk Stock Recovery Exchange */}
            <RecoveryExchange
              listings={listings}
              buyers={buyers}
            />
          </section>

          {/* ── 2. RIGHT COLUMN: Compressor Health (TOP) + Spoilage Risk & Produce Status (BELOW) ── */}
          <aside className="right-section" aria-label="Compressor & Spoilage Intelligence">
            {/* Top of Right Column: Compressor Health Score & Degradation Analytics */}
            <CompressorHealth data={compressor} />

            {/* Below Compressor Health: Produce Batches & Shelf Life */}
            <div className="hmi-card">
              <div className="hmi-section-title">Produce Batches & Shelf Life</div>
              <div className="inv-list">
                {PRODUCE_ORDER.map(pt => (
                  <InventoryBatchCard
                    key={pt}
                    pt={pt}
                    predictions={predictions}
                    readings={readings}
                    ssRec={ssMap[pt]}
                    isActive={pt === activeProduce}
                    onSelect={setActiveProduce}
                  />
                ))}
              </div>
              <div className="inv-note">
                PyTorch LSTM model (360-min window). Click batch for live chamber telemetry.
              </div>
            </div>

            {/* Active Produce Risk Badge */}
            <RiskBadge prediction={activePred} />

            {/* Financial Value Metric */}
            <ValueMetric value={activePred.value} />

            {/* Batch Cards */}
            <BatchCard metadata={{
              ...activeReading,
              display_name:    PRODUCE_CONFIG[activeProduce].display_name,
              batch_weight_kg: BATCH_META[activeProduce].batch_weight_kg,
              value_per_kg:    BATCH_META[activeProduce].value_per_kg,
            }} />

            {/* Fault Control */}
            <FaultControl
              activeProduce={activeProduce}
              allMeta={readings}
              onFaultTriggered={handleFaultTriggered}
            />
          </aside>

        </main>
      )}

      {/* Status bar */}
      <footer className="statusbar">
        <div className="statusbar-left">
          <div className="sb-item">
            <div className={`sb-dot ${connected ? '' : 'offline'}`} />
            {connected ? 'localhost:8000 — connected' : 'disconnected'}
          </div>
          <div className="sb-item">
            Model: PyTorch LSTM (360-min window) · Poll: {POLL_INTERVAL_MS / 1000}s
          </div>
          <div className="sb-item">
            Active: {PRODUCE_CONFIG[activeProduce].display_name}
          </div>
        </div>
        <div>Arctiq · Technova 2026 · Simulation</div>
      </footer>

      {/* Electricity Rate Tariff Modal */}
      <RateSettingsModal
        isOpen={isRateModalOpen}
        onClose={() => setIsRateModalOpen(false)}
        currentRate={electricityRate}
        onSaveRate={handleSaveRate}
      />

    </div>
  );
}
