<!-- Copy of the Claude Doc https://claude.ai/artifact/BGJZprvzmgP39BeMRMU2gW, exported 2026-11-23.
     The online doc is the master: edit there, then export again. The diagram is only in the online doc. -->

# LRS Website Renewal — Proposal for the Committee

21 Nov 2026 · Michael

## Summary

I propose rebuilding the LRS website on **Wagtail**, a well-established, free content management system built on the same Python and Django foundation as today's site. It would keep every current feature, run on our existing IONOS server, and cost nothing beyond the hosting we already pay for.

The new site would be faster for visitors, more secure, and much easier for admins creating concert listings. Its look would also be replaceable without touching the underlying system. A working prototype is being built alongside the current site, which stays live and unchanged until the committee is happy to switch.

## Why change

The current site works, but it carries a lot of weight it doesn't need, and one part of it is no longer supported.

- **Size:** the site is made of 1,829 files, but only about 60 are our own code. The rest are bundled third-party files and leftovers from the original purchased design (127 MB of static files).
- **An unsupported editor:** the text editor admins use (CKEditor 4) reached end of life in 2023 and has known security weaknesses that will not be fixed.
- **Design is hard to change:** layout and content are mixed together, so a new look means rewriting many pages.
- **Fragile updates:** changes are copied to the server by hand, and the server has drifted from the master copy of the code.
- **Newsletter limits:** emails go out through a Gmail account capped at about 500 a day, with some going to spam.

## What stays the same

Everything the current site does today carries over. Existing concerts, composers, documents, FAQs, links and subscribers would be transferred automatically, and old web addresses would redirect to their new pages so search results keep working.

| Area | Current features kept |
| --- | --- |
| Concerts | Upcoming and past concerts, concert detail pages, booking links, ticket prices, venue and time |
| Music | Composers and repertoire page ("Our music") |
| Public pages | Home, About, Join, Donate, Contact form, FAQ, Links, Calendar, photo gallery |
| Members | Login, singer area, document downloads, committee calendar |
| Admin | Manage concerts, composers, FAQs, links, documents and subscribers |
| Newsletter | Sign-up form, subscriber list and export, sending newsletters with attachments |

## Proposed approach

The site would be built on Wagtail, which is used by organisations such as the NHS, Google and many charities. It sits on Python, Django and PostgreSQL, which we already use, and runs on our current IONOS server.

*[Diagram: proposed structure, 3 layers. See the online doc.]*

The key design choice is a strict separation between content and design. Admins manage content in the stable middle layer. The design layer only displays that content, so a future redesign means replacing the top layer alone, with no change to concerts, documents or member logins.

## What improves for admins

Creating a concert listing becomes a matter of filling in fields and stacking ready-made blocks, with the design taken care of automatically.

- **Concert essentials as fields:** title, date, time, venue, price and booking link. These drive the listings and calendar, so nothing is typed twice.
- **Content blocks to build the page:** text, image, photo gallery, programme (piece and composer), audio sample, YouTube video, quote, and a ticket button. Blocks can be added, reordered or removed by dragging.
- **Images done for you:** upload a photo once and mark its focal point. The site produces correctly sized, compressed versions for phones and desktops, and strips hidden location data from photos.
- **Audio samples:** upload an MP3 or similar; it plays in a simple player on the concert page.
- **Video:** paste a YouTube link and the video appears on the page, using YouTube's privacy-enhanced mode.
- **Preview, drafts and scheduling:** see exactly how a page will look before publishing, save drafts, and set a page to go live on a chosen date.
- **Revision history:** every save is kept, so a mistake can be undone.

## What improves for website visitors

Visitors get faster pages, sharper images and a site that works well on a phone. The targets are a Google Lighthouse score of 95 or more and pages under about 300 KB.

- **Speed:** one small style file, very little JavaScript, and images sized for the device viewing them. Public pages are cached, and a free Cloudflare layer serves them from close to the visitor.
- **Mobile first:** concert listings, maps and booking buttons designed for phones, where most visitors arrive from.
- **Better concert pages:** a clear date, venue and ticket button at the top, then the programme, photos, audio and video in a consistent layout.
- **Accessibility:** readable text sizes and contrast, image descriptions, and keyboard-friendly navigation.
- **Sharing:** each concert shows a proper picture and summary when shared on WhatsApp, Facebook or email.

## Documents for members and committee

Every document is placed in one of three access levels when it is uploaded, and the site checks the level on every download.

| Level | Who can download | Examples |
| --- | --- | --- |
| Public | Anyone | Concert flyers, joining information |
| Members | Any logged-in choir member | Rehearsal schedules, music notes, newsletters |
| Committee | Committee members only | Minutes, finances, policies in draft |

Documents are stored outside the public part of the server, so a copied link does not work for someone without access. Admins can replace a document with a newer version without changing its link.

## Security improvements

The biggest single gain is removing the unsupported editor; the rest closes the common ways small sites are compromised.

- **Two-step login for admins:** anyone who can edit the site enters a 6-digit code from a phone app as well as their password. A stolen password alone is not enough.
- **Limits on login attempts** to block password guessing.
- **Upload checks:** files are checked for their real type and size before they are accepted.
- **Browser protections:** standard security headers that stop the site being framed or injected with outside scripts.
- **Kept up to date:** automatic alerts when any component needs a security update.
- **Nightly backups** of the database and documents, stored off the server.
- **Reliable deployment:** updates go to the server from the master copy of the code, so the live site always matches what has been tested.

## Costs

There are no new licence or subscription costs. All the software is free and open source, with no charge per admin or per page. Development is volunteer time.

| Item | Cost |
| --- | --- |
| Wagtail, Django, Python, PostgreSQL | Free (open source) |
| Two-step login (django-otp), image and audio processing | Free (open source) |
| IONOS server and domain | Existing cost, unchanged |
| SSL certificate (Let's Encrypt) | Free |
| Cloudflare speed and protection layer | Free plan |
| YouTube video hosting | Free |
| Off-server backups | Free (Backblaze B2 free tier, or a copy to a personal drive) |
| Newsletter sending | Free if we stay on Gmail; optional move to Amazon SES at about $0.10 per 1,000 emails |

One caveat: YouTube may show adverts on embedded videos, even on a channel that isn't monetised.

## Questions for the committee

Twelve decisions are open, on two-step login, calendars, the newsletter and members' contact details; work on each waits for the committee's answer. The recommendations are mine; the last column is for the meeting. The background follows the table.

| # | Question | Recommendation | Decision |
| --- | --- | --- | --- |
| 1 | Should everyone who can edit the website (Editors and Committee) have to use two-step login? | Yes. Singers keep a password only. | |
| 2 | Can each of those people use a free phone app such as Google Authenticator? | Yes. Anyone without a smartphone uses printed one-time backup codes. | |
| 3 | Committee calendar: keep using Google Calendar in the choir's Google account, or move it to the new site? | Keep Google Calendar if the committee is happy with it; the members' area links to it. | |
| 4 | Public calendar: what should visitors see? | The concert listings the site already builds from each concert. A public Google Calendar only if other public events (such as open rehearsals) need listing. | |
| 5 | Who adds events to the calendars? | Names needed. | |
| 6 | Does the choir still send a newsletter? How often, and to roughly how many people? | Facts needed; question 7 depends on them. | |
| 7 | How should newsletters be sent? | A small list: from the new site through Gmail (free). Otherwise keep the current tool and add a sign-up form to the site. | |
| 8 | What happens to the 14 newsletters on the old site? | Keep them as an archive in the members' documents. | |
| 9 | Should members keep their own contact and emergency details up to date on the website, instead of paper forms? | Yes, but later: once every singer has their own login. | |
| 10 | Which details should be collected? | Name, email, mobile, voice part and an emergency contact. Postal address only if the choir posts things. No medical information. | |
| 11 | Which committee roles may see members' details, and who is the choir's privacy contact? | Names needed. As few people as possible, e.g. the Secretary and the Chair. | |
| 12 | How long are a member's details kept after they leave? | 12 months, then deleted automatically. | |

### Two-step login for admins (questions 1–2)

Two-step login stops someone who has guessed or stolen an editor's password from getting in. After the password, the site asks for a 6-digit code from an app on the person's phone; the code changes every 30 seconds.

It matters for editors because they can publish anything on the public site and open the Committee documents. It costs nothing and needs no outside service.

- **Setting up:** once, at the first login after it goes live, by scanning a square code with the phone app. About two minutes.
- **Every login after that:** password, then the code from the app.
- **Lost phone:** each person gets 10 one-time backup codes to keep somewhere safe. If those are gone too, the webmaster resets their two-step login and they set it up again.
- **Singers:** not affected. They only see members' pages and documents, and keep logging in with a password.

### Calendars (questions 3–5)

The old site has a public calendar and a committee calendar, but the committee also keeps events in Google Calendar in the choir's Google account. The new site can work either way; what matters is that events are entered in one place only.

| | Keep Google Calendar | Calendar on the new site |
| --- | --- | --- |
| Where events are entered | Google Calendar, as now | The website's admin |
| Concerts | Typed into Google as well as the concert listing | Appear automatically from each concert page |
| On phones | Already in the Google Calendar app | Through a subscription link people add once |
| Committee-only events | A private Google calendar, linked from the members' area | Shown only to Committee logins |
| On the website | A link, or the calendar shown after a click (like YouTube videos, so Google sees nothing until then) | Pages in the site's own design |
| Change for the committee | None | A new place to enter events |

If the committee is happy with Google Calendar, keeping it is simpler: nothing changes for them, and the site's concert listings already serve as the public list of concerts.

### Newsletter (questions 6–8)

The right newsletter set-up depends on facts only the committee has: whether newsletters still go out, how often, to how many people, and with which tool. The old site sends through a Gmail account, which allows about 500 emails a day, and some land in spam.

- **Send from the new site:** a sign-up form, a subscriber list and sending, all free through Gmail. Fits a list of a few hundred people.
- **Keep the current tool:** if newsletters already go out another way, the new site only needs a sign-up form that feeds that list.
- **A larger list later:** a sending service costing pennies per thousand emails would remove the daily limit, but that is a new paid service and would need the committee's approval.

Whichever is chosen, every newsletter must offer a one-click unsubscribe, and the list may only hold people who signed up themselves.

The old site holds 14 past newsletters that were not carried over. They could go into the members' documents as an archive, go on the public site, or be left behind.

### Members' contact details (questions 9–12)

Members could keep their own contact and emergency details up to date on the website, replacing the paper forms. This is proposed for later, not for the first version: it needs every singer to have their own login first.

- **My details:** a page where each member sees, changes and saves only their own details, showing when they last did so.
- **For the committee:** a list in the admin that only the named committee roles can open (not website editors), with a spreadsheet download, e.g. a printable emergency-contacts sheet for rehearsals and concerts.
- **Email changes** are confirmed by a link before use, because the same address receives password resets and newsletters.
- **A yearly reminder** asks members to check their details are still right.
- **Cost:** none; no new service is needed.

The details collected should be only what the choir uses: name, email, mobile, voice part and an emergency contact (name, relationship, phone). Medical information is best left out: health data is "special category" data under UK GDPR and needs a stronger legal basis and extra safeguards. In an emergency, the emergency contact and a 999 call cover it.

**Legal side.** The paper forms already fall under UK GDPR; moving the details online is a good moment to write the rules down.

- **Responsibility:** the choir, as a charity, is the "data controller" and needs a named privacy contact (question 11).
- **Privacy notice:** a Privacy page saying what is collected and why, who can see it, how long it is kept, and people's rights to see, correct or delete their data and to complain to the ICO. The site needs one anyway for newsletter sign-ups and the contact form, so one page covers all three.
- **Lawful basis:** probably "legitimate interests": running the choir, and reaching someone's emergency contact if they are taken ill or hurt.
- **Someone else's data:** an emergency contact is a third party, so the form asks members to check that the person they name is happy to be listed.
- **Retention:** details are deleted automatically a set time after someone leaves (question 12).
- **ICO fee:** many small charities are exempt from the data protection fee; the committee should confirm the choir is.
- **Wording:** the webmaster can draft the privacy notice for the committee to approve; it is standard wording, not legal advice.

**Technical side.**

- **Two-step login (question 1) matters more:** a stolen committee password would otherwise expose members' addresses and emergency contacts.
- **Backups:** the details sit in the site's database and so in its nightly backups; old backups are deleted on a schedule, so removed details don't linger.
- **Paper forms** can be shredded once members have entered their details online.
