import React from 'react'

function RadialRing({ value, size = 72 }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const filled = circ * Math.min(1, Math.max(0, value))
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e1e24" strokeWidth={6} />
      <circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke="#00d4aa" strokeWidth={6}
        strokeDasharray={`${filled} ${circ - filled}`}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 800ms ease' }}
      />
    </svg>
  )
}

function NullRateBar({ column, rate }) {
  const pct = Math.min(100, (rate * 100).toFixed(1))
  const color = rate > 0.15 ? 'bg-dp-red' : rate > 0.05 ? 'bg-dp-amber' : 'bg-dp-teal'
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-dp-muted w-24 truncate shrink-0">{column}</span>
      <div className="flex-1 h-1.5 bg-dp-border rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%`, transition: 'width 600ms ease' }} />
      </div>
      <span className="text-xs font-mono text-dp-muted w-10 text-right shrink-0">{pct}%</span>
    </div>
  )
}

export default function QualityPanel({ report, attested }) {
  if (!report) return null

  const completeness = report.completeness_score ?? 0
  const schema = report.schema_consistent
  const verdict = report.overall_quality || 'unknown'
  const nullRates = report.null_rates || {}
  const topNulls = Object.entries(nullRates)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  const verdictColor = verdict === 'high' ? 'text-dp-teal' : verdict === 'medium' ? 'text-dp-amber' : 'text-dp-red'
  const borderColor = attested ? 'border-dp-teal/50' : 'border-dp-amber/40'

  return (
    <div className={`bg-dp-surface border ${borderColor} rounded-lg p-4 space-y-4`}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-mono tracking-widest text-dp-muted uppercase">Data Quality</p>
        <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${
          attested ? 'text-dp-teal border-dp-teal/40 bg-dp-teal/10' : 'text-dp-amber border-dp-amber/40 bg-dp-amber/10'
        }`}>
          {attested ? 'ATTESTED' : 'UNATTESTED'}
        </span>
      </div>

      {/* Completeness ring */}
      <div className="flex items-center gap-4">
        <div className="relative">
          <RadialRing value={completeness} />
          <span className="absolute inset-0 flex items-center justify-center text-sm font-mono text-dp-text rotate-90" style={{ transform: 'rotate(90deg)' }}>
            {(completeness * 100).toFixed(0)}%
          </span>
        </div>
        <div>
          <p className="text-xs font-mono text-dp-muted mb-0.5">COMPLETENESS</p>
          <p className={`text-sm font-mono font-semibold ${verdictColor} uppercase`}>{verdict}</p>
          {report.summary && (
            <p className="text-xs text-dp-muted mt-1 leading-relaxed">{report.summary}</p>
          )}
        </div>
      </div>

      {/* Schema consistency */}
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${schema ? 'bg-dp-teal' : 'bg-dp-red'}`} />
        <span className="text-xs font-mono text-dp-muted">SCHEMA</span>
        <span className={`text-xs font-mono ${schema ? 'text-dp-teal' : 'text-dp-red'}`}>
          {schema ? 'CONSISTENT' : 'VIOLATIONS'}
        </span>
      </div>

      {/* Null rates */}
      {topNulls.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-mono text-dp-muted uppercase tracking-wider">Null Rates</p>
          {topNulls.map(([col, rate]) => (
            <NullRateBar key={col} column={col} rate={rate} />
          ))}
        </div>
      )}

      {/* Quality issues */}
      {report.quality_issues?.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-mono text-dp-muted uppercase tracking-wider">Issues</p>
          {report.quality_issues.slice(0, 3).map((issue, i) => (
            <p key={i} className="text-xs text-dp-amber font-mono">↳ {issue}</p>
          ))}
        </div>
      )}
    </div>
  )
}
