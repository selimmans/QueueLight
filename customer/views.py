from django.core.cache import cache
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

import phonenumbers

from businesses.models import Business
from queues.models import QueueEntry
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
        return render(request, self.template_name, {"business": business, "errors": {}})

    def post(self, request, slug):
        business = self._get_business(slug)
        if not business.is_active:
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

        if errors:
            return render(request, self.template_name, {
                "business": business,
                "errors": errors,
                "name": name,
                "phone": raw_phone,
            })

        try:
            entry = QueueService.join(business, name=name, phone=phone)
        except RuleViolationError:
            raise Http404

        return redirect("customer:confirmation", slug=slug, entry_id=entry.pk)


class ConfirmView(View):
    template_name = "customer/confirmation.html"

    def get(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)

        wait_min = wait_max = None
        if business.avg_service_minutes:
            ahead = QueueEntry.objects.filter(
                business=business,
                status=QueueEntry.Status.WAITING,
                position__lt=entry.position,
            ).count()
            if ahead > 0:
                mid = ahead * business.avg_service_minutes
                # ±25 % range, rounded to nearest 5 min
                wait_min = max(1, round(mid * 0.75 / 5) * 5)
                raw_max = round(mid * 1.25 / 5) * 5
                wait_max = max(raw_max, wait_min + 5)

        return render(request, self.template_name, {
            "business": business,
            "entry": entry,
            "wait_min": wait_min,
            "wait_max": wait_max,
        })
