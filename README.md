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
deploy/         nginx config and an example .env
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
    frontend.links frontend.homepagecontent documents --indent 1 > lrs_export.json
```
Copy `lrs_export.json` and the old `media/` folder across, then on a **fresh** database:
```
python manage.py lrs_setup --import lrs_export.json --media /path/to/old/media
```
Passwords carry over, so members keep their logins. Old Admins become Editors + Committee, and old Singers stay Singers. Documents in the old "Committee" category go to the Committee collection, and all others go to Members. Documents that were only external links are listed at the end, to be added by hand.

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

## Not yet built (phase 2)

- Two-step login for admins (django-otp)
- Newsletter: subscribers, sign-up, sending
- Calendar and committee calendar
- Redirects from old URLs (`/concert-details/<id>/` and so on). Wagtail's Redirects module is installed; the importer should create these.
- Spam protection on the contact form
- Production deployment on the IONOS VPS (gunicorn systemd unit, Postgres database, certbot)
