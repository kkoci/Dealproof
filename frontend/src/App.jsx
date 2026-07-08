import React from 'react'
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom'
import Landing from './pages/offercheck/Landing.jsx'
import CandidateNew from './pages/offercheck/CandidateNew.jsx'
import CandidateSession from './pages/offercheck/CandidateSession.jsx'
import EmployerSession from './pages/offercheck/EmployerSession.jsx'
import CompanyRegister from './pages/offercheck/CompanyRegister.jsx'
import Dashboard from './pages/offercheck/Dashboard.jsx'
import Demo from './pages/offercheck/Demo.jsx'

function NavBar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-gray-950/90 backdrop-blur-md border-b border-gray-800/60">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center shadow-lg shadow-emerald-900/50">
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <span className="text-gray-100 font-semibold tracking-tight group-hover:text-white transition-colors">
              Offer Check
            </span>
          </Link>

          <div className="flex items-center gap-1">
            <Link
              to="/offercheck/dashboard"
              className="px-3 py-1.5 rounded-md text-sm font-medium text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 transition-colors"
            >
              Dashboard
            </Link>
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
        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors"
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
