import React, { useState } from 'react';

const SPEED_OPTIONS = [
  { value: 1, label: '1× — Real-time' },
  { value: 3, label: '3× — Fast' },
  { value: 5, label: '5× — Demo mode' },
  { value: 10, label: '10× — Rapid' },
  { value: 20, label: '20× — Max speed' },
];

const API_BASE = 'http://localhost:8000';

export default function FaultControl({ activeProduce, allMeta, onFaultTriggered }) {
  const [speed, setSpeed] = useState(5);
  const [scope, setScope] = useState('active'); // 'active' or 'all'
  const [loading, setLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);

  const activeFault = allMeta?.[activeProduce]?.fault_active;
  const anyFault = allMeta && Object.values(allMeta).some(m => m.fault_active);

  const triggerFault = async () => {
    setLoading(true);
    try {
      const body = {
        speed: speed,
        produce_type: scope === 'active' ? activeProduce : null,
      };
      const res = await fetch(`${API_BASE}/api/trigger-fault`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to trigger fault');
      if (onFaultTriggered) onFaultTriggered();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const resetFault = async () => {
    setResetLoading(true);
    try {
      const body = {
        produce_type: scope === 'active' ? activeProduce : null,
      };
      const res = await fetch(`${API_BASE}/api/reset-fault`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to reset fault');
      if (onFaultTriggered) onFaultTriggered();
    } catch (e) {
      console.error(e);
    } finally {
      setResetLoading(false);
    }
  };

  return (
    <div className="fault-card glass-card">
      <div className="fault-title">🎮 Demo Control</div>

      <div className="fault-controls">
        {/* Speed selector */}
        <div className="speed-row">
          <span className="speed-label">Speed</span>
          <select
            id="fault-speed"
            className="speed-select"
            value={speed}
            onChange={e => setSpeed(Number(e.target.value))}
          >
            {SPEED_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* Scope selector */}
        <div className="fault-scope-row">
          <button
            id="scope-active"
            className={`scope-btn ${scope === 'active' ? 'active' : ''}`}
            onClick={() => setScope('active')}
          >
            Active Batch
          </button>
          <button
            id="scope-all"
            className={`scope-btn ${scope === 'all' ? 'active' : ''}`}
            onClick={() => setScope('all')}
          >
            All Batches
          </button>
        </div>

        {/* Trigger button */}
        <button
          id="trigger-fault-btn"
          className={`trigger-btn ${activeFault || (scope === 'all' && anyFault) ? 'triggered' : ''}`}
          onClick={triggerFault}
          disabled={loading}
        >
          {loading ? '⏳' : '⚡'} {loading ? 'Triggering…' : 'Trigger Cooling Fault'}
        </button>

        {/* Reset button */}
        <button
          id="reset-fault-btn"
          className="reset-btn"
          onClick={resetFault}
          disabled={resetLoading}
        >
          {resetLoading ? 'Resetting…' : '↺ Reset Fault'}
        </button>
      </div>

      {/* Active fault indicator */}
      {anyFault && (
        <div style={{ marginTop: 10, padding: '8px 10px', background: 'rgba(255,71,87,0.1)', borderRadius: 8, fontSize: '0.72rem', color: '#ff6b6b', border: '1px solid rgba(255,71,87,0.2)' }}>
          ⚠️ Cooling fault active — drift in progress
        </div>
      )}
    </div>
  );
}
