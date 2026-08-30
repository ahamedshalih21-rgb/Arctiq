import React, { useCallback, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div className="label">Reading #{label}</div>
      {payload.map((p, i) => (
        <div key={i} className={p.dataKey === 'temperature' ? 'value-temp' : 'value-hum'}>
          {p.dataKey === 'temperature' ? '🌡️' : '💧'} {p.name}: {Number(p.value).toFixed(1)}{p.dataKey === 'temperature' ? '°C' : '%'}
        </div>
      ))}
    </div>
  );
};

export default function SensorChart({ history, produceConfig }) {
  const data = history.map((r, i) => ({
    index: i + 1,
    temperature: r.temperature,
    humidity: r.humidity,
  }));

  return (
    <div className="chart-card glass-card">
      <div className="chart-header">
        <div className="chart-title">
          {produceConfig?.emoji} Sensor Trend — {produceConfig?.display_name}
        </div>
        <div className="chart-legend">
          <div className="legend-item">
            <div className="legend-line" style={{ background: '#ff6b6b' }} />
            Temperature (°C)
          </div>
          <div className="legend-item">
            <div className="legend-line" style={{ background: '#4ecdc4' }} />
            Humidity (%)
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="index"
            tick={{ fontSize: 10 }}
            interval={Math.floor(data.length / 6)}
            tickFormatter={(v) => `t-${data.length - v}`}
          />
          <YAxis yAxisId="temp" domain={['auto', 'auto']} tick={{ fontSize: 10 }} />
          <YAxis yAxisId="hum"  orientation="right" domain={[50, 100]} tick={{ fontSize: 10 }} />
          <Tooltip content={<CustomTooltip />} />

          {/* Ideal temperature reference */}
          {produceConfig?.ideal_temp && (
            <ReferenceLine
              yAxisId="temp"
              y={produceConfig.ideal_temp}
              stroke="rgba(255,107,107,0.3)"
              strokeDasharray="4 4"
              label={{ value: 'ideal T', fill: 'rgba(255,107,107,0.5)', fontSize: 10, position: 'insideTopLeft' }}
            />
          )}

          <Line
            yAxisId="temp"
            type="monotone"
            dataKey="temperature"
            name="Temperature"
            stroke="#ff6b6b"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#ff6b6b' }}
            isAnimationActive={false}
          />
          <Line
            yAxisId="hum"
            type="monotone"
            dataKey="humidity"
            name="Humidity"
            stroke="#4ecdc4"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#4ecdc4' }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
