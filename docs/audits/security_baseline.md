# Security Baseline

**Date:** 2026-07-13
**Scope:** Authentication, authorization, data protection, input validation

---

## 1. Authentication Mechanisms

### 1.1 FastAPI (JWT)
- **Library:** python-jose (HS256)
- **Token lifetime:** 24 hours (configurable)
- **Storage:** Client-side (no server-side blacklist)
- **Password hashing:** bcrypt via passlib with 72-byte truncation
- **Endpoint:** `POST /api/auth/login`

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-01 | Critical | No token revocation mechanism. Compromised tokens valid until expiry. | `app/core/security.py:24-30` |
| S-02 | Critical | No rate limiting on login endpoint. Brute-force possible. | `app/api/auth.py:97-115` |
| S-03 | High | Secret key loaded from .env with fallback `"change-this-to-a-random-string"`. If .env missing, uses insecure default. | `app/config.py:20` |
| S-04 | High | JWT secret is symmetric (HS256). Same key signs and verifies. | `app/core/security.py:30` |
| S-05 | Medium | No token refresh mechanism. Users must re-authenticate after expiry. | (missing) |

### 1.2 Flask (Session)
- **Library:** Flask-Login
- **Storage:** Server-side session (cookie-based)
- **Endpoint:** `POST /auth/login`

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-06 | Critical | No CSRF protection on any Flask POST route. | `webapp/routes/auth.py`, `webapp/routes/profile.py`, `webapp/routes/jobs.py` |
| S-07 | High | Session cookie security flags not explicitly set (Secure, SameSite, HttpOnly). | `webapp/app.py:33` |
| S-08 | Medium | No session timeout configuration. | `webapp/app.py` |

### 1.3 Password Handling
- **Library:** passlib with bcrypt
- **Truncation:** 72 bytes (bcrypt limit)

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-09 | Critical | Hard-coded demo password hash `"demo-not-a-real-hash"` in test script. If copied to production, authentication bypassed. | `scripts/test_recommend.py:46` |
| S-10 | Medium | No password complexity enforcement in API registration (only Flask route checks length). | `app/api/auth.py:52-94` |
| S-11 | Low | No password breach checking (e.g., Have I Been Pwned API). | (missing) |

---

## 2. Authorization

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-12 | Critical | No rate limiting on any endpoint (login, registration, search, API). | All route files |
| S-13 | High | Admin/regular user role distinction not implemented. All users have same access. | `app/models/user.py` |
| S-14 | High | No authorization checks on job data — any user can see any job. This is acceptable for a job board but should be documented. | `app/api/jobs.py` |
| S-15 | Medium | Password reset token has no rate limiting. Can be abused to spam reset emails. | `app/api/auth.py:118-141` |

---

## 3. Data Protection

### 3.1 CV/Resume Data
**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-16 | High | No file-size limit enforcement at application level (Flask MAX_CONTENT_LENGTH is set but not validated in route). | `webapp/app.py:34`, `webapp/routes/profile.py:59` |
| S-17 | High | No PDF signature/MIME validation. Only file extension checked. | `webapp/routes/profile.py:16-17` |
| S-18 | High | No explicit consent mechanism before processing resume data. | `webapp/routes/profile.py:59` |
| S-19 | High | No configurable data retention. Resume text stored indefinitely in profile. | (missing) |
| S-20 | High | No account deletion or data export capability (GDPR). | (missing) |
| S-21 | Medium | Resume text sent to OpenAI API. User consent for external API call not explicitly obtained. | `app/services/resume_parser.py:123` |
| S-22 | Medium | No prompt-injection resistance in resume parsing. Malicious PDF text could manipulate LLM output. | `app/services/resume_parser.py:70-102` |

### 3.2 Personal Data
**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-23 | High | User email stored in plaintext in database (not encrypted at rest). | `app/models/user.py:17` |
| S-24 | Medium | Profile skills, locations, and career interests stored as plaintext arrays. | `app/models/user.py:56-63` |
| S-25 | Medium | No data anonymization for evaluation datasets. | `scripts/run_evaluation.py` |

### 3.3 Secrets Management
**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-26 | Critical | .env file may be committed if .gitignore is not properly configured. | `.gitignore` |
| S-27 | High | No secrets rotation mechanism. | (missing) |
| S-28 | Medium | API keys (Adzuna, Reed, OpenAI) stored in .env without encryption. | `.env.example` |

---

## 4. Input Validation

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-29 | High | No explicit HTML sanitization in Jinja2 templates. Relies on Flask default autoescaping. | `webapp/templates/` |
| S-30 | Medium | No input length validation on API endpoints beyond Pydantic model definitions. | `app/api/*.py` |
| S-31 | Medium | Search query not sanitized for special characters in keyword search (ILIKE pattern). | `app/services/search.py:186-191` |
| S-32 | Low | No SQL injection risk (SQLAlchemy ORM used throughout), but raw SQL in job detail route. | `webapp/routes/jobs.py:102-111` |

---

## 5. Network Security

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-33 | High | No CORS configuration on FastAPI. Cannot restrict cross-origin access. | `app/main.py:10-14` |
| S-34 | Medium | No HTTPS enforcement. HTTP allowed. | (missing) |
| S-35 | Medium | No Content Security Policy headers. | (missing) |
| S-36 | Low | No request size limits on FastAPI endpoints. | `app/main.py` |

---

## 6. Logging and Audit

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-37 | High | No structured logging. All output via `print()`. Cannot filter sensitive data. | All files |
| S-38 | High | No audit trail for security events (login failures, password resets, data access). | (missing) |
| S-39 | Medium | No log sanitization. Potential for log injection via user input. | All `print()` calls |
| S-40 | Medium | Password reset tokens printed to console in demo mode. | `app/api/auth.py:138-139` |

---

## 7. Dependency Security

**Findings:**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-41 | Medium | No dependency vulnerability scanning (e.g., safety, pip-audit). | (missing) |
| S-42 | Low | Some dependencies pinned to exact versions (good), but no lock file. | `requirements.txt` |

---

## 8. Security Summary

| Severity | Count |
|----------|-------|
| Critical | 6 |
| High | 14 |
| Medium | 14 |
| Low | 4 |
| **Total** | **38** |

---

## 9. Recommendations by Priority

### Immediate (Phase 0-1)
1. Add CSRF protection to Flask forms
2. Add rate limiting to login/registration
3. Remove hard-coded password hash from test script
4. Set secure cookie flags (Secure, SameSite, HttpOnly)
5. Add .env to .gitignore verification

### Short-term (Phase 1-2)
1. Add database indexes
2. Set up Alembic migrations
3. Add timezone-aware datetimes
4. Add processing error table

### Medium-term (Phase 3-6)
1. Add CORS configuration
2. Add structured logging
3. Add token revocation mechanism
4. Implement rate limiting middleware
5. Add PDF validation
6. Add consent mechanism for resume processing
7. Add account deletion/export (GDPR)
8. Add audit logging

### Long-term (Phase 7-8)
1. Add dependency vulnerability scanning
2. Add security test suite
3. Add CSP headers
4. Add request size limits
5. Add password breach checking
