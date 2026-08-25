import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { LanguageProvider } from './i18n/LanguageContext'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { setupFetchAuthInterceptor } from './utils/auth.ts'

// Initialize global auth interceptor for all fetch requests
setupFetchAuthInterceptor()

// Ensure fallback loading placeholder from index.html is completely removed
const initialLoadingBox = document.getElementById('initial-loading-box')
if (initialLoadingBox) {
  initialLoadingBox.remove()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary fallbackTitle="Hệ thống đã gặp lỗi giao diện">
      <LanguageProvider>
        <App />
      </LanguageProvider>
    </ErrorBoundary>
  </StrictMode>,
)

