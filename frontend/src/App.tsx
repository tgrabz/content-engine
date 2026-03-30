import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import ErrorBoundary from './components/ErrorBoundary'
import DashboardPage from './pages/DashboardPage'
import NichesPage from './pages/NichesPage'
import ScraperPage from './pages/ScraperPage'
import VideosPage from './pages/VideosPage'
import PostsPage from './pages/PostsPage'
import WorkspacePage from './pages/WorkspacePage'
import SettingsPage from './pages/SettingsPage'
import OAuthCallbackPage from './pages/OAuthCallbackPage'
import NotFoundPage from './pages/NotFoundPage'
import LoginPage from './pages/LoginPage'
import DownloadPage from './pages/DownloadPage'
import NetworkSettingsPage from './pages/NetworkSettingsPage'
import { useAppStore } from './stores/appStore'

// Lazy-load pages that pull in fabric.js (~400KB)
const EditorPage = lazy(() => import('./pages/EditorPage'))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'))

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-screen text-zinc-600 text-sm">
      Loading editor...
    </div>
  )
}

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { token } = useAppStore()
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/download" element={<DownloadPage />} />
        <Route path="/auth/callback" element={<OAuthCallbackPage />} />

        {/* Protected app with sidebar */}
        <Route path="*" element={
          <AuthGuard>
            <div className="flex min-h-screen bg-zinc-950">
              <Sidebar />
              <main className="flex-1 overflow-auto">
                <Routes>
                  <Route path="/" element={<WorkspacePage />} />
                  <Route path="/workspace" element={<WorkspacePage />} />
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/niches" element={<NichesPage />} />
                  <Route path="/scraper" element={<ScraperPage />} />
                  <Route path="/videos" element={<VideosPage />} />
                  <Route path="/editor" element={<Suspense fallback={<LoadingFallback />}><EditorPage /></Suspense>} />
                  <Route path="/templates" element={<Suspense fallback={<LoadingFallback />}><TemplatesPage /></Suspense>} />
                  <Route path="/posts" element={<PostsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/network-settings" element={<NetworkSettingsPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Routes>
              </main>
            </div>
          </AuthGuard>
        } />
      </Routes>
    </ErrorBoundary>
  )
}
