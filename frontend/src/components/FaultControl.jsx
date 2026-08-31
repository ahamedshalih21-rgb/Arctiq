import React, { useState } from 'react';

const SPEED_OPTIONS = [
  { value: 1,  label: '1×  — Real-time' },
  { value: 3,  label: '3×  — Fast' },
  { value: 5,  label: '5×  — Demo' },
  { value: 10, label: '10× — Rapid' },
  { value: 20, label: '20× — Max' },
];

const API_BASE = 'http://localhost:8000';

export default function FaultControl({ activeProduce, allMeta, onFaultTriggered }) {
  const [speed,        setSpeed]        = useState(5);
  const [scope,        setScope]        = useState('active');
  const [loading,      setLoading]      = useState(false);
  const [resetLoading, setResetLoading] = useState(false);

  const activeFault = allMeta?.[activeProduce]?.fault_active;
  const anyFault    = allMeta && Object.values(allMeta).some(m => m.fault_active);

  const triggerFault = async () => {
    setLoading(true);
    try {
      await fetch(`${API_BASE}/api/trigger-fault`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed, produce_type: scope === 'active' ? activeProduce : null }),
      });
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
      await fetch(`${API_BASE}/api/reset-fault`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ produce_type: scope === 'active' ? activeProduce : null }),
      });
      if (onFaultTriggered) onFaultTriggered();
    } catch (e) {
      console.error(e);
    } finally {
      setResetLoading(false);
    }
  };

  return (
    <div className="fault-card">
      <div className="fault-title">Demo Control</div>

      <div className="fault-controls">
        {/* Speed */}
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

        {/* Scope toggle */}
        <div className="fault-scope-row">
          <button
            id="scope-active"
            className={`scope-btn ${scope === 'active' ? 'active' : ''}`}
            onClick={() => setScope('active')}
          >
            Active
          </button>
          <button
            id="scope-all"
            className={`scope-btn ${scope === 'all' ? 'active' : ''}`}
            onClick={() => setScope('all')}
          >
            All
          </button>
        </div>

        {/* Trigger */}
        <button
          id="trigger-fault-btn"
          className={`trigger-btn ${activeFault || (scope === 'all' && anyFault) ? 'triggered' : ''}`}
          onClick={triggerFault}
          disabled={loading}
        >
          ⚡ {loading ? 'INJECTING…' : 'TRIGGER FAULT'}
        </button>

        {/* Reset */}
        <button
          id="reset-fault-btn"
          className="reset-btn"
          onClick={resetFault}
          disabled={resetLoading}
        >
          {resetLoading ? 'RESETTING…' : '↺  RESET FAULT'}
        </button>

        {anyFault && (
          <div className="fault-active-indicator">
            ⚠ Cooling fault active
          </div>
        )}
      </div>
    </div>
  );
}
