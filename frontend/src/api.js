const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  // `...options` must come first — if it were spread after `headers`, a
  // caller-supplied options.headers (e.g. createAgentRailDeal's X-Demo-Token)
  // would replace this whole headers object outright (object spread: later
  // keys win), silently dropping Content-Type and making fetch send the JSON
  // body as text/plain, which the backend can't parse (422).
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!res.ok) {
    let errorMessage = `HTTP ${res.status}: ${res.statusText}`
    try {
      const errBody = await res.json()
      if (errBody.detail) {
        errorMessage = typeof errBody.detail === 'string'
          ? errBody.detail
          : JSON.stringify(errBody.detail)
      }
    } catch {
      // ignore parse errors
    }
    throw new Error(errorMessage)
  }

  return res.json()
}

/**
 * GET /health
 * @returns {{ status: string, tee_mode: string }}
 */
export function getHealth() {
  return request('/health')
}

/**
 * POST /api/deals/run — create and negotiate in one call
 * @param {object} body
 * @returns {Promise<DealResult>}
 */
export function runDeal(body) {
  return request('/api/deals/run', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/deals — create deal only (status=pending)
 * @param {object} body
 * @returns {Promise<DealStatus>}
 */
export function createDeal(body) {
  return request('/api/deals', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/deals/:id/negotiate
 * @param {string} id
 * @returns {Promise<DealResult>}
 */
export function negotiateDeal(id) {
  return request(`/api/deals/${id}/negotiate`, { method: 'POST' })
}

/**
 * GET /api/deals/:id/status
 * @param {string} id
 * @returns {Promise<DealStatus>}
 */
export function getDealStatus(id) {
  return request(`/api/deals/${id}/status`)
}

/**
 * GET /api/deals/:id/attestation
 * @param {string} id
 * @returns {Promise<{ deal_id: string, attestation: string }>}
 */
export function getDealAttestation(id) {
  return request(`/api/deals/${id}/attestation`)
}

/**
 * GET /api/deals/:id/dcap-verify
 * @param {string} id
 * @returns {Promise<DCAPVerification>}
 */
export function getDcapVerification(id) {
  return request(`/api/deals/${id}/dcap-verify`)
}

/**
 * GET /api/deals/:id/verification
 * @param {string} id
 * @returns {Promise<{ deal_id: string, verification: object }>}
 */
export function getDealVerification(id) {
  return request(`/api/deals/${id}/verification`)
}

// ---------------------------------------------------------------------------
// Agent Rail — B2B procurement deal room (Phase 2)
// ---------------------------------------------------------------------------

/**
 * POST /api/agentrail/deals — sealed buyer + supplier parameters, starts negotiation.
 * Gated (Phase 3): requires a valid magic-link demo token, sent as X-Demo-Token —
 * this is the only Agent Rail endpoint that calls Claude, so it's the only one gated.
 * @param {{buyer: object, supplier: object, max_rounds?: number}} body
 * @param {string} demoToken
 * @returns {Promise<{deal_id: string, status: string}>}
 */
export function createAgentRailDeal(body, demoToken) {
  const headers = {}
  if (demoToken) headers['X-Demo-Token'] = demoToken
  return request('/api/agentrail/deals', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/agentrail/deals/:id — poll live negotiation status + transcript
 * @param {string} id
 * @returns {Promise<object>}
 */
export function getAgentRailDeal(id) {
  return request(`/api/agentrail/deals/${id}`)
}

/**
 * GET /api/agentrail/deals/:id/attest — DCAP attestation receipt (only once agreed)
 * @param {string} id
 * @returns {Promise<object>}
 */
export function getAgentRailAttestation(id) {
  return request(`/api/agentrail/deals/${id}/attest`)
}
