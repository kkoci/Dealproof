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

async function requestMultipart(path, formData) {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, { method: 'POST', body: formData })

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
// Offer Check (vertical/hr-offer-check) — /api/offercheck/*
// ---------------------------------------------------------------------------

/**
 * POST /api/offercheck/sessions — candidate submits competing offer + ask
 * @param {object} body { competing_offer, candidate_ask }
 * @returns {Promise<object>} CandidateSubmitResponse
 */
export function offercheckSubmit(body) {
  return request('/api/offercheck/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/employer/band — one-time private band submission
 * @param {string} sessionId
 * @param {object} body { employer_token, band_min, band_mid, band_max }
 * @returns {Promise<object>} EmployerBandResponse
 */
export function offercheckSetEmployerBand(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/band`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/employer/move
 * @param {string} sessionId
 * @param {object} body { token, move, value }
 * @returns {Promise<object>} SessionView
 */
export function offercheckEmployerMove(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/move`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/candidate/move
 * @param {string} sessionId
 * @param {object} body { token, move, value }
 * @returns {Promise<object>} SessionView
 */
export function offercheckCandidateMove(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/candidate/move`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/offercheck/sessions/:id?token=... — viewer-scoped status poll
 * @param {string} sessionId
 * @param {string} token
 * @returns {Promise<object>} SessionView
 */
export function offercheckGetSession(sessionId, token) {
  return request(`/api/offercheck/sessions/${sessionId}?token=${encodeURIComponent(token)}`)
}

/**
 * POST /api/offercheck/parse-offer-letter — upload a PDF, get draft fields to review
 * @param {File} file
 * @returns {Promise<object>} OfferLetterExtraction { competing_offer, confidence, notes }
 */
export function offercheckParseOfferLetter(file) {
  const formData = new FormData()
  formData.append('file', file)
  return requestMultipart('/api/offercheck/parse-offer-letter', formData)
}

/**
 * GET /api/offercheck/sessions/:id/attest?token=... — TDX attestation receipt (terminal states only)
 * @param {string} sessionId
 * @param {string} token
 * @returns {Promise<object>} AttestationReceipt
 */
export function offercheckGetAttestation(sessionId, token) {
  return request(`/api/offercheck/sessions/${sessionId}/attest?token=${encodeURIComponent(token)}`)
}

/**
 * POST /api/offercheck/sessions/:id/start-agentic — run CandidateAgent vs EmployerAgent to completion
 * @param {string} sessionId
 * @param {string} token
 * @returns {Promise<object>} AgenticResult
 */
export function offercheckStartAgentic(sessionId, token) {
  return request(`/api/offercheck/sessions/${sessionId}/start-agentic`, {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

/**
 * GET /api/offercheck/sessions/:id/dcap-verify?token=... — parsed DCAP quote fields
 * @param {string} sessionId
 * @param {string} token
 * @returns {Promise<object>} DcapVerification
 */
export function offercheckGetDcapVerify(sessionId, token) {
  return request(`/api/offercheck/sessions/${sessionId}/dcap-verify?token=${encodeURIComponent(token)}`)
}

/**
 * GET /api/offercheck/sessions/:id/credential — either ?token=... or an X-API-Key header
 * @param {string} sessionId
 * @param {{ token?: string, apiKey?: string }} auth
 * @returns {Promise<object>} CredentialResponse
 */
export function offercheckGetCredential(sessionId, { token, apiKey } = {}) {
  if (apiKey) {
    return request(`/api/offercheck/sessions/${sessionId}/credential`, { headers: { 'X-API-Key': apiKey } })
  }
  return request(`/api/offercheck/sessions/${sessionId}/credential?token=${encodeURIComponent(token)}`)
}

/**
 * POST /api/offercheck/company/register
 * @param {{ name: string, hires_per_year?: number }} body
 * @returns {Promise<object>} CompanyRegisterResponse — api_key is shown exactly once
 */
export function offercheckRegisterCompany(body) {
  return request('/api/offercheck/company/register', { method: 'POST', body: JSON.stringify(body) })
}

/**
 * POST /api/offercheck/company/ats-connect
 * @param {string} apiKey
 * @param {{ provider: string, api_key: string }} body
 * @returns {Promise<object>} AtsConnectResponse
 */
export function offercheckConnectAts(apiKey, body) {
  return request('/api/offercheck/company/ats-connect', {
    method: 'POST',
    headers: { 'X-API-Key': apiKey },
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/offercheck/company/sessions
 * @param {string} apiKey
 * @returns {Promise<object>} CompanySessionsResponse
 */
export function offercheckListCompanySessions(apiKey) {
  return request('/api/offercheck/company/sessions', { headers: { 'X-API-Key': apiKey } })
}

/**
 * POST /api/offercheck/company/verify/bulk
 * @param {string} apiKey
 * @param {{ verifications: object[] }} body
 * @returns {Promise<object>} BulkVerifyResponse
 */
export function offercheckBulkVerify(apiKey, body) {
  return request('/api/offercheck/company/verify/bulk', {
    method: 'POST',
    headers: { 'X-API-Key': apiKey },
    body: JSON.stringify(body),
  })
}
