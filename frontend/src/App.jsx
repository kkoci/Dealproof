import React from 'react'
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom'
import FundraisingLanding from './pages/FundraisingLanding.jsx'
import DiligenceLanding from './pages/DiligenceLanding.jsx'
import DiligenceNew from './pages/DiligenceNew.jsx'
import DiligenceView from './pages/DiligenceView.jsx'
import InvestorThresholdForm from './pages/InvestorThresholdForm.jsx'
import MatchResultView from './pages/MatchResultView.jsx'

function NavBar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-gray-950/90 backdrop-blur-md border-b border-gray-800/60">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-900/50">
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <span className="text-gray-100 font-semibold tracking-tight group-hover:text-white transition-colors">
              Fundraising Credential
            </span>
          </Link>

          <div className="flex items-center gap-1">
            <a
              href={`${import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-md text-sm font-medium text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 transition-colors flex items-center gap-1.5"
            >
              API Docs
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </nav>
  )
}

function NotFound() {
  const navigate = useNavigate()
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4">
      <h1 className="text-4xl font-bold text-gray-200">404</h1>
      <p className="text-gray-400">Page not found.</p>
      <button
        onClick={() => navigate('/')}
        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
      >
        Go Home
      </button>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <NavBar />
        <div className="pt-14">
          <Routes>
            <Route path="/" element={<FundraisingLanding />} />
            <Route path="/fundraising" element={<DiligenceLanding />} />
            <Route path="/fundraising/new" element={<DiligenceNew />} />
            <Route path="/fundraising/diligence/:id" element={<DiligenceView />} />
            <Route path="/fundraising/match/new" element={<InvestorThresholdForm />} />
            <Route path="/fundraising/match/:id" element={<MatchResultView />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
