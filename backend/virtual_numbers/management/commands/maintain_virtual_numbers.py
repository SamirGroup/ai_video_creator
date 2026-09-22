from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from virtual_numbers.models import IncomingSMS, NumberOrder, PhoneNumber


class Command(BaseCommand):
    help = "Purge expired SMS and retire expired rentals. Run at least every 5 minutes."

    def handle(self, *args, **options):
        deleted, _ = IncomingSMS.objects.filter(
            delete_after__lte=timezone.now()
        ).delete()
        count = 0
        for pk in NumberOrder.objects.filter(
            status="active", expires_at__lte=timezone.now()
        ).values_list("pk", flat=True):
            with transaction.atomic():
                order = NumberOrder.objects.select_for_update().get(pk=pk)
                if order.status == "active" and order.expires_at <= timezone.now():
                    order.status = "expired"
                    order.save(update_fields=["status", "updated_at"])
                    PhoneNumber.objects.filter(pk=order.phone_id).update(
                        state="retired"
                    )
                    count += 1
        self.stdout.write(
            f"Deleted {deleted} expired messages; retired {count} rentals."
        )
