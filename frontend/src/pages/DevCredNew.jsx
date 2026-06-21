import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ingestDevCred, evaluateDevCred } from '../api.js'

// ---------------------------------------------------------------------------
// Mode toggle
// ---------------------------------------------------------------------------

function ModeToggle({ mode, onChange }) {
  return (
    <div className="flex gap-1 p-1 bg-gray-900/60 rounded-lg border border-gray-700/40 mb-6 w-fit">
      {['github', 'direct'].map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => onChange(m)}
          className={`px-4 py-1.5 rounded-md text-xs font-semibold transition-colors ${
            mode === m
              ? 'bg-teal-700 text-white'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          {m === 'github' ? 'GitHub Token' : 'Direct JSON'}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Repo list builder (github mode)
// ---------------------------------------------------------------------------

function RepoList({ repos, onChange }) {
  function add() {
    onChange([...repos, ''])
  }
  function update(i, val) {
    const next = [...repos]
    next[i] = val
    onChange(next)
  }
  function remove(i) {
    onChange(repos.filter((_, idx) => idx !== i))
  }

  return (
    <div className="space-y-2">
      {repos.map((r, i) => (
        <div key={i} className="flex gap-2">
          <input
            type="text"
            value={r}
            onChange={(e) => update(i, e.target.value)}
            placeholder="owner/repo-name"
            className="flex-1 bg-gray-900/60 border border-gray-700/60 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-teal-500/60 font-mono"
          />
          <button
            type="button"
            onClick={() => remove(i)}
            className="px-2 py-2 rounded-lg border border-gray-700/40 text-gray-500 hover:text-red-400 hover:border-red-800/40 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="text-xs text-teal-500 hover:text-teal-400 transition-colors flex items-center gap-1"
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add repo
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main form
// ---------------------------------------------------------------------------

const INPUT_CLASS =
  'w-full bg-gray-900/60 border border-gray-700/60 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-teal-500/60 focus:ring-1 focus:ring-teal-500/30 transition-colors font-mono'

export default function DevCredNew() {
  const navigate = useNavigate()

  const [mode, setMode] = useState('github')
  const [handle, setHandle] = useState('')
  const [token, setToken] = useState('')
  const [repos, setRepos] = useState([''])
  const [rawJson, setRawJson] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)

    let ingestPayload
    const credId = `devcred-${Date.now()}`

    if (mode === 'github') {
      if (!token.trim()) {
        setError('GitHub token is required.')
        return
      }
      const filteredRepos = repos.filter((r) => r.trim())
      if (!filteredRepos.length) {
        setError('Add at least one repository.')
        return
      }
      ingestPayload = {
        credential_id: credId,
        developer_handle: handle.trim(),
        mode: 'github',
        github_token: token.trim(),
        repos: filteredRepos,
      }
    } else {
      let commits
      try {
        commits = JSON.parse(rawJson)
        if (!Array.isArray(commits)) throw new Error('Must be a JSON array of commits')
      } catch (err) {
        setError(`Invalid JSON: ${err.message}`)
        return
      }
      if (!commits.length) {
        setError('Commits array is empty.')
        return
      }
      ingestPayload = {
        credential_id: credId,
        developer_handle: handle.trim() || 'anonymous',
        mode: 'direct',
        commits,
      }
    }

    setLoading(true)
    try {
      await ingestDevCred(ingestPayload)
      const cred = await evaluateDevCred(credId, {})
      navigate(`/devcred/${credId}`, { state: { cred } })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-2xl mx-auto">

        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span className="text-teal-400">Dev Credential</span>
            <span>/</span>
            <span className="text-gray-400">new</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-2">
            Generate Dev Credential
          </h1>
          <p className="text-sm text-gray-500 leading-relaxed">
            The enclave reads your commit history and issues a
            SeniorDevCredential. Your token is used once and discarded.
            Repo names and employer names never appear in the credential.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">

          <ModeToggle mode={mode} onChange={setMode} />

          {/* Developer handle */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">
              Developer Handle <span className="text-gray-600">(GitHub username)</span>
            </label>
            <input
              type="text"
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              placeholder="your-github-username"
              className={INPUT_CLASS}
            />
            <p className="text-[10px] text-gray-600 mt-1">
              Appears in the credential — no email or employer name stored.
            </p>
          </div>

          {mode === 'github' ? (
            <>
              {/* Token */}
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">
                  GitHub Token <span className="text-gray-600">(read-only scope)</span>
                </label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="ghp_…"
                  autoComplete="off"
                  className={INPUT_CLASS}
                />
                <p className="text-[10px] text-gray-600 mt-1">
                  Used in-memory to fetch commits. Never written to disk or database.
                </p>
              </div>

              {/* Repos */}
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-2">
                  Repositories
                </label>
                <RepoList repos={repos} onChange={setRepos} />
              </div>
            </>
          ) : (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Commits JSON
              </label>
              <textarea
                rows={10}
                value={rawJson}
                onChange={(e) => setRawJson(e.target.value)}
                placeholder={`[\n  {\n    "sha": "abc123",\n    "author": "alice",\n    "timestamp": "2024-03-15T10:00:00Z",\n    "message": "feat: add OAuth flow",\n    "diff_stat": {"additions": 150, "deletions": 20},\n    "changed_files": ["src/auth.go", "tests/auth_test.go"]\n  }\n]`}
                className={INPUT_CLASS + ' resize-y font-mono text-xs'}
              />
              <p className="text-[10px] text-gray-600 mt-1">
                Each commit needs: sha, timestamp (ISO 8601), message, diff_stat, changed_files.
              </p>
            </div>
          )}

          {/* TEE note */}
          <div className="rounded-xl border border-teal-800/30 bg-teal-950/10 px-4 py-3 text-xs text-teal-300 leading-relaxed">
            Analysis runs inside Intel TDX. The issued credential contains only computed
            ratios — not employer names, repo names, or file paths.
          </div>

          {error && (
            <div className="rounded-lg bg-red-950/40 border border-red-800/50 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-teal-600 hover:bg-teal-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Analysing inside TEE…</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>Analyse &amp; Issue Credential</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
