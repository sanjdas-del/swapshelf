from django.core.management.base import BaseCommand

from market.seed import seed


class Command(BaseCommand):
    help = "Load SwapShelf demo accounts and listings."

    def handle(self, *args, **options):
        seed()
        self.stdout.write(self.style.SUCCESS("SwapShelf demo data is ready."))
