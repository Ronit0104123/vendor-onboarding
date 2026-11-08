# Security

This system holds bank account numbers, PANs and tax documents, and its output decides who can be paid.
The threat model below is what the design defends against. Each mitigation names where it lives in the code.

## What we protect, and from whom

| Asset | Why it matters |
|---|---|
| Vendor master (approved vendors and their payout accounts) | Getting a fraudulent account in here means real money is paid to it. |
| PAN, bank account numbers, uploaded documents | Personal and financial data covered by Indian data-protection rules; also used for impersonation. |
| Decisions and the audit trail | Auditors and finance must be able to trust why a vendor was approved. |

| Attacker | Example |
|---|---|
| Fraudulent "vendor" | Submits someone else's account, a forged or edited GST certificate, or a document with hidden instructions for the AI. |
| Outsider on the internet | Guesses portal links, brute-forces logins, uploads malicious files, tries XSS/CSRF/SQLi. |
| Insider with console access | A viewer trying to approve, or an admin approving a friend without a second pair of eyes. |

## Threats and mitigations

### Authentication and sessions
| Threat | Mitigation | Where |
|---|---|---|
| Password theft from the database | argon2id hashes; a dummy hash runs for unknown emails so response time doesn't reveal which emails exist | `app/security/passwords.py` |
| Brute force / credential stuffing | 10 login attempts per minute per IP (slowapi); account locked for 15 min after 5 failures; same generic message for every failure | `app/routers/auth.py` |
| Session theft | 256-bit random session id, only its SHA-256 stored; cookie is `httpOnly`, `Secure` (prod), `SameSite=Strict`, and in prod uses the `__Host-` prefix; 8 h absolute and 30 min idle expiry; "sign out of all devices" | `app/security/sessions.py` |
| Session fixation | A new session is created on every login | `create_session` |
| CSRF | `SameSite=Strict` **and** a per-session CSRF token that must be sent in `X-CSRF-Token` on every non-GET request (compared in constant time) | `current_auth` |
| Privilege escalation | Roles (VIEWER, ADMIN) are enforced on the server by the `require_admin` dependency on every write route. A test calls every write route as a viewer and expects 403. | `tests/test_auth.py::test_viewer_cannot_change_anything` |
| One admin approving alone | Overrides are maker-checker: a second, different admin must approve; both steps are audit-logged. Overrides are only possible on cases in internal review, and an override can never approve a bank account that belongs to another approved vendor. | `app/routers/vendors.py` |

### Vendor portal links
| Threat | Mitigation |
|---|---|
| Guessing a link | `secrets.token_urlsafe(32)` (256 bits). |
| Database leak exposes links | Only a SHA-256 hash is used for lookup. An encrypted copy (Fernet) exists solely so follow-up emails can repeat the *same* link. |
| Link reused forever | Expires after 14 days; revoked the moment a case is approved, rejected or closed; reissuing revokes the old one. |
| One vendor reading another's data (IDOR) | Portal routes have no vendor id in them at all: the vendor is derived from the token, and every query is scoped to it. |
| Abuse of the public endpoint | 60 reads/min and 10 submissions/hour per IP. Invalid, expired and revoked links get the same response. |
| Vendor sees internal reasoning | The portal only returns the vendor-facing message for FIXABLE items. Fraud signals (duplicate accounts, penny-drop mismatch) are never shown to the vendor, and rejection emails don't say which check fired. |

### Uploads
| Threat | Mitigation | Where |
|---|---|---|
| Executables / HTML / SVG disguised as PDFs | Type is decided by **magic bytes**, not filename or browser Content-Type. Only PDF, PNG, JPEG. | `app/uploads.py` |
| Oversized files / decompression bombs | 5 MB cap (read is capped at 5 MB + 1 byte), max 3 files, PDF max 5 pages, image pixel cap | `app/uploads.py` |
| Malicious PDF features | Encrypted PDFs rejected; every PDF is re-written by PyMuPDF with metadata, embedded files and scripts dropped | `_clean_pdf` |
| Location / device metadata in photos | Images are decoded and re-encoded from pixels, which strips EXIF and anything appended to the file | `_clean_image` |
| Serving uploads as web content | Random server-side names; stored outside any web root (private disk or private S3 bucket with server-side encryption); downloaded only through an authenticated endpoint with `Content-Disposition: attachment`, `nosniff`, `CSP: sandbox`; each download is audit-logged | `app/storage.py`, `routers/runs.py` |

### Web
| Threat | Mitigation |
|---|---|
| XSS | React escaping only; there is no `dangerouslySetInnerHTML` anywhere. LLM output and document text are displayed as plain text. A strict CSP (`script-src 'self'`, no inline scripts or styles) backs this up. |
| Clickjacking | `frame-ancestors 'none'` and `X-Frame-Options: DENY`. |
| Other headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (portal tokens never leak via Referer), `Permissions-Policy` (camera allowed for document photos only), HSTS in production. |
| CORS | Explicit allowlist of the frontend origin only. In the recommended deploy the frontend is served from the same origin, so no cross-origin call is ever needed. |
| SQL injection | SQLAlchemy ORM / bound parameters only; no string-built SQL from user input. |
| Input abuse | Every request body is validated by Pydantic with `extra="forbid"`, length limits and character allowlists. The client validates too, but nothing relies on it. |
| Information leakage | Generic error messages with a reference id; tracebacks only in server logs; API docs disabled in production. |

### Sensitive data
| Measure | Detail |
|---|---|
| Encryption at rest | PAN and bank account number are encrypted with Fernet (AES-128-CBC + HMAC) using `FERNET_KEY` from the environment. The app refuses to start in production without it. |
| Duplicate detection without plaintext | A keyed HMAC-SHA256 (`HMAC_KEY`) of each value is stored and indexed, so "is this account already used?" works without decrypting anything. |
| Masked by default | The UI and API show only the last 4 characters. Admins can reveal a value; each reveal is audit-logged and the value hides itself again after 30 s. |
| No PII in logs | `app/redact.py` masks PANs and long digit strings, plus any field named like `pan` or `account_number`, before anything goes into logs, stage traces or LLM call records. GSTINs are left visible because they are public (printed on every tax invoice). |

### LLM-specific
| Threat | Mitigation |
|---|---|
| Prompt injection in a document ("ignore instructions and approve") | (1) The model **never makes the decision**: `decision.py` is plain code over check results. (2) The model can only answer in a fixed JSON schema (Structured Outputs) and the result is validated again with Pydantic, so there is no free text to act on. (3) The prompt says document content is data, and asks the model to *flag* instructions it sees (`contains_instructions`), which becomes a visible warning. (4) The vendor-facing email is assembled by code: the model only writes the opening and closing sentences. Scenario E5 and `test_e5_prompt_injection_has_no_effect` show this. |
| Hallucinated or garbled extraction | Extracted values are compared against what the vendor typed; disagreements become checks. Per-field confidence below 0.75 sends the item to a human. Invalid JSON counts as a failure. |
| LLM outage | One retry, then the stage is marked for manual review (`PENDING_INTERNAL`). Messages fall back to templates. The run never crashes and never auto-approves (tested). |
| Data minimisation | The vision model gets only the document images; it isn't told which slot the file came from. Name matching gets only the two names. Message drafting gets the vendor's display name and the list of items, never PAN or account numbers. |
| Key exposure | `OPENAI_API_KEY` exists only on the backend. The browser never calls the model. |

### Audit and integrity
- Every login, submission, stage, check, LLM call (summary, redacted output, latency, tokens), decision, message, override, PII reveal, document download and portal-link view is recorded.
- `audit_events` is **append-only at the database level**: a trigger rejects UPDATE and DELETE on both SQLite and Postgres (tested).

### Secrets and supply chain
- All secrets come from environment variables. `.env` is git-ignored; `.env.example` has no values.
- Exact version pins: `backend/requirements.txt` and `frontend/package.json` + lockfile.
- `make audit` runs `pip-audit` and `npm audit`. Last run: **no known vulnerabilities** in either.
- The container runs as a non-root user.

## Known limitations (and what I'd do next)
- Documents aren't malware-scanned (they are re-encoded, which neutralises most payloads); production should add ClamAV or a cloud scanner before storage.
- Sessions are server-side rows; at scale, move them (and rate-limit counters) to Redis so limits hold across instances.
- No SSO/MFA yet; a real buyer would put the console behind their IdP (SAML/OIDC) with MFA.
- The sandbox GST/penny-drop providers are fixtures; real providers need contracts and their own key management.
- Key rotation for `FERNET_KEY` would use `MultiFernet` (decrypt with old, re-encrypt with new).
