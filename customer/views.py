from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

import phonenumbers

from businesses.models import Business
from queues.models import QueueEntry, QueueEventLog, PickupEntry
from queues.pickup_service import PickupService
from queues.services import QueueService, RuleViolationError

_JOIN_LIMIT = 20
_JOIN_WINDOW = 3600


def _is_rate_limited(ip: str) -> bool:
    key = f"ql_join_{ip}"
    count = cache.get(key, 0)
    if count >= _JOIN_LIMIT:
        return True
    cache.set(key, count + 1, timeout=_JOIN_WINDOW)
    return False


def _parse_phone(raw: str, country: str) -> tuple[str | None, str | None]:
    try:
        parsed = phonenumbers.parse(raw, country)
    except phonenumbers.NumberParseException:
        return None, "Please enter a valid phone number"
    if not phonenumbers.is_valid_number(parsed):
        return None, "Please enter a valid phone number"
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), None


@method_decorator(csrf_exempt, name="dispatch")
class JoinView(View):
    template_name = "customer/join.html"

    def _get_business(self, slug):
        key = f"business_obj:{slug}"
        business = cache.get(key)
        if business is None:
            business = get_object_or_404(Business, slug=slug)
            cache.set(key, business, timeout=30)
        return business

    def get(self, request, slug):
        business = self._get_business(slug)
        if not business.is_active:
            raise Http404

        # State 4: nothing enabled
        if not business.queue_enabled and not business.pickup_enabled:
            return render(request, self.template_name, {"business": business, "mode": "inactive"})

        calling_code = phonenumbers.country_code_for_region(business.country) or 1
        waiting_count = QueueEntry.objects.filter(
            business=business, status=QueueEntry.Status.WAITING
        ).count()
        wait_min, wait_max = _wait_range(business, waiting_count)
        ctx = {
            "business": business,
            "errors": {},
            "calling_code": calling_code,
            "waiting_count": waiting_count,
            "wait_min": wait_min,
            "wait_max": wait_max,
            "mode": _join_mode(business),
            "active_tab": request.GET.get("tab", "queue"),
        }
        if business.is_closing:
            ctx["closing_message"] = f"{business.name} is closing soon and is no longer accepting new customers."
        return render(request, self.template_name, ctx)

    def post(self, request, slug):
        business = self._get_business(slug)
        if not business.is_active:
            raise Http404
        if not business.queue_enabled:
            raise Http404
        if business.is_closing:
            raise Http404

        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")).split(",")[0].strip()
        if _is_rate_limited(ip):
            return render(request, self.template_name, {
                "business": business,
                "errors": {},
                "global_error": "Too many requests. Please try again later.",
                "mode": _join_mode(business),
                "active_tab": "queue",
            }, status=429)

        name = request.POST.get("name", "").strip()
        raw_phone = request.POST.get("phone", "").strip()
        errors = {}

        if not name:
            errors["name"] = "Please enter your name"
        phone, phone_error = _parse_phone(raw_phone, business.country)
        if phone_error:
            errors["phone"] = phone_error

        calling_code = phonenumbers.country_code_for_region(business.country) or 1
        if errors:
            return render(request, self.template_name, {
                "business": business,
                "errors": errors,
                "name": name,
                "phone": raw_phone,
                "calling_code": calling_code,
                "mode": _join_mode(business),
                "active_tab": "queue",
            })

        intake_fields = business.intake_fields or []
        intake_answers = {
            q: request.POST.get(f"intake_{i}", "").strip()
            for i, q in enumerate(intake_fields)
        }

        try:
            entry = QueueService.join(business, name=name, phone=phone, intake_answers=intake_answers)
        except RuleViolationError:
            raise Http404

        return redirect("customer:confirmation", slug=slug, entry_id=entry.pk)


class ConfirmView(View):
    template_name = "customer/confirmation.html"

    def get(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)

        waiting_qs = QueueEntry.objects.filter(
            business=business,
            status=QueueEntry.Status.WAITING,
        )
        ahead = waiting_qs.filter(position__lt=entry.position).count()
        waiting_count = waiting_qs.count()
        wait_min, wait_max = _wait_range(business, ahead)

        return render(request, self.template_name, {
            "business": business,
            "entry": entry,
            "ahead": ahead,
            "waiting_count": waiting_count,
            "wait_min": wait_min,
            "wait_max": wait_max,
        })


def _wait_range(business, ahead: int) -> tuple[int | None, int | None]:
    if not business.avg_service_minutes or ahead <= 0:
        return None, None
    mid = ahead * business.avg_service_minutes
    wait_min = max(1, round(mid * 0.75 / 5) * 5)
    raw_max = round(mid * 1.25 / 5) * 5
    wait_max = max(raw_max, wait_min + 5)
    return wait_min, wait_max


class CustomerStatusView(View):
    def get(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)

        called_last = (
            QueueEntry.objects.filter(business=business, status=QueueEntry.Status.CALLED)
            .order_by("-called_at")
            .first()
        )

        waiting_qs = QueueEntry.objects.filter(business=business, status=QueueEntry.Status.WAITING)
        waiting_total = waiting_qs.count()

        if entry.status == QueueEntry.Status.WAITING:
            if business.mode == business.MODE_BATCH:
                ahead = (
                    waiting_qs.filter(batch_number__lt=entry.batch_number)
                    .values("batch_number")
                    .distinct()
                    .count()
                )
            else:
                ahead = waiting_qs.filter(position__lt=entry.position).count()
        else:
            ahead = 0

        wait_min, wait_max = _wait_range(business, ahead)

        return JsonResponse({
            "status": entry.status,
            "batch_number": entry.batch_number,
            "position": entry.position,
            "ahead_count": ahead,
            "waiting_total": waiting_total,
            "currently_serving_batch": called_last.batch_number if called_last else None,
            "currently_serving_position": called_last.position if called_last else None,
            "wait_min": wait_min,
            "wait_max": wait_max,
            "mode": business.mode,
        })


@method_decorator(csrf_exempt, name="dispatch")
class LeaveQueueView(View):
    """Customer voluntarily leaves the queue."""

    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)

        if entry.status in (QueueEntry.Status.WAITING, QueueEntry.Status.CALLED):
            QueueService.abandon(entry)

        return redirect("customer:join", slug=slug)


def _join_mode(business: Business) -> str:
    """Return a string describing which forms to show on the join page."""
    if business.queue_enabled and business.pickup_enabled:
        return "both"
    if business.queue_enabled:
        return "queue_only"
    if business.pickup_enabled:
        return "pickup_only"
    return "inactive"


_VALID_RESPONSES = {"late_arrival", "left_other", "left_home"}


@method_decorator(csrf_exempt, name="dispatch")
class CustomerResponseView(View):
    """Record what a customer does after being abandoned/skipped."""

    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)

        action = request.POST.get("action", "").strip()
        if action not in _VALID_RESPONSES:
            return JsonResponse({"error": "Invalid action."}, status=400)

        if entry.status not in (QueueEntry.Status.ABANDONED, QueueEntry.Status.SKIPPED):
            return JsonResponse({"error": "No response needed for this entry."}, status=400)

        if action == "late_arrival":
            QueueEventLog.objects.create(
                business=business,
                entry=entry,
                event_type=QueueEventLog.EventType.LATE_ARRIVAL,
                before_values={"status": entry.status},
                after_values={},
                meta={"customer_response": action},
            )
        else:
            QueueEventLog.objects.create(
                business=business,
                entry=entry,
                event_type=QueueEventLog.EventType.LEFT,
                before_values={"status": entry.status},
                after_values={},
                meta={"customer_response": action},
            )

        return JsonResponse({"ok": True})


@method_decorator(csrf_exempt, name="dispatch")
class PickupJoinView(View):
    """Customer registers for a pickup notification.

    Two paths:
    - POS flow  (business.pos_type != 'none'): name-first, JS matches against
      POS, confirmed server-side on submit.  Handles hidden fields
      pos_order_id / pos_order_items / customer_name.
    - Standard flow (no POS): order_number + optional name + optional phone.
    """

    template_name = "customer/pickup_join.html"

    def _get_business(self, slug):
        key = f"business_obj:{slug}"
        business = cache.get(key)
        if business is None:
            business = get_object_or_404(Business, slug=slug)
            cache.set(key, business, timeout=30)
        return business

    def _ctx(self, business, **kwargs):
        calling_code = phonenumbers.country_code_for_region(business.country) or 1
        pos_enabled = business.pos_type != business.POS_NONE and bool(business.pos_api_token)
        return {"business": business, "calling_code": calling_code,
                "pos_enabled": pos_enabled, "errors": {}, **kwargs}

    def get(self, request, slug):
        business = self._get_business(slug)
        if not business.is_active or not business.pickup_enabled:
            raise Http404
        return render(request, self.template_name, self._ctx(business))

    def post(self, request, slug):
        import json as _json
        business = self._get_business(slug)
        if not business.is_active or not business.pickup_enabled:
            raise Http404

        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")).split(",")[0].strip()
        if _is_rate_limited(ip):
            return render(request, self.template_name,
                          self._ctx(business, global_error="Too many requests. Please try again later."),
                          status=429)

        calling_code = phonenumbers.country_code_for_region(business.country) or 1
        pos_enabled = business.pos_type != business.POS_NONE and bool(business.pos_api_token)
        errors = {}

        raw_phone = request.POST.get("phone", "").strip()
        phone = ""
        if raw_phone:
            phone, phone_error = _parse_phone(raw_phone, business.country)
            if phone_error:
                errors["phone"] = phone_error

        customer_name = request.POST.get("customer_name", "").strip()

        if pos_enabled and request.POST.get("pos_order_id"):
            # ── POS-confirmed path ───────────────────────────────────────
            pos_order_id = request.POST.get("pos_order_id", "").strip()
            raw_items = request.POST.get("pos_order_items", "[]")
            try:
                pos_order_items = [
                    str(i) for i in _json.loads(raw_items)
                    if isinstance(i, str)
                ]
            except (_json.JSONDecodeError, TypeError):
                pos_order_items = []

            if errors:
                return render(request, self.template_name,
                              self._ctx(business, errors=errors, phone=raw_phone))

            # Use pos_order_id as the display order number for staff dashboard
            order_number = pos_order_id or f"W{slug[:4].upper()}"
            entry = PickupService.register(
                business,
                order_number=order_number,
                customer_name=customer_name,
                phone=phone,
            )
            # Stamp POS data
            entry.pos_order_id = pos_order_id
            entry.pos_order_items = pos_order_items
            entry.pos_match_confidence = None  # already confirmed by customer
            entry.save(update_fields=["pos_order_id", "pos_order_items", "pos_match_confidence"])

        elif pos_enabled:
            # ── POS fallback path (no match / "that's not me") ──────────
            import uuid as _uuid
            if not customer_name:
                errors["customer_name"] = "Please enter your name"
            if errors:
                return render(request, self.template_name,
                              self._ctx(business, errors=errors, phone=raw_phone,
                                        customer_name=customer_name))

            order_number = f"W{_uuid.uuid4().hex[:6].upper()}"
            pickup_intake_fields = business.pickup_intake_fields or []
            intake_answers = {
                q: request.POST.get(f"pickup_intake_{i}", "").strip()
                for i, q in enumerate(pickup_intake_fields)
            }
            entry = PickupService.register(
                business,
                order_number=order_number,
                customer_name=customer_name,
                phone=phone,
                intake_answers=intake_answers,
            )

        else:
            # ── Standard path (no POS) ───────────────────────────────────
            order_number = request.POST.get("order_number", "").strip()
            if not order_number:
                errors["order_number"] = "Please enter your order number"
            if errors:
                return render(request, self.template_name,
                              self._ctx(business, errors=errors,
                                        order_number=order_number,
                                        customer_name=customer_name,
                                        phone=raw_phone))

            pickup_intake_fields = business.pickup_intake_fields or []
            intake_answers = {
                q: request.POST.get(f"pickup_intake_{i}", "").strip()
                for i, q in enumerate(pickup_intake_fields)
            }
            entry = PickupService.register(
                business,
                order_number=order_number,
                customer_name=customer_name,
                phone=phone,
                intake_answers=intake_answers,
            )

        return redirect("customer:pickup_confirmation", slug=slug, entry_id=entry.pk)


class PickupConfirmView(View):
    template_name = "customer/pickup_confirmation.html"

    def get(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(PickupEntry, pk=entry_id, business=business)
        return render(request, self.template_name, {"business": business, "entry": entry})


class PickupCustomerStatusView(View):
    def get(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(PickupEntry, pk=entry_id, business=business)
        return JsonResponse({"status": entry.status})
