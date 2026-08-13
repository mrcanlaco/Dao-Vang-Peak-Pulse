# 🤝 Contributing to DAO VANG — PeakPulse AI

Thank you for your interest in contributing to **DAO VANG (PeakPulse AI)**! We welcome contributions of all kinds: bug reports, documentation improvements, new machine learning models, additional exchange connectors, and frontend enhancements.

---

## 📜 Table of Contents

1. [Code of Conduct](#-code-of-conduct)
2. [Getting Started](#-getting-started)
3. [Development Workflow](#-development-workflow)
4. [Engineering Standards & Rules](#-engineering-standards--rules)
5. [Testing & Quality Gates](#-testing--quality-gates)
6. [Submitting a Pull Request](#-submitting-a-pull-request)

---

## 🛡 Code of Conduct

All contributors and maintainers are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). Please be respectful and constructive in all interactions.

---

## 🚀 Getting Started

### 1. Fork & Clone
```bash
git clone https://github.com/<your-username>/dao_vang.git
cd dao_vang
git remote add upstream https://github.com/mrcanlaco/dao_vang.git
```

### 2. Environment Setup

#### Backend (Python 3.11+)
We recommend using [`uv`](https://docs.astral.sh/uv/) for ultra-fast dependency management:
```bash
# Install dependencies including dev tools
uv sync --all-extras --dev

# Or using standard pip in a venv
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

#### Frontend (Node.js 18+)
```bash
cd frontend
npm install
cd ..
```

---

## 🛠 Development Workflow

### 1. Create a Topic Branch
Always branch off the latest `main`:
```bash
git fetch upstream
git checkout main
git merge upstream/main
git checkout -b feat/your-feature-name  # or fix/your-bug-fix
```

### 2. Commit Message Guidelines
We follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat: add OKX futures data collector`
- `fix: resolve race condition in SQLite fallback`
- `docs: update Telegram bot setup guide`
- `refactor: optimize duckdb as-of join query`
- `test: add unit tests for walk-forward splitter`

---

## 📐 Engineering Standards & Rules

When writing code for DAO VANG, strictly observe these core tenets:

1. **Zero Lookahead Bias (Point-in-Time Correctness):**
   - In feature engineering and ML training, strictly avoid data leakage. Features for candle $t$ must only use information available strictly at or before $t$.
2. **Deterministic Data Engine:**
   - Use DuckDB with explicit schema definitions. All time-series joins must use `as-of` matching.
3. **No Auto-Trading / Human-in-the-Loop:**
   - DAO VANG is an analytical and alert radar. Do not introduce automated order execution logic.
4. **Security & Redaction:**
   - Never log full API tokens or private keys. Always use `redact_secrets` from `dao_vang.logging`.
5. **Bilingual Support (i18n):**
   - User-facing UI elements or Telegram alert strings should support both Vietnamese (`vi`) and English (`en`).

---

## 🧪 Testing & Quality Gates

Before opening a PR, ensure all quality checks pass locally:

### 1. Backend Checks
```bash
# 1. Format and Linting
uv run ruff check .

# 2. Type Checking
uv run pyright

# 3. Unit & Integration Tests
uv run pytest
```

### 2. Frontend Checks
```bash
cd frontend

# Run TypeScript type check and production build
npm run build
```

---

## 📬 Submitting a Pull Request

1. **Push your branch:** `git push origin feat/your-feature-name`
2. **Open a PR:** Go to the GitHub repository and click **New Pull Request**.
3. **Fill the PR Template:** Clearly describe:
   - What changed and why.
   - Which issue is resolved (e.g. `Fixes #123`).
   - Confirmation that all automated tests and builds pass.
4. **Code Review:** Maintainers will review your PR and provide constructive feedback.

Thank you for helping make DAO VANG more powerful and accessible to traders worldwide! 🚀
