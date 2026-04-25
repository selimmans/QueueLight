import io

import qrcode
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from businesses.models import Business, StaffPhone
from queues.models import QueueEntry
from queues.services import QueueService, RuleViolationError

SESSION_BUSINESS = "business_id"
SESSION_STAFF = "staff_phone_id"


def _require_session(request, business: Business) -> bool:
    return (
        request.session.get(SESSION_BUSINESS) == business.pk
        and request.session.get(SESSION_STAFF) is not None
    )


def _entry_to_dict(entry: QueueEntry) -> dict:
    return {
        "id": entry.pk,
        "name": entry.name,
        "position": entry.position,
        "batch_number": entry.batch_number,
        "status": entry.status,
        "joined_at": entry.joined_at.isoformat(),
    }


class StaffLoginView(View):
    template_name = "dashboard/login.html"

    def get(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        return render(request, self.template_name, {"business": business})

    def post(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        phone_raw = request.POST.get("phone", "").strip()

        try:
            staff = StaffPhone.objects.get(phone=phone_raw, business=business)
        except StaffPhone.DoesNotExist:
            return render(
                request,
                self.template_name,
                {"business": business, "error": "Phone number not recognised."},
            )

        request.session[SESSION_BUSINESS] = business.pk
        request.session[SESSION_STAFF] = staff.pk
        return redirect("dashboard:dashboard", slug=slug)


class StaffLogoutView(View):
    def get(self, request, slug):
        request.session.pop(SESSION_BUSINESS, None)
        request.session.pop(SESSION_STAFF, None)
        return redirect("dashboard:login", slug=slug)


class DashboardView(View):
    template_name = "dashboard/queue.html"

    def get(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect("dashboard:login", slug=slug)

        waiting = QueueEntry.objects.filter(
            business=business, status=QueueEntry.Status.WAITING
        ).order_by("position")

        called_last = (
            QueueEntry.objects.filter(business=business, status=QueueEntry.Status.CALLED)
            .order_by("-called_at")
            .first()
        )

        return render(request, self.template_name, {
            "business": business,
            "waiting": waiting,
            "called_last": called_last,
        })


class CallNextView(View):
    def post(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect("dashboard:login", slug=slug)

        try:
            QueueService.call_next(business)
        except RuleViolationError:
            pass  # empty queue — redirect back without crashing

        return redirect("dashboard:dashboard", slug=slug)


def _build_qr_png(url: str) -> bytes:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class QRCodeView(View):
    """Return a QR code PNG for the customer join page.

    Generated once and cached permanently — the URL never changes for a slug.
    """

    def get(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect("dashboard:login", slug=slug)

        cache_key = f"qr_png:{slug}"
        png = cache.get(cache_key)
        if png is None:
            join_path = reverse("customer:join", kwargs={"slug": slug})
            join_url = request.build_absolute_uri(join_path)
            png = _build_qr_png(join_url)
            cache.set(cache_key, png, timeout=None)

        return HttpResponse(png, content_type="image/png")


class QueueStatusAPIView(View):
    def get(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        waiting = list(
            QueueEntry.objects.filter(
                business=business, status=QueueEntry.Status.WAITING
            ).order_by("position")
        )

        called_last = (
            QueueEntry.objects.filter(business=business, status=QueueEntry.Status.CALLED)
            .order_by("-called_at")
            .first()
        )

        return JsonResponse({
            "waiting": [_entry_to_dict(e) for e in waiting],
            "called_last": _entry_to_dict(called_last) if called_last else None,
            "mode": business.mode,
            "batch_size": business.batch_size,
            "avg_service_minutes": business.avg_service_minutes,
        })
