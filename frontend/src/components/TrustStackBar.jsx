import React from 'react'

const LAYERS = [
  { key: 'tdx',     label: 'TDX ENCLAVE',     detail: 'Hardware secured' },
  { key: 'dcap',    label: 'DCAP ATTESTATION', detail: 'Code verified'   },
  { key: 'memory',  label: 'CONTEXTO MEMORY',  detail: 'Attested inputs' },
  { key: 'picreds', label: 'πCREDS CONDUCT',   detail: 'Conduct attested' },
]

/**
 * active: { tdx, dcap, memory, picreds } — each bool
 * hash: short hex string to display below the bar
 */
export default function TrustStackBar({ active = {}, hash }) {
  return (
    <div className="bg-dp-surface border border-dp-border rounded-lg p-4 space-y-2.5">
      <p className="text-xs font-mono tracking-widest text-dp-muted uppercase mb-3">Trust Stack</p>

      {LAYERS.map((layer) => {
        const on = !!active[layer.key]
        return (
          <div key={layer.key}>
            <div className="flex items-center justify-between mb-1">
              <span className={`text-xs font-mono tracking-wide ${on ? 'text-dp-teal' : 'text-dp-muted'}`}>
                {layer.label}
              </span>
              <span className={`text-xs font-mono ${on ? 'text-dp-teal' : 'text-dp-muted/50'}`}>
                {on ? 'VERIFIED' : 'PENDING'}
              </span>
            </div>
            <div className="h-1.5 bg-dp-border rounded-full overflow-hidden">
              <div
                className="h-full bg-dp-teal rounded-full"
                style={{
                  width: on ? '100%' : '0%',
                  transition: 'width 600ms ease',
                }}
              />
            </div>
          </div>
        )
      })}

      {hash && (
        <div className="pt-2 border-t border-dp-border">
          <p className="text-xs font-mono text-dp-muted mb-1">TDX QUOTE</p>
          <p className="text-xs font-mono text-dp-text break-all">
            {hash.slice(0, 20)}…{hash.slice(-8)}
          </p>
        </div>
      )}
    </div>
  )
}
