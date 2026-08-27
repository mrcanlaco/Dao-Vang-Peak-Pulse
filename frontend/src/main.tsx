import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { LanguageProvider } from './i18n/LanguageContext'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { setupFetchAuthInterceptor } from './utils/auth.ts'

// Initialize global auth interceptor for all fetch requests
setupFetchAuthInterceptor()

// Defensively guard against Google Translate and 3rd-party browser extensions mutating DOM nodes
if (typeof Node === 'function' && Node.prototype) {
  const originalRemoveChild = Node.prototype.removeChild
  Node.prototype.removeChild = function <T extends Node>(child: T): T {
    if (child.parentNode !== this) {
      if (typeof console !== 'undefined' && console.warn) {
        console.warn('[DOM Guard] Cannot remove child: not a child of this node', child, this)
      }
      return child
    }
    return originalRemoveChild.call(this, child) as T
  }

  const originalInsertBefore = Node.prototype.insertBefore
  Node.prototype.insertBefore = function <T extends Node>(newNode: T, referenceNode: Node | null): T {
    if (referenceNode && referenceNode.parentNode !== this) {
      if (typeof console !== 'undefined' && console.warn) {
        console.warn('[DOM Guard] Cannot insert before: reference node not a child of this node', referenceNode, this)
      }
      return newNode
    }
    return originalInsertBefore.call(this, newNode, referenceNode) as T
  }
}

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

