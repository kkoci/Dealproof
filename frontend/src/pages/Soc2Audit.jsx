import React, { useState } from 'react'
import { soc2Ingest, soc2Evaluate } from '../api.js'

// ── Constants ─────────────────────────────────────────────────────────────────

const SOURCES = [
  { value: 'iam_policies',      label: 'IAM Policies',       format: 'aws_iam_json' },
  { value: 'cloudtrail_config', label: 'CloudTrail Config',  format: 'aws_cloudtrail_json' },
  { value: 'bucket_policies',   label: 'S3 Bucket Policies', format: 'aws_s3_json' },
  { value: 'cloudwatch_alarms', label: 'CloudWatch Alarms',  format: 'aws_cloudwatch_json' },
]

const CONTROL_LABELS = {
  'CC6.1': 'MFA Enforcement',
  'CC6.2': 'Least Privilege',
  'CC6.3': 'Access Logging',
  'CC6.6': 'No Public S3',
  'CC7.1': 'CloudTrail Active',
  'CC7.2': 'Alerting Configured',
}

// AcmeCorp — all controls pass
const EXAMPLE_CONFIGS_GOOD = [
  {
    source: 'iam_policies',
    content: `{
  "Statement": [
    {
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "Bool": { "aws:MultiFactorAuthPresent": "false" }
      }
    }
  ]
}`,
  },
  {
    source: 'cloudtrail_config',
    content: `{
  "IsLogging": true,
  "Trail": { "Name": "prod-trail" },
  "EventSelectors": [
    { "IncludeManagementEvents": true, "ReadWriteType": "All" }
  ]
}`,
  },
  {
    source: 'bucket_policies',
    content: `{
  "BucketName": "private-data",
  "PublicAccessBlockConfiguration": {
    "BlockPublicAcls": true,
    "IgnorePublicAcls": true,
    "BlockPublicPolicy": true,
    "RestrictPublicBuckets": true
  }
}`,
  },
  {
    source: 'cloudwatch_alarms',
    content: `{
  "MetricAlarms": [
    { "AlarmName": "UnauthorizedAccess" },
    { "AlarmName": "RootAccountUsage" }
  ]
}`,
  },
]

// BadCorp — multiple controls fail
const EXAMPLE_CONFIGS_BAD = [
  {
    source: 'iam_policies',
    // No MFA condition (CC6.1 FAIL) + wildcard Allow (CC6.2 FAIL)
    content: `{
  "PolicyName": "AdminAccess",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*"
    }
  ]
}`,
  },
  {
    source: 'cloudtrail_config',
    // IsLogging false (CC7.1 FAIL), no event selectors (CC6.3 FAIL)
    content: `{
  "IsLogging": false,
  "Trail": { "Name": "dormant-trail" },
  "EventSelectors": []
}`,
  },
  {
    source: 'bucket_policies',
    // Public access not blocked (CC6.6 FAIL)
    content: `{
  "BucketName": "public-assets",
  "PublicAccessBlockConfiguration": {
    "BlockPublicAcls": false,
    "IgnorePublicAcls": false,
    "BlockPublicPolicy": false,
    "RestrictPublicBuckets": false
  }
}`,
  },
  {
    source: 'cloudwatch_alarms',
    // No alarms (CC7.2 FAIL)
    content: `{
  "MetricAlarms": []
}`,
  },
]

// ── Sub-components ────────────────────────────────────────────────────────────

function ControlCard({ finding }) {
  const pass = finding.effective
  return (
    <div className={`rounded-xl border p-4 ${
      pass
        ? 'border-emerald-800/50 bg-emerald-950/20'
        : 'border-red-800/50 bg-red-950/20'
    }`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <span className="text-xs font-mono text-gray-500">{finding.control_id}</span>
          <p className="text-sm font-semibold text-gray-200">
            {CONTROL_LABELS[finding.control_id] || finding.control_id}
          </p>
        </div>
        <span className={`flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
          pass
            ? 'bg-emerald-900/60 text-emerald-400 border border-emerald-700/40'
            : 'bg-red-900/60 text-red-400 border border-red-700/40'
        }`}>
          {pass ? (
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
          ) : (
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          )}
          {pass ? 'PASS' : 'FAIL'}
        </span>
      </div>

      {finding.qualitative_assessment && (
        <p className="text-xs text-gray-400 leading-relaxed mb-2">
          {finding.qualitative_assessment}
        </p>
      )}

      {finding.evidence_snippets?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {finding.evidence_snippets.slice(0, 2).map((e, i) => (
            <span key={i} className="inline-block px-2 py-0.5 rounded bg-gray-800/60 text-gray-500 text-xs font-mono truncate max-w-full">
              {e}
            </span>
          ))}
        </div>
      )}

      {finding.risk_notes && (
        <p className="text-xs text-gray-600 mt-2 italic leading-relaxed">
          {finding.risk_notes}
        </p>
      )}
    </div>
  )
}

function ConfigEntry({ entry, index, onChange, onRemove, disabled }) {
  const [jsonError, setJsonError] = useState(null)

  function handleContentChange(val) {
    try {
      JSON.parse(val)
      setJsonError(null)
    } catch {
      setJsonError('Invalid JSON')
    }
    onChange(index, 'content', val)
  }

  const sourceInfo = SOURCES.find(s => s.value === entry.source) || SOURCES[0]

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
        <select
          value={entry.source}
          onChange={e => onChange(index, 'source', e.target.value)}
          disabled={disabled}
          className="bg-transparent text-sm font-medium text-gray-300 focus:outline-none cursor-pointer disabled:opacity-50"
        >
          {SOURCES.map(s => (
            <option key={s.value} value={s.value} className="bg-gray-900">{s.label}</option>
          ))}
        </select>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-600">{sourceInfo.format}</span>
          <button
            type="button"
            onClick={() => onRemove(index)}
            disabled={disabled}
            className="text-gray-600 hover:text-red-400 transition-colors disabled:opacity-40"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      <div className="p-3">
        <textarea
          value={entry.content}
          onChange={e => handleContentChange(e.target.value)}
          disabled={disabled}
          rows={6}
          spellCheck={false}
          placeholder='{ "Statement": [...] }'
          className={`w-full px-3 py-2 rounded-lg bg-gray-950/60 border text-xs font-mono text-gray-300 placeholder-gray-700 focus:outline-none focus:ring-1 resize-y transition-all disabled:opacity-50 ${
            jsonError ? 'border-red-700/60 focus:ring-red-500/40' : 'border-gray-700/40 focus:ring-indigo-500/40'
          }`}
        />
        {jsonError && (
          <p className="text-xs text-red-400 mt-1">{jsonError}</p>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Soc2Audit() {
  const [orgName, setOrgName] = useState('')
  const [configs, setConfigs] = useState([{ source: 'iam_policies', content: '' }])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  function addConfig() {
    setConfigs(prev => [...prev, { source: 'iam_policies', content: '' }])
  }

  function removeConfig(index) {
    setConfigs(prev => prev.filter((_, i) => i !== index))
  }

  function updateConfig(index, key, value) {
    setConfigs(prev => prev.map((c, i) => i === index ? { ...c, [key]: value } : c))
  }

  function loadPreset(name, presetConfigs) {
    setOrgName(name)
    setConfigs(presetConfigs.map(c => ({ source: c.source, content: c.content })))
    setResult(null)
    setError(null)
  }

  async function handleRun(e) {
    e.preventDefault()
    setError(null)
    setResult(null)

    if (!orgName.trim()) {
      setError('Organisation name is required.')
      return
    }

    const parsedConfigs = []
    for (let i = 0; i < configs.length; i++) {
      const c = configs[i]
      if (!c.content.trim()) continue
      try {
        const content = JSON.parse(c.content)
        const sourceInfo = SOURCES.find(s => s.value === c.source)
        parsedConfigs.push({ source: c.source, format: sourceInfo.format, content })
      } catch {
        setError(`Config #${i + 1} (${c.source}): invalid JSON — fix before running.`)
        return
      }
    }

    if (parsedConfigs.length === 0) {
      setError('Add at least one config file.')
      return
    }

    setRunning(true)
    try {
      const ingestResult = await soc2Ingest({ org_name: orgName.trim(), configs: parsedConfigs })
      const evalResult = await soc2Evaluate(ingestResult.audit_id)
      setResult({ ingest: ingestResult, eval: evalResult })
    } catch (err) {
      setError(err.message || 'Audit failed. Is the backend running?')
    } finally {
      setRunning(false)
    }
  }

  const cred = result?.eval?.credential
  const passCount = cred?.control_findings?.filter(f => f.effective).length ?? 0
  const totalCount = cred?.control_findings?.length ?? 0

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span>dealproof</span>
            <span>/</span>
            <span className="text-gray-400">soc2-audit</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-2">
            SOC 2 Compliance Audit
          </h1>
          <p className="text-sm text-gray-500 mb-4">
            Paste your AWS config JSON into each box. Six CC6/CC7 controls are evaluated
            inside the Intel TDX TEE — raw configs never leave the enclave.
            A <span className="text-gray-400 font-mono">SOC2ControlCredential</span> with a TDX attestation quote is issued for your auditor.
          </p>

          {/* Real-world note */}
          <div className="rounded-lg border border-gray-800/50 bg-gray-900/30 px-4 py-3 mb-5">
            <p className="text-xs text-gray-500 font-medium mb-1.5">In a real workflow, run these AWS CLI commands and paste the output:</p>
            <div className="space-y-0.5 font-mono text-xs text-gray-600">
              <p><span className="text-indigo-500">IAM</span>      aws iam get-account-authorization-details</p>
              <p><span className="text-indigo-500">CloudTrail</span> aws cloudtrail describe-trails &amp;&amp; get-trail-status</p>
              <p><span className="text-indigo-500">S3</span>       aws s3api get-public-access-block --bucket &lt;name&gt;</p>
              <p><span className="text-indigo-500">Alarms</span>   aws cloudwatch describe-alarms</p>
            </div>
          </div>

          {/* Presets */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600">Try a preset:</span>
            <button
              type="button"
              onClick={() => loadPreset('AcmeCorp', EXAMPLE_CONFIGS_GOOD)}
              disabled={running}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-emerald-400 border border-emerald-700/40 hover:bg-emerald-900/20 transition-all disabled:opacity-40"
            >
              AcmeCorp (all pass)
            </button>
            <button
              type="button"
              onClick={() => loadPreset('BadCorp', EXAMPLE_CONFIGS_BAD)}
              disabled={running}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-red-400 border border-red-700/40 hover:bg-red-900/20 transition-all disabled:opacity-40"
            >
              BadCorp (multiple fail)
            </button>
          </div>
        </div>

        <form onSubmit={handleRun} className="space-y-6">

          {/* Org name */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-800/40 bg-gray-900/40">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                Organisation
              </h2>
            </div>
            <div className="px-5 py-4">
              <input
                type="text"
                value={orgName}
                onChange={e => setOrgName(e.target.value)}
                disabled={running}
                placeholder="AcmeCorp"
                className="w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all disabled:opacity-50"
              />
            </div>
          </div>

          {/* Config files */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-300">Config Files</h2>
              <button
                type="button"
                onClick={addConfig}
                disabled={running}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 border border-gray-700/40 hover:text-gray-200 hover:bg-gray-800/40 transition-all disabled:opacity-40"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add config
              </button>
            </div>

            {configs.map((c, i) => (
              <ConfigEntry
                key={i}
                entry={c}
                index={i}
                onChange={updateConfig}
                onRemove={removeConfig}
                disabled={running}
              />
            ))}

            {configs.length === 0 && (
              <div className="rounded-xl border border-dashed border-gray-700/40 py-8 text-center text-gray-600 text-sm">
                No configs added. Click "Add config" or "Load example".
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <p>{error}</p>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={running}
            className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60 hover:-translate-y-0.5 active:translate-y-0 disabled:translate-y-0 disabled:shadow-none"
          >
            {running ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Evaluating controls inside TEE...</span>
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Run SOC 2 Audit
              </>
            )}
          </button>
        </form>

        {/* Results */}
        {result && cred && (
          <div className="mt-10 space-y-6">

            {/* Overall banner */}
            <div className={`rounded-xl border p-5 ${
              cred.all_controls_effective
                ? 'border-emerald-700/50 bg-emerald-950/20'
                : 'border-red-700/50 bg-red-950/20'
            }`}>
              <div className="flex items-center justify-between gap-4 mb-3">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                    cred.all_controls_effective ? 'bg-emerald-700/40' : 'bg-red-700/40'
                  }`}>
                    {cred.all_controls_effective ? (
                      <svg className="w-5 h-5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                    )}
                  </div>
                  <div>
                    <p className={`text-base font-bold ${cred.all_controls_effective ? 'text-emerald-400' : 'text-red-400'}`}>
                      {cred.all_controls_effective ? 'All Controls Effective' : 'Controls Require Remediation'}
                    </p>
                    <p className="text-xs text-gray-500">{passCount}/{totalCount} controls passed · {cred.org_name}</p>
                  </div>
                </div>
                <span className="flex-shrink-0 px-3 py-1 rounded-full text-xs font-mono bg-gray-800/60 border border-gray-700/40 text-gray-400">
                  TEE attested
                </span>
              </div>
              <p className="text-sm text-gray-400 leading-relaxed">{cred.overall_assessment}</p>
            </div>

            {/* Control grid */}
            <div>
              <h3 className="text-sm font-semibold text-gray-300 mb-3">Control Findings</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {cred.control_findings.map(f => (
                  <ControlCard key={f.control_id} finding={f} />
                ))}
              </div>
            </div>

            {/* Material weaknesses */}
            {cred.material_weaknesses?.length > 0 && (
              <div className="rounded-xl border border-red-800/40 bg-red-950/10 px-4 py-3">
                <p className="text-sm font-semibold text-red-400 mb-1">Material Weaknesses</p>
                <div className="flex flex-wrap gap-2">
                  {cred.material_weaknesses.map(w => (
                    <span key={w} className="px-2 py-0.5 rounded text-xs font-mono bg-red-900/40 text-red-300 border border-red-800/40">{w}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Credential metadata */}
            <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
              <div className="px-5 py-3.5 border-b border-gray-800/40 bg-gray-900/40">
                <h3 className="text-sm font-semibold text-gray-300">Attestation Metadata</h3>
              </div>
              <div className="px-5 py-4 space-y-3 text-xs font-mono">
                {[
                  { label: 'audit_id',         value: result.eval.audit_id },
                  { label: 'corpus_root',       value: result.ingest.corpus_root },
                  { label: 'credential_hash',   value: cred.credential_hash },
                  { label: 'issued_at',         value: cred.issued_at },
                  { label: 'tee_quote',         value: result.eval.tee_quote },
                ].map(({ label, value }) => (
                  <div key={label} className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-3">
                    <span className="text-gray-600 flex-shrink-0 w-36">{label}</span>
                    <span className="text-gray-400 break-all">{value}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  )
}
