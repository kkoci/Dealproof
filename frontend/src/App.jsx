import React from 'react'
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom'
import Landing from './pages/offercheck/Landing.jsx'
import CandidateNew from './pages/offercheck/CandidateNew.jsx'
import CandidateSession from './pages/offercheck/CandidateSession.jsx'
import EmployerSession from './pages/offercheck/EmployerSession.jsx'
import CompanyRegister from './pages/offercheck/CompanyRegister.jsx'
import Dashboard from './pages/offercheck/Dashboard.jsx'
import Demo from './pages/offercheck/Demo.jsx'
import logo from './assets/icon.svg'

function NavBar() {
  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 bg-bg-surface border-b border-border"
      style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <Link to="/" className="flex items-center gap-2 group">
            <img src={logo} alt="Offer Check" className="h-6 w-6" />
            <span className="text-ink-primary font-semibold tracking-tight">
              Offer Check
            </span>
          </Link>

          <div className="flex items-center gap-1">
            <Link
              to="/offercheck/dashboard"
              className="px-3 py-1.5 rounded-md text-sm font-medium text-ink-secondary hover:text-ink-primary hover:bg-bg-elevated transition-colors"
            >
              Dashboard
            </Link>
            <a
              href={`${import.meta.env.VITE_BACKEND_URL || 'https://d31d2a226327eaf1da3c400fc137f21639555cf8-8000.dstack-pha-prod5.phala.network'}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-md text-sm font-medium text-ink-secondary hover:text-ink-primary hover:bg-bg-elevated transition-colors flex items-center gap-1.5"
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
      <h1 className="text-4xl font-bold text-ink-primary">404</h1>
      <p className="text-ink-secondary">Page not found.</p>
      <button
        onClick={() => navigate('/')}
        className="px-4 py-2 bg-teal hover:bg-teal-hover text-white rounded-lg transition-colors"
      >
        Go Home
      </button>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg-primary text-ink-primary">
        <NavBar />
        <div className="pt-14">
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/offercheck/new" element={<CandidateNew />} />
            <Route path="/offercheck/candidate/:sessionId" element={<CandidateSession />} />
            <Route path="/offercheck/employer/:sessionId" element={<EmployerSession />} />
            <Route path="/offercheck/company/register" element={<CompanyRegister />} />
            <Route path="/offercheck/dashboard" element={<Dashboard />} />
            <Route path="/offercheck/demo" element={<Demo />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
