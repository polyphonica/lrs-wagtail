# LRS website rebuild (Wagtail)

**LRS = Liverpool Renaissance Singers** (not London). A Wagtail rebuild of the current Django site, which lives in `../LRS` and stays live until switch-over.

## Decisions made by the owner (2026-11-21)
- Stay with Python: Wagtail 8.1 on Django 6.1. Postgres in production, SQLite locally.
- Host on IONOS. No new paid services; everything is open source / free tier.
- **Changed 2026-11-22:** production moves to the owner's *other* IONOS server (more resources), not the old site's VPS. It already runs several other sites on nginx + gunicorn: **they must not be affected in any way.** The trial deploy (step 3) goes there too, on a test address, so the choir's main website contact can preview it.
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

## Logins (decided 2026-11-21)
Everyone has an individual login: singers, Committee and Editors. No shared accounts; no public sign-up (the old site's `/register/` page is not carried over). The old site has only two accounts, `admin` and a shared `singer1` login, so singers' accounts must be created new before the switch-over, and `singer1` is then deactivated. When someone leaves, deactivate their account. Imported accounts have no email address yet, so one must be added before a password reset can reach them.

## Built in Phase 2 so far
- **Password reset by email**: themed pages at `/password-reset/`, email wording in `core/templates/core/email/`. Sending uses Gmail SMTP; for now the owner's personal Gmail with an app password. Locally, real sending needs `EMAIL_BACKEND` set in `.env` (git-ignored), loaded with `set -a; source .env; set +a`; otherwise emails print to the terminal. Check settings with `manage.py sendtestemail`.
- **Redirects from old URLs** (Wagtail redirects, editable under Settings → Redirects): fixed ones made by `lrs_setup`, per-concert and per-document ones by the importer from old ids. `/calendar/`, `/committee-calendar/` and `/newsletters/` point to the home page as temporary (302) redirects; repoint them when those pages exist.
- **Gallery page** (`/gallery/`), plus `robots.txt` and the Google Search Console verification file at the old site's addresses (`lrs/urls.py`).
- **Homepage matches the live site**: header shows the choir's name as text (no logo image; the live site has none); heading, strapline and `quote` field carry the live text; new "Image beside text" block holds the choir photo and intro. The two homepage images (score background, choir photo) are in the local DB only (see step 7).
- **Photo privacy**: every uploaded image is re-saved without EXIF/XMP (GPS, camera, owner), turned upright first (`core/models.py`, end). Wagtail would otherwise copy GPS into every served rendition. The importer goes through the same path.
- **Trial deploy** on the shared IONOS server (layout and update steps in README, "Deploy"). Found and fixed one server-only bug: Postgres needs `django.contrib.postgres` for Wagtail search (`lrs/settings.py`). Outgoing email to Gmail works from the server. The Contact page has no "to" address yet, so messages are stored but not emailed.
- **Contact-form spam protection** (`ContactPage` in `core/models.py`): a hidden "website" trap box plus a signed time stamp (under 3 seconds = bot; over 2 days = "please press Send again"). Spam gets the normal thank-you page but is not stored or emailed. Both checks sit outside the Wagtail form, so editors can change the form fields freely.

## Next steps (agreed order, 2026-11-21)
1. ~~Contact-form spam protection~~ (done 2026-11-22).
2. Two-step login for admins (django-otp). **Parked 2026-11-22: awaiting committee approval.** Proposed plan: required for everyone with admin access (not singers), QR-code setup on first login (adds the `qrcode` package), 10 backup codes, a `manage.py` command to reset a locked-out admin, code page under the nginx login rate limit.
3. ~~Trial deploy on the new IONOS server~~ (done 2026-11-22): https://choir.tywynwebsites.co.uk, behind an nginx password (user `choir`). Next: show it to the choir's website contact.
4. Calendars: public + committee; then repoint the temporary `/calendar/` and `/committee-calendar/` redirects. **Parked 2026-11-22: committee to decide** whether to use a calendar on the new site or keep using Google Calendar in the choir's Google account (if Google: link or load-on-click embed, like YouTube, and repoint the redirects to it).
5. Newsletter (largest job): subscribers, sign-up, sending (Gmail SMTP for now, maybe Amazon SES later); decide what to do with the old site's 14 newsletter files in `media/newsletters/` (not imported yet); repoint the `/newsletters/` redirect.
6. Singers' accounts: bulk creation (needs the owner's list of names and emails).
7. Production deploy on IONOS (gunicorn unit, Postgres, certbot), trial run on a test address, admin sign-off, DNS switch with the old site kept as a fallback. On production also:
   - re-upload the two homepage images, ideally a larger score image (the live one is 309 px wide);
   - add email addresses to imported accounts;
   - deactivate `singer1` once singers have their own accounts.
   - accounts made only on the preview (so far: `anna`, Editor, the choir's website contact, added 2026-11-22) exist only in the preview database: recreate them unless production starts from a copy of it.

## Working here
- Local: `export DEBUG=1`, `.venv/bin/python manage.py runserver`; tests: `DEBUG=1 .venv/bin/python manage.py test core` (keep them passing; without `DEBUG=1` or `SECRET_KEY` settings refuse to load).
- Import: the old site's local DB is unreachable (its `.env` points at a retired AWS database). Real data must come from `dumpdata` run on the live server (`/var/www/LRS`; command in README), copied to `~/Downloads`, imported into a fresh local DB with `manage.py lrs_setup --import <export.json> --media <old media folder>`, then the copies deleted. The export holds password hashes: never commit it.
- Copying the local DB to the server (trial only): dump `contenttypes auth.permission` to one file and everything else to a second (excluding `sessions`, `wagtailsearch`, `wagtailimages.rendition`, `wagtailcore.referenceindex`, `wagtailcore.pagelogentry`, `wagtailadmin.editingsession`), keep plain ids (Wagtail's natural keys break on the root collection), then on the server `flush` with `inhibit_post_migrate=True`, load file 1, then file 2, then `migrate`, `update_index`, `rebuild_references_index`, `collectstatic`. Delete both export files afterwards (password hashes).
- Local Python is from python.org; if TLS fails with CERTIFICATE_VERIFY_FAILED, run `/Applications/Python 3.12/Install Certificates.command`.
- Commit only when the owner asks. This is its own git repo, separate from `../LRS`. The owner tries a change first (locally or on the preview), then says "commit and push": `git fetch` and check `origin/main` first, commit on a short-lived branch, fast-forward `main`, delete the branch, push. The owner works from more than one computer, so keep everything needed in this repo.
- Parked steps (2, 4) wait for the committee: don't start one until the owner says it has decided.

## Server (shared IONOS, also runs the owner's other sites)
- Log in: `ssh root@tywynwebsites.co.uk` (the same server). Key login only. Each computer needs its own key: `ssh-keygen -t ed25519 -f ~/.ssh/ionos_lrs -C lrs-deploy`, `ssh-copy-id -i ~/.ssh/ionos_lrs.pub root@tywynwebsites.co.uk`, `ssh-add --apple-use-keychain ~/.ssh/ionos_lrs`, all typed in Terminal: password and passphrase prompts don't receive input through Claude Code's `!` shell.
- **Never affect the other sites.** Survey read-only first and get the owner's go-ahead before changing anything outside `/var/www/lrs`. Before and after any nginx change, check every other site from outside (status code of http and https for each `server_name` in `/etc/nginx/sites-enabled/`, plus which certificate answers an unknown name: it must stay recorder-ed.com) and compare. `nginx -t`, then `systemctl reload nginx`; never restart; no system package upgrades. A copy of nginx's settings from before LRS: `/root/nginx-backup-2026-11-22.tgz`.
- Layout and update steps: README, "Deploy". Preview password file: `/etc/nginx/lrs-preview.htpasswd` (user `choir`).

## Known issues in the old site
- `../LRS/choir/settings.py` (tracked in git) contains a hard-coded database password. Flagged to the owner; to be fixed when they are back in that project.
- The old site has a public `/register/` page that lets anyone create an account (see Logins).
- About 52 images embedded in old page text (`media/uploads/`) are dropped by the importer; some pages may need pictures re-added.

## Links
- Committee proposal: https://claude.ai/artifact/BGJZprvzmgP39BeMRMU2gW (Claude Doc, the master). A copy is in `docs/committee-proposal.md` (exported 2026-11-22; export again after editing the doc). It still says the site runs on the old site's IONOS server; production now goes on the shared server (see Decisions).
