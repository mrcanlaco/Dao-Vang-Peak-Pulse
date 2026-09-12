import { expect, test, type Page } from '@playwright/test';

interface ApiState {
  authenticated: boolean;
  scannerTriggers: number;
}

const statusFixture = {
  scanner_status: 'ONLINE',
  scanner_mode: 'shadow',
  heartbeat: '2026-09-13T01:30:37+07:00',
  scanned_coins_count: 150,
  active_signals_count: 0,
  top_risk_symbol: '',
  model_version: 'v2',
  model_id: 'frozen_test',
  telegram_connected: true,
  threshold: 0.25,
};

const telemetryFixture = {
  scanner_engine_status: 'ONLINE',
  last_scan_timestamp: '2026-09-13T01:30:37+07:00',
  next_scan_in_seconds: 240,
  poll_interval_minutes: 5,
  api_endpoint: 'Binance USD-M',
  average_api_latency_ms: 42,
  active_scan_mode: 'volatile',
  active_scan_modes: ['volatile'],
  scanned_pairs_count: 150,
  signals_triggered_count: 0,
  stablecoins_excluded_count: 8,
  runtime_state: { status: 'running' },
  model_id: 'frozen_test',
  cycle: 2,
  max_coins: 150,
  logs: [],
  telegram_dispatches: [],
};

const auditFixture = {
  report_available: true,
  report_generated_at: '2026-09-12T10:00:00Z',
  report_matches_current_model: true,
  model_name: 'frozen_test',
  horizon: '24h',
  target_drawdown: '-8%',
  mae_allowed: '+4%',
  sample_size: 25,
  total_alerts: 30,
  has_enough_data: true,
  metrics: {
    precision: 0.36,
    walk_forward_precision: 0.4,
    ci_95_lower: 0.31,
    ci_95_upper: 0.49,
    brier_score: 0.18,
    ece: 0.03,
  },
  precision_by_risk_level: {
    HIGH: { n_judged: 25, n_hit: 9, precision: 0.36 },
  },
  lead_time: {
    mean_hours: 2.5,
    median_hours: 2.2,
    min_hours: 0.5,
    max_hours: 8,
  },
  quality_gates: { precision_gate: true },
  validation_checks: {
    walk_forward_status: 'passed',
    leakage_test: 'passed',
    embargo_period: '24h',
    point_in_time_verified: true,
  },
};

async function mockApi(page: Page, state: ApiState) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    let body: unknown = {};

    if (pathname === '/api/auth/status') {
      body = { auth_required: true, authenticated: state.authenticated };
    } else if (pathname === '/api/auth/verify') {
      const payload = request.postDataJSON() as { password?: string };
      state.authenticated = payload.password === 'smoke-password';
      body = state.authenticated ? { ok: true } : { error: 'invalid password' };
      if (!state.authenticated) {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify(body),
        });
        return;
      }
    } else if (pathname === '/api/status') {
      body = statusFixture;
    } else if (pathname === '/api/signals') {
      body = [];
    } else if (pathname === '/api/candidates/compare') {
      body = null;
    } else if (pathname === '/api/candidates') {
      body = [];
    } else if (pathname === '/api/audit') {
      body = auditFixture;
    } else if (pathname === '/api/market') {
      body = null;
    } else if (pathname === '/api/watchlist') {
      body = { active_modes: ['volatile'], manual_watchlist: [], presets: [] };
    } else if (pathname === '/api/tracking-watchlist') {
      body = [];
    } else if (pathname === '/api/scanner/telemetry') {
      body = telemetryFixture;
    } else if (pathname === '/api/models') {
      body = {
        models: [],
        total: 0,
        current_scanner_model_id: 'frozen_test',
      };
    } else if (pathname === '/api/scanner/trigger') {
      state.scannerTriggers += 1;
      body = { ok: true, accepted: true };
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
}

test('login unlocks the dashboard without storing the password', async ({ page }) => {
  const state: ApiState = { authenticated: false, scannerTriggers: 0 };
  await mockApi(page, state);
  await page.goto('/');

  await page.getByTestId('login-password').fill('smoke-password');
  await page.getByTestId('login-submit').click();

  await expect(page.getByTestId('main-workspace')).toBeVisible();
  await expect.poll(() => state.authenticated).toBe(true);
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('dao_vang_authenticated')))
    .toBe('1');
  await expect
    .poll(() => page.evaluate(() => JSON.stringify(localStorage)))
    .not.toContain('smoke-password');
});

test('authenticated dashboard loads the release-critical API chain', async ({ page }) => {
  const state: ApiState = { authenticated: true, scannerTriggers: 0 };
  const requestedPaths = new Set<string>();
  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith('/api/')) requestedPaths.add(pathname);
  });
  await mockApi(page, state);
  await page.goto('/');

  await expect(page.getByTestId('main-workspace')).toBeVisible();
  await expect(page.getByTestId('workspace-tab-decision')).toBeVisible();
  await expect.poll(() => requestedPaths.has('/api/status')).toBe(true);
  await expect.poll(() => requestedPaths.has('/api/scanner/telemetry')).toBe(true);
  await expect.poll(() => requestedPaths.has('/api/audit')).toBe(true);
});

test('scanner trigger and model audit report remain operable', async ({ page }) => {
  const state: ApiState = { authenticated: true, scannerTriggers: 0 };
  await page.addInitScript(() => {
    localStorage.setItem('peakpulse_dev_mode', 'true');
  });
  await mockApi(page, state);
  await page.goto('/');
  await expect(page.getByTestId('main-workspace')).toBeVisible();

  await page.getByTestId('workspace-system-menu').click();
  await page.getByTestId('workspace-tab-telemetry').click();
  await page.getByTestId('scanner-trigger').click();
  await expect.poll(() => state.scannerTriggers).toBe(1);
  await expect(page.getByText(/Đã ghi nhận yêu cầu quét|Scan requested/)).toBeVisible();

  await page.getByTestId('workspace-system-menu').click();
  await page.getByTestId('workspace-tab-audit').click();
  await expect(page.getByTestId('model-audit-report')).toBeVisible();
  await expect(page.getByTestId('model-audit-report')).toContainText('frozen_test');
  await expect(page.getByTestId('model-audit-report')).toContainText('36.0%');
});
