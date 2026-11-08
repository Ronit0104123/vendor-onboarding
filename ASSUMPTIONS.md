# Assumptions

Where the brief left something open, this is what I chose and why.

## Decisions and severities
1. **E3 (bank account in a person's name) is REJECTED, not sent to internal review.** A vendor that claims to be a Private Limited company but asks to be paid into an individual's account is the classic third-party-payment fraud pattern. The company can't "fix" this by resubmitting without changing the account, and a reviewer approving it would be overriding the exact control the process exists for. Code decides this: the LLM only says the two names are DIFFERENT_ENTITY, and a code rule recognises that one of them is a person.
2. **A well-formed GSTIN with a wrong check digit is BLOCKING.** A typo usually breaks the format too, which is FIXABLE. A GSTIN that looks right but fails the checksum is more likely made up.
3. **PAN-in-GSTIN mismatch and GSTIN-state mismatch are BLOCKING.** Each field is valid on its own, so these aren't typos: the GST registration belongs to a different taxpayer or state.
4. **Document vs form mismatches (account number, IFSC, PAN, GSTIN) are FIXABLE.** The usual cause is a typo, and the vendor must make the two agree. Fraud signals that can't be fixed by retyping (duplicate account, penny-drop name mismatch, a person's account) are BLOCKING.
5. **Attempt limit:** if items are still FIXABLE on attempt 3, the case is AUTO_CLOSED. BLOCKING always rejects, whatever the attempt.
6. **Confidence threshold is 0.75** (configurable). Below it, an extracted value goes to internal review rather than to the vendor. Below 0.5 for the document *type*, the vendor is asked for a clearer copy.
7. **Name normalisation** treats Pvt/Private, Ltd/Limited, Co/Company, Corp/Corporation, "&"/"and" and a leading "M/s" as equivalent, and ignores case and punctuation. "Pvt Ltd" vs "LLP" is *not* equivalent (different legal form), so it goes to the LLM, which usually answers UNSURE, and then to a human.
8. **Free-email domain** for a company is only a WARN, as the brief says. It doesn't change the decision.
9. **Duplicate account on a vendor that is still being onboarded** (not yet approved) goes to internal review rather than rejection. That vendor may itself be the legitimate one.
10. **Running a demo scenario twice** produces a duplicate of the first run, and the duplicate is rejected for the same account/PAN. That is correct behaviour. `make reset` restores the demo data.

## Process
11. **The buyer name** is one setting: `BUYER_NAME` (default "Acme Industries Pvt Ltd").
12. **Resubmission keeps what wasn't flagged.** PAN and account number are never shown back in full; leaving them blank keeps the value on file. Files that weren't flagged are kept unless replaced. Every check re-runs on every attempt.
13. **The same portal link works across attempts** (the brief asks for "the same link"). It is stored encrypted only so follow-up emails can repeat it; lookups use the hash.
14. **After a decision the link is revoked.** If the vendor is watching the page, they see "processed, check your email" rather than "invalid link".
15. **Reminders are flagged, not auto-sent.** "Reminder due" appears after `REMINDER_DAYS` (3) of waiting on the vendor. An admin sends the reminder with one click. A simulated clock (Demo page) moves "today" forward for the demo. A production version would send these from a scheduled job.
16. **Overrides need two admins (maker-checker).** The brief asks for "an admin with a mandatory reason". For bank-detail approvals the four-eyes rule is standard in finance, so it is on by default (`FOUR_EYES_OVERRIDES=true`). The seed creates two admins for the demo.
17. **The vendor is told less than procurement.** Rejection emails are polite and don't name the fraud check (telling a fraudster which control caught them helps them next time). The internal alert lists every reason.
18. **US and UK vendors** only need a bank proof; GST/PAN documents are India-specific. The UK country code is `GB` (ISO 3166). Rules live in `backend/config/countries.yaml`.

## LLM and data flow
19. **Models:** `gpt-5.4` for document vision and `gpt-5.4-mini` for name judgment and message drafting, both at low reasoning effort for speed. Both are configurable (`OPENAI_MODEL_VISION`, `OPENAI_MODEL_TEXT`).
20. **What is sent to OpenAI:**
    - *Document extraction*: page images of the uploaded document (up to 2 pages, max 1600 px), with no form data. The model is deliberately not told which slot the file was uploaded in.
    - *Name matching*: the two names being compared, nothing else.
    - *Message drafting*: the message type, the vendor's display name and the list of items for the vendor. Never PAN, account numbers or internal fraud reasons.

    Responses are stored redacted in `llm_calls`.
21. **The LLM writes only the wording around the fix-list.** Code inserts the exact list and the link, so a message can't ask for more or less than the checks found.
22. **Offline mock.** With `LLM_MODE=mock` (tests, seeding) a deterministic stand-in answers from `sample_data/manifest.json`. Unknown PDFs are read via their text layer; unknown images come back "unreadable", so a human looks at them. Seeded history uses the mock (free, reproducible); live demo runs use the real model.
23. **GSTINs are not redacted in logs.** They are public identifiers printed on every tax invoice. The PAN inside them is therefore not secret either, but a *bare* PAN is still masked everywhere.

## Verification providers
24. **Live GST lookup and penny-drop** are behind a provider interface (`app/verification/providers.py`). The "sandbox" provider answers from a fixture registry of the fictional companies. When a value isn't known, it returns UNAVAILABLE, which is a WARN and not a failure, so manually entered test data isn't blocked. A real GSTN lookup would return NOT_FOUND, which is BLOCKING.

## Infrastructure
25. **One deployable unit.** The FastAPI app serves the built frontend from the same origin. That gives one public URL, lets `SameSite=Strict` cookies work, and removes the need for cross-origin calls. A Vercel config (`frontend/vercel.json`) rewrites `/api/*` to the backend for those who want the frontend on Vercel; it keeps the browser on one origin for the same reason.
26. **Durable queue on the database.** Runs are rows (QUEUED → RUNNING → DONE). Workers claim them with a conditional UPDATE, a RUNNING job whose lease expires is picked up again, and a run that fails twice goes to manual review. I chose this over Celery/Redis to keep the moving parts to one database; the trade-off is polling latency of about 0.5 s.
27. **Live view uses SSE that reads stage rows from the database**, so it works whichever process runs the job, and a dropped connection resumes from the current state.
28. **Storage** is local disk in development and any S3-compatible bucket in production (`STORAGE_BACKEND=s3`), because Render/Railway disks are wiped on redeploy.
29. **Schema changes** go through Alembic. Migrations run automatically on startup.
30. **Timestamps** all come from one function (`app/timeutil.py`). The seed script pins it to create realistic backdated history without ever rewriting rows, which matters because the audit table refuses updates.
