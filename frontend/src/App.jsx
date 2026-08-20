import React from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import Landing from './pages/offercheck/Landing.jsx'
import CandidateNew from './pages/offercheck/CandidateNew.jsx'
import CandidateJoin from './pages/offercheck/CandidateJoin.jsx'
import CandidateSession from './pages/offercheck/CandidateSession.jsx'
import EmployerSession from './pages/offercheck/EmployerSession.jsx'
import CompanyRegister from './pages/offercheck/CompanyRegister.jsx'
import CompanyNew from './pages/offercheck/CompanyNew.jsx'
import Dashboard from './pages/offercheck/Dashboard.jsx'
import Demo from './pages/offercheck/Demo.jsx'
import Button from './components/offercheck/Button.jsx'
import { ArrowRightIcon } from './components/offercheck/icons.jsx'
import logo from './assets/icon.svg'

// Company mode = the company-auth surfaces (register, invite creation, dashboard itself).
// The Dashboard link is scoped to those — it reads a company API key from localStorage and
// lists that company's sessions, so it has no meaning for a candidate or on the landing page.
function isCompanyMode(pathname) {
  return pathname.startsWith('/offercheck/company') || pathname === '/offercheck/dashboard'
}

function NavBar() {
  const { pathname } = useLocation()
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-bg-surface border-b border-border shadow-card">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <Link to="/" className="flex items-center gap-2 focus-ring rounded-md">
            <img src={logo} alt="" className="h-6 w-6" />
            <span className="font-display text-ink-primary font-semibold tracking-tight">
              Offer Check
            </span>
          </Link>

          <div className="flex items-center gap-1">
            {isCompanyMode(pathname) && (
              <Link
                to="/offercheck/dashboard"
                className="focus-ring px-3 py-1.5 rounded-md text-sm font-medium text-ink-secondary hover:text-ink-primary hover:bg-bg-elevated transition-colors"
              >
                Dashboard
              </Link>
            )}
            <a
              href={`${import.meta.env.VITE_BACKEND_URL || 'https://d31d2a226327eaf1da3c400fc137f21639555cf8-8000.dstack-pha-prod5.phala.network'}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="focus-ring px-3 py-1.5 rounded-md text-sm font-medium text-ink-secondary hover:text-ink-primary hover:bg-bg-elevated transition-colors flex items-center gap-1.5"
            >
              API docs
              <ArrowRightIcon size={12} className="-rotate-45" />
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
      <h1 className="font-display text-hero text-ink-primary">404</h1>
      <p className="text-ink-secondary">We couldn't find that page.</p>
      <Button onClick={() => navigate('/')}>Go home</Button>
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
            <Route path="/offercheck/candidate/join/:inviteId" element={<CandidateJoin />} />
            <Route path="/offercheck/candidate/:sessionId" element={<CandidateSession />} />
            <Route path="/offercheck/employer/:sessionId" element={<EmployerSession />} />
            <Route path="/offercheck/company/register" element={<CompanyRegister />} />
            <Route path="/offercheck/company/new" element={<CompanyNew />} />
            <Route path="/offercheck/dashboard" element={<Dashboard />} />
            <Route path="/offercheck/demo" element={<Demo />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
