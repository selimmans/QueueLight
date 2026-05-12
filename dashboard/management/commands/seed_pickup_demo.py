"""Management command: seed a demo pickup business with realistic data.

Usage:
    python manage.py seed_pickup_demo

Creates (or resets) a business called "Demo Café" with:
  - pickup_enabled=True, pos_type="demo"
  - 2 registered entries in Section 1 (one waiting, one ready)
  - 3 unregistered POS orders in Section 2 (hardcoded demo data)
  - A staff phone you can log in with: +16135550001

Visit: /staff/demo-cafe/
Login with phone: +1 (613) 555-0001
"""
from django.core.management.base import BaseCommand

from businesses.models import Business, StaffPhone
from queues.models import PickupEntry
from queues.pickup_service import PickupService


SLUG = "demo-cafe"
STAFF_PHONE = "+16135550001"


class Command(BaseCommand):
    help = "Seed a demo pickup business for UI preview"

    def handle(self, *args, **options):
        # ── Business ────────────────────────────────────────────────────
        biz, created = Business.objects.update_or_create(
            slug=SLUG,
            defaults={
                "name": "Demo Café",
                "is_active": True,
                "queue_enabled": False,
                "pickup_enabled": True,
                "pos_type": "demo",
                "logo_colour": "#4f46e5",
                "field_name_enabled": True,
                "field_name_required": False,
                "field_order_number_enabled": False,
                "field_order_number_required": False,
            },
        )
        action = "Created" if created else "Reset"
        self.stdout.write(f"{action} business: {biz.name} (slug={SLUG})")

        # ── Staff phone ──────────────────────────────────────────────────
        StaffPhone.objects.get_or_create(
            phone=STAFF_PHONE,
            business=biz,
            defaults={"name": "Demo Staff"},
        )
        self.stdout.write(f"Staff phone: {STAFF_PHONE}")

        # ── Clear existing pickup entries ────────────────────────────────
        PickupEntry.objects.filter(business=biz).delete()

        # ── Section 1: registered entries ───────────────────────────────
        e1 = PickupService.register(
            biz,
            order_number="T-38",
            customer_name="Marcus Williams",
            phone="+16135550099",
        )
        e1.pos_order_id = "DEMO-REGISTERED-1"
        e1.pos_order_items = ["Cold Brew", "Banana Bread"]
        e1.pos_order_total = 1350
        e1.pos_order_reference = "T-38"
        e1.save(update_fields=["pos_order_id", "pos_order_items", "pos_order_total", "pos_order_reference"])

        e2 = PickupService.register(
            biz,
            order_number="T-39",
            customer_name="Priya Sharma",
            phone="+16135550098",
        )
        e2.pos_order_id = "DEMO-REGISTERED-2"
        e2.pos_order_items = ["Flat White", "Egg Sandwich"]
        e2.pos_order_total = 1625
        e2.pos_order_reference = "T-39"
        e2.save(update_fields=["pos_order_id", "pos_order_items", "pos_order_total", "pos_order_reference"])
        # Mark Priya's order ready
        PickupService.mark_ready(e2)

        self.stdout.write("Section 1: 2 registered entries (1 waiting, 1 ready)")

        # ── Section 2 note ───────────────────────────────────────────────
        self.stdout.write(
            "Section 2: 3 unregistered POS orders (live from demo POS — T-41, T-42, T-43)"
        )

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Visit http://localhost:8000/staff/{SLUG}/\n"
            f"Log in with phone: {STAFF_PHONE}\n"
            f"Switch to the Pickup tab to see both sections."
        ))
