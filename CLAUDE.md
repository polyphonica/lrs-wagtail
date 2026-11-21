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
- `deploy/` = nginx config (CSP, rate limit on login and password-reset pages, `/media/` closed except resized images, `/protected/` X-Accel) and `env.example`.
- Keep the file count low: no vendored libraries, no media in git, no new dependencies without good reason.

## Access rules (set up by `manage.py lrs_setup`)
| Collection | Download | Manage |
|---|---|---|
| Public | anyone | Editors, Moderators |
| Members | Singers, Committee, Editors, Moderators | Editors, Moderators |
| Committee | Committee only | Committee only |
| Audio | anyone | Editors, Moderators |

Old-site mapping on import: Admins → Editors + Committee; Singers → Singers; documents in category "Committee" → Committee collection, others → Members; portfolio photos → Gallery page (the old `position` field is a display order number, not a role).

## Built in Phase 2 so far
- **Password reset by email**: themed pages at `/password-reset/`, email wording in `core/templates/core/email/`. Sending uses Gmail SMTP; for now the owner's personal Gmail with an app password. Locally, real sending needs `EMAIL_BACKEND` set in `.env` (git-ignored), loaded with `set -a; source .env; set +a`; otherwise emails print to the terminal. Check settings with `manage.py sendtestemail`.
- **Redirects from old URLs** (Wagtail redirects, editable under Settings → Redirects): fixed ones made by `lrs_setup`, per-concert and per-document ones by the importer from old ids. `/calendar/`, `/committee-calendar/` and `/newsletters/` point to the home page as temporary (302) redirects; repoint them when those pages exist.
- **Gallery page** (`/gallery/`), plus `robots.txt` and the Google Search Console verification file at the old site's addresses (`lrs/urls.py`).
- **Homepage matches the live site**: header shows the choir's name as text (no logo image; the live site has none); heading, strapline and `quote` field carry the live text; new "Image beside text" block holds the choir photo and intro. The two homepage images (score background, choir photo) are content in the local DB only: re-upload on production, ideally a larger score image (the live one is 309 px wide).
- **Photo privacy**: every uploaded image is re-saved without EXIF/XMP (GPS, camera, owner), turned upright first (`core/models.py`, end). Wagtail would otherwise copy GPS into every served rendition. The importer goes through the same path.

## Next steps (agreed order, 2026-11-21)
1. Contact-form spam protection (hidden trap field + timing check; no outside service).
2. Two-step login for admins (django-otp).
3. Consider a trial deploy on IONOS here, to catch server-only problems (e.g. blocked outgoing email) early.
4. Calendars: public + committee; then repoint the temporary `/calendar/` and `/committee-calendar/` redirects.
5. Newsletter (largest job; decide what to do with the 14 old newsletter files).
6. Singers' accounts (needs the owner's list of names and emails).
7. Production deploy, trial on a test address, admin sign-off, DNS switch.

## Working here
- Local: `export DEBUG=1`, `.venv/bin/python manage.py runserver`; tests: `.venv/bin/python manage.py test core` (keep them passing).
- Import: the old site's local DB is unreachable (its `.env` points at a retired AWS database). Real data must come from `dumpdata` run on the live server (`/var/www/LRS`; command in README), copied to `~/Downloads`, imported into a fresh local DB, then the copies deleted. The export holds password hashes: never commit it.
- Local Python is from python.org; if TLS fails with CERTIFICATE_VERIFY_FAILED, run `/Applications/Python 3.12/Install Certificates.command`.
- Commit only when the owner asks. This is its own git repo, separate from `../LRS`.

## Phase 2 (not built yet)
Two-step login for admins (django-otp) · newsletter (subscribers, sign-up, sending; Gmail SMTP for now, maybe Amazon SES later; the old site's 14 newsletter files in `media/newsletters/` are not imported yet) · calendar + committee calendar · contact-form spam protection · bulk creation of singers' accounts (needs a list of names and emails) · production deploy on IONOS (gunicorn unit, Postgres, certbot), then a trial run on a test address, admin sign-off, and DNS switch with the old site kept as a fallback.

## Committee proposal
https://claude.ai/artifact/BGJZprvzmgP39BeMRMU2gW (Claude Doc).

## Logins (decided 2026-11-21)
Everyone has an individual login: singers, Committee and Editors. No shared accounts. The old site has only two accounts, `admin` and a shared `singer1` login, so singers' accounts must be created new before the switch-over, and `singer1` is then deactivated. When someone leaves, deactivate their account. Password reset by email is built; imported accounts have no email address yet, so one must be added before a reset can reach them.

## Known issues in the old site
- `../LRS/choir/settings.py` (tracked in git) contains a hard-coded database password. Flagged to the owner; to be fixed when they are back in that project.
- The old site has a public `/register/` page that lets anyone create an account. The new site must not have public sign-up.
- About 52 images embedded in old page text (`media/uploads/`) are dropped by the importer; some pages may need pictures re-added.
