/**
 * Authentication and Access Security utilities for Đảo Vàng System.
 */

const AUTH_STORAGE_KEY = 'dao_vang_access_password';

export function getStoredPassword(): string | null {
  try {
    return localStorage.getItem(AUTH_STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export function setStoredPassword(password: string): void {
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, password);
  } catch (err) {
    console.error('Failed to save auth password to localStorage', err);
  }
}

export function clearStoredPassword(): void {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    document.cookie = 'dao_vang_password=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
  } catch (err) {
    console.error('Failed to clear auth password from localStorage', err);
  }
}

export async function verifyPassword(password: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Access-Password': password,
      },
      body: JSON.stringify({ password }),
    });

    const data = await res.json().catch(() => ({}));
    if (res.ok && data?.ok) {
      setStoredPassword(password);
      return { ok: true };
    }
    return {
      ok: false,
      error: data?.error || 'Mật khẩu không chính xác. Vui lòng thử lại.',
    };
  } catch (err) {
    return {
      ok: false,
      error: 'Không thể kết nối đến máy chủ. Vui lòng kiểm tra lại.',
    };
  }
}

export async function checkAuthStatus(): Promise<{ auth_required: boolean; authenticated: boolean }> {
  try {
    const res = await fetch('/api/auth/status', { cache: 'no-store' });
    if (!res.ok) {
      return { auth_required: true, authenticated: false };
    }
    return await res.json();
  } catch {
    return { auth_required: true, authenticated: false };
  }
}

let isInterceptorInitialized = false;

/**
 * Automatically injects X-Access-Password and Authorization headers to all /api/ fetch calls
 * and catches 401 Unauthorized responses to trigger lock screen.
 */
export function setupFetchAuthInterceptor(): void {
  if (isInterceptorInitialized || typeof window === 'undefined') return;
  isInterceptorInitialized = true;

  const originalFetch = window.fetch;

  window.fetch = async function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const isApiRequest = urlStr.includes('/api/');

    const modifiedInit: RequestInit = init ? { ...init } : {};

    if (isApiRequest) {
      const password = getStoredPassword();
      const headers = new Headers(
        modifiedInit.headers || (typeof input === 'object' && input && 'headers' in input ? (input as Request).headers : undefined)
      );

      if (password) {
        if (!headers.has('X-Access-Password')) {
          headers.set('X-Access-Password', password);
        }
        if (!headers.has('Authorization')) {
          headers.set('Authorization', `Bearer ${password}`);
        }
      }

      modifiedInit.headers = headers;
    }

    try {
      const response = await originalFetch(input, modifiedInit);

      if (isApiRequest && response.status === 401) {
        if (!urlStr.includes('/api/auth/verify') && !urlStr.includes('/api/auth/status')) {
          clearStoredPassword();
          window.dispatchEvent(new CustomEvent('dao_vang_auth_error', { detail: { status: 401 } }));
        }
      }

      return response;
    } catch (error) {
      throw error;
    }
  };
}
