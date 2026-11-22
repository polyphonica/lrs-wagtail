# Liverpool Renaissance Singers website (Wagtail prototype)

A rebuild of the LRS site on Wagtail 8.1 / Django 6.1. The content model is kept separate from the design, so the look can be replaced without touching content.

```
lrs/            settings and URLs (everything environment-specific comes from env vars)
core/           the stable content model
  models.py       pages: Home, Concerts (upcoming + /past/), Concert, Standard, Our music, Members, Contact
  blocks.py       content blocks: text, image, gallery, programme, audio, YouTube, quote, button, FAQ, link card
  management/commands/lrs_setup.py   groups, collections, access rules, page tree, import from the old site
  tests.py
themes/classic/ the design: templates + one CSS file + one small JS file
deploy/         nginx site, gunicorn and newsletter systemd units, and an example .env
```

## Run it locally

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DEBUG=1
.venv/bin/python manage.py migrate
.venv/bin/python manage.py lrs_setup                 # structure only
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```
The site is at http://localhost:8000 and the admin at http://localhost:8000/admin.

## Import the old site

On the live server, from the old project:
```
python manage.py dumpdata auth.group auth.user frontend.concert frontend.composer frontend.faq \
    frontend.links frontend.homepagecontent frontend.portfolio documents --indent 1 > lrs_export.json
```
Copy `lrs_export.json` and the old `media/` folder across, then on a **fresh** database:
```
python manage.py lrs_setup --import lrs_export.json --media /path/to/old/media
```
Passwords carry over, so members keep their logins. Old Admins become Editors + Committee, and old Singers stay Singers. Documents in the old "Committee" category go to the Committee collection, and all others go to Members. Documents that were only external links are listed at the end, to be added by hand.

Old photo-gallery pictures go to the Gallery page. Old addresses such as `/concert-details/<id>/`, `/past-concerts/` and `/portfolio/` redirect to the new pages; see and edit them in the admin under Settings → Redirects.

## Who can see what

| Collection | Download | Manage in admin |
|---|---|---|
| Public | anyone | Editors, Moderators |
| Members | Singers, Committee, Editors, Moderators | Editors, Moderators |
| Committee | Committee | Committee |
| Audio (concert samples) | anyone | Editors, Moderators |

Superusers can do everything. Every download goes through Wagtail's permission check. In production, nginx then streams the file (`NGINX_SENDFILE=1`), and `/media/` is closed apart from resized images.

## Switching design

Copy `themes/classic` to `themes/<new>`, change its templates and `theme.css`, and set `LRS_THEME=<new>`. Templates only display content. Colours, fonts and spacing are CSS variables at the top of `theme.css`.

## Tests

```
DEBUG=1 .venv/bin/python manage.py test core
```

## Deploy (IONOS, shared server)

The server also hosts other sites, so LRS keeps to itself: its own Linux user `lrs`, everything under `/var/www/lrs` (`app/` = this repo, `venv/`, `.env`, `media/`, `acme/`), its own Postgres database `lrs` (local socket, no password), gunicorn on `/run/lrs/gunicorn.sock` (`deploy/lrs.service`) and one nginx file, `zz-lrs` (`deploy/nginx.conf`; read the notes at its top). Always `nginx -t` before `systemctl reload nginx`; never restart nginx.

Update the code:
```
sudo -u lrs git -C /var/www/lrs/app pull
sudo -u lrs bash -c 'cd /var/www/lrs/app && set -a && . ../.env && set +a && \
  ../venv/bin/pip install -qr requirements.txt && ../venv/bin/python manage.py migrate && \
  ../venv/bin/python manage.py collectstatic --noinput'
systemctl reload lrs
sudo -u lrs bash -c 'cd /var/www/lrs/app && set -a && . ../.env && set +a && ../venv/bin/python manage.py warm_images --all'
```

Background jobs (once): copy `deploy/lrs-jobs.service` and `deploy/lrs-jobs.timer` to `/etc/systemd/system/`, then `systemctl daemon-reload && systemctl enable --now lrs-jobs.timer`. Every minute it sends waiting newsletter emails and makes resized pictures for anything just edited. Check with `systemctl list-timers lrs-jobs.timer` and `journalctl -u lrs-jobs`.

## Not yet built (phase 2)

See "Next steps" in `CLAUDE.md`: two-step login for admins, calendars, newsletter, singers' accounts, switch-over.
