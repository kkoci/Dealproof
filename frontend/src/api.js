const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
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
// Fundraising diligence
// ---------------------------------------------------------------------------

/**
 * POST /api/fundraising/diligence/ingest
 * @param {object} body — { company_name, round_label?, metrics_records }
 */
export function ingestDiligence(body) {
  return request('/api/fundraising/diligence/ingest', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/fundraising/diligence/:id/evaluate
 * @param {string} id
 * @param {object} body — { claimed_values? }
 */
export function evaluateDiligence(id, body = {}) {
  return request(`/api/fundraising/diligence/${id}/evaluate`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/fundraising/diligence/:id
 * @param {string} id
 */
export function getDiligence(id) {
  return request(`/api/fundraising/diligence/${id}`)
}

/**
 * POST /api/fundraising/diligence/:id/investor-thresholds
 * @param {string} diligenceId
 * @param {object} body — InvestorThresholds payload
 * @returns {{ threshold_id, diligence_id, investor_id, disclosure_on_mismatch, created_at }}
 */
export function submitInvestorThresholds(diligenceId, body) {
  return request(`/api/fundraising/diligence/${diligenceId}/investor-thresholds`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/fundraising/diligence/:id/match/:threshold_id
 * @param {string} diligenceId
 * @param {string} thresholdId
 * @returns {MatchRunResponse}
 */
export function runMatch(diligenceId, thresholdId) {
  return request(`/api/fundraising/diligence/${diligenceId}/match/${thresholdId}`, {
    method: 'POST',
  })
}

/**
 * GET /api/fundraising/match/:match_id?viewer=founder|investor
 * @param {string} matchId
 * @param {'founder'|'investor'} viewer
 */
export function getMatch(matchId, viewer = 'investor') {
  return request(`/api/fundraising/match/${matchId}?viewer=${viewer}`)
}

// ---------------------------------------------------------------------------
// Fundraising negotiation (AN3 endpoint)
// ---------------------------------------------------------------------------

/**
 * POST /api/fundraising/negotiation/run
 * @param {object} body — FundraisingNegotiationRequest
 * @returns {Promise<FundraisingNegotiationCredential>}
 */
export function runFundraisingNegotiation(body) {
  return request('/api/fundraising/negotiation/run', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// Dev credential
// ---------------------------------------------------------------------------

/**
 * POST /api/devcred/ingest
 * @param {object} body — DevCredIngestRequest
 */
export function ingestDevCred(body) {
  return request('/api/devcred/ingest', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/devcred/:id/evaluate
 * @param {string} id
 * @param {object} body — DevCredEvaluateRequest
 */
export function evaluateDevCred(id, body = {}) {
  return request(`/api/devcred/${id}/evaluate`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/devcred/:id
 * @param {string} id
 */
export function getDevCred(id) {
  return request(`/api/devcred/${id}`)
}
