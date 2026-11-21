# LRS website rebuild (Wagtail)

**LRS = Liverpool Renaissance Singers** (not London). A Wagtail rebuild of the current Django site, which lives in `../LRS` and stays live until switch-over.

## Decisions made by the owner (2026-11-21)
- Stay with Python: Wagtail 8.1 on Django 6.1. Postgres in production, SQLite locally.
- Stay on the existing IONOS VPS. No new paid services; everything is open source / free tier.
- Video = YouTube embeds only (privacy-enhanced, load-on-click). Audio samples are self-hosted.
- One maintainer (the owner). Admin users only create and edit content, mainly concert listings.
- Goals: fewer files, faster, more secure, top-quality admin editing and concert pages, and a design layer that can be swapped without touching content.

## Structure
- `core/` = the stable content model (pages, blocks, setup/import command). Themes never define content.
- `themes/<name>/` = templates + `theme.css` (design tokens at top) + `theme.js`. Selected by `LRS_THEME`. Keep templates display-only.
- Default template names resolve from the theme: `core/<model_name>.html`. All stream blocks render through `includes/block.html`.
- `deploy/` = nginx config (CSP, login rate limit, `/media/` closed except resized images, `/protected/` X-Accel) and `env.example`.
- Keep the file count low: no vendored libraries, no media in git, no new dependencies without good reason.

## Access rules (set up by `manage.py lrs_setup`)
| Collection | Download | Manage |
|---|---|---|
| Public | anyone | Editors, Moderators |
| Members | Singers, Committee, Editors, Moderators | Editors, Moderators |
| Committee | Committee only | Committee only |
| Audio | anyone | Editors, Moderators |

Old-site mapping on import: Admins → Editors + Committee; Singers → Singers; documents in category "Committee" → Committee collection, others → Members.

## Working here
- Local: `export DEBUG=1`, `.venv/bin/python manage.py runserver`; tests: `.venv/bin/python manage.py test core` (keep them passing).
- Import: the old site's local DB is unreachable (its `.env` points at a retired AWS database). Real data must come from `dumpdata` run on the live server (command in README).
- Commit only when the owner asks. This is its own git repo, separate from `../LRS`.

## Phase 2 (not built yet)
Two-step login for admins (django-otp) · newsletter (subscribers, sign-up, sending; Gmail SMTP for now, maybe Amazon SES later) · calendar + committee calendar · redirects from old URLs (e.g. `/concert-details/<id>/`) created by the importer · contact-form spam protection · production deploy on IONOS (gunicorn unit, Postgres, certbot), then a trial run on a test address, admin sign-off, and DNS switch with the old site kept as a fallback.

## Committee proposal
https://claude.ai/artifact/BGJZprvzmgP39BeMRMU2gW (Claude Doc).

## Logins (decided 2026-11-21)
Everyone has an individual login: singers, Committee and Editors. No shared accounts. The old site's per-user accounts and passwords come across on import. When someone leaves, deactivate their account. Password reset by email depends on Phase 2 email sending.

## Known issue in the old site
`../LRS/choir/settings.py` (tracked in git) contains a hard-coded database password. Flagged to the owner; not yet fixed.
