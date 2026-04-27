from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

import phonenumbers

from businesses.models import Business
from queues.models import QueueEntry, QueueEventLog
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


class JoinView(View):
    template_name = "customer/join.html"

    def _get_business(self, slug):
        return get_object_or_404(Business, slug=slug)

    def get(self, request, slug):
        business = self._get_business(slug)
        if not business.is_active:
            raise Http404
        calling_code = phonenumbers.country_code_for_region(business.country) or 1
        waiting_count = QueueEntry.objects.filter(
            business=business, status=QueueEntry.Status.WAITING
        ).count()
        wait_min, wait_max = _wait_range(business, waiting_count)
        ctx = {"business": business, "errors": {}, "calling_code": calling_code,
               "waiting_count": waiting_count, "wait_min": wait_min, "wait_max": wait_max}
        if business.is_closing:
            ctx["closing_message"] = f"{business.name} is closing soon and is no longer accepting new customers."
        return render(request, self.template_name, ctx)

    def post(self, request, slug):
        business = self._get_business(slug)
        if not business.is_active:
            raise Http404
        if business.is_closing:
            raise Http404

        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")).split(",")[0].strip()
        if _is_rate_limited(ip):
            return render(request, self.template_name, {
                "business": business,
                "errors": {},
                "global_error": "Too many requests. Please try again later.",
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


class LeaveQueueView(View):
    """Customer voluntarily leaves the queue."""

    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)

        if entry.status in (QueueEntry.Status.WAITING, QueueEntry.Status.CALLED):
            QueueService.abandon(entry)

        return redirect("customer:join", slug=slug)


_VALID_RESPONSES = {"late_arrival", "left_other", "left_home"}


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
