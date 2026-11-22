"""Send waiting newsletter emails, a batch at a time (run every minute on the server by lrs-jobs.timer).

    python manage.py send_newsletters           # one batch
    python manage.py send_newsletters --all     # locally: keep going until done or the daily limit is reached
"""
from django.core.management.base import BaseCommand

from core.newsletter import send_pending


class Command(BaseCommand):
    help = "Send waiting newsletter emails, keeping to the batch size and daily limit in settings."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="repeat batches until nothing more can be sent")

    def handle(self, *args, all=False, **options):
        total = 0
        while True:
            sent = send_pending()
            total += sent
            if not (all and sent):
                break
        if total or options["verbosity"] > 1:
            self.stdout.write(f"Newsletter: {total} sent.")
