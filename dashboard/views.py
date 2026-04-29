import io

import qrcode
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views import View

from businesses.models import Business, StaffPhone
from queues.models import QueueEntry, PickupEntry
from queues.pickup_service import PickupService
from queues.services import QueueService, RuleViolationError

SESSION_BUSINESS = "business_id"
SESSION_STAFF = "staff_phone_id"


def _require_superuser(request):
    return request.user.is_authenticated and request.user.is_superuser


def _require_session(request, business: Business) -> bool:
    if _require_superuser(request):
        return True
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
        "intake_answers": entry.intake_answers or {},
    }


class StaffUnifiedLoginView(View):
    template_name = "dashboard/login.html"

    def _businesses_with_codes(self):
        import phonenumbers as _pn
        businesses = Business.objects.filter(is_active=True).order_by("name")
        return [(b, _pn.country_code_for_region(b.country) or 1) for b in businesses]

    def get(self, request):
        if _require_superuser(request):
            return redirect("platform:platform")
        selected = request.GET.get("slug", "")
        return render(request, self.template_name, {
            "businesses_with_codes": self._businesses_with_codes(),
            "selected_slug": selected,
        })

    def post(self, request):
        import phonenumbers as _pn
        slug = request.POST.get("slug", "").strip()
        phone_local = request.POST.get("phone", "").strip()

        def _err(msg):
            return render(request, self.template_name, {
                "businesses_with_codes": self._businesses_with_codes(),
                "selected_slug": slug,
                "error": msg,
            })

        try:
            business = Business.objects.get(slug=slug, is_active=True)
        except Business.DoesNotExist:
            return _err("Please select a business.")

        try:
            parsed = _pn.parse(phone_local, business.country)
            if not _pn.is_valid_number(parsed):
                raise ValueError
            e164 = _pn.format_number(parsed, _pn.PhoneNumberFormat.E164)
        except Exception:
            return _err("Invalid phone number.")

        try:
            staff = StaffPhone.objects.get(phone=e164, business=business)
        except StaffPhone.DoesNotExist:
            return _err("Phone number not recognised.")

        request.session[SESSION_BUSINESS] = business.pk
        request.session[SESSION_STAFF] = staff.pk
        return redirect("dashboard:dashboard", slug=slug)


class StaffLoginView(View):
    def get(self, request, slug):
        return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")

    def post(self, request, slug):
        return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")


class StaffLogoutView(View):
    def get(self, request, slug):
        request.session.pop(SESSION_BUSINESS, None)
        request.session.pop(SESSION_STAFF, None)
        return redirect("dashboard:unified_login")


class DashboardView(View):
    template_name = "dashboard/queue.html"

    def get(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")

        waiting = QueueEntry.objects.filter(
            business=business, status=QueueEntry.Status.WAITING
        ).order_by("position")

        called_entries = QueueEntry.objects.filter(
            business=business, status=QueueEntry.Status.CALLED
        ).order_by("position")

        called_last = called_entries.order_by("-called_at").first()

        pickup_entries = []
        if business.pickup_enabled:
            pickup_entries = list(
                PickupEntry.objects.filter(
                    business=business,
                    status__in=[PickupEntry.Status.WAITING, PickupEntry.Status.READY],
                ).order_by("registered_at")
            )

        # dashboard_mode drives tab visibility in the template
        if business.queue_enabled and business.pickup_enabled:
            dashboard_mode = "both"
        elif business.queue_enabled:
            dashboard_mode = "queue_only"
        elif business.pickup_enabled:
            dashboard_mode = "pickup_only"
        else:
            dashboard_mode = "inactive"

        return render(request, self.template_name, {
            "business": business,
            "waiting": waiting,
            "called_entries": called_entries,
            "called_last": called_last,
            "pickup_entries": pickup_entries,
            "dashboard_mode": dashboard_mode,
        })


class CallNextView(View):
    def post(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")

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
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")

        cache_key = f"qr_png:{slug}"
        png = cache.get(cache_key)
        if png is None:
            join_path = reverse("customer:join", kwargs={"slug": slug})
            join_url = request.build_absolute_uri(join_path)
            png = _build_qr_png(join_url)
            cache.set(cache_key, png, timeout=None)

        return HttpResponse(png, content_type="image/png")


class SettingsView(View):
    template_name = "dashboard/settings.html"

    def _render(self, request, business, error=None, success=None):
        staff_phones = StaffPhone.objects.filter(business=business).order_by("name")
        return render(request, self.template_name, {
            "business": business,
            "staff_phones": staff_phones,
            "error": error,
            "success": success,
            "is_admin": _require_superuser(request),
        })

    def get(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        return self._render(request, business)

    def post(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")

        action = request.POST.get("action", "")

        if action == "save_settings":
            # Batch size
            try:
                batch_size = int(request.POST.get("batch_size", business.batch_size))
                if batch_size >= 1:
                    business.batch_size = batch_size
            except (TypeError, ValueError):
                pass

            # avg_service_minutes
            raw_avg = request.POST.get("avg_service_minutes", "").strip()
            if raw_avg:
                try:
                    business.avg_service_minutes = max(1, int(raw_avg))
                except ValueError:
                    pass
            else:
                business.avg_service_minutes = None

            # SMS template
            sms_template = request.POST.get("sms_template", "").strip()
            if sms_template:
                business.sms_template = sms_template

            menu_url = request.POST.get("menu_url", "").strip()
            business.menu_url = menu_url

            new_type = request.POST.get("business_type", "").strip()
            if new_type in (Business.TYPE_RETAIL, Business.TYPE_CLINIC):
                business.business_type = new_type

            intake_questions = [q.strip() for q in request.POST.getlist("intake_questions") if q.strip()]
            business.intake_fields = intake_questions

            business.save(update_fields=[
                "batch_size", "avg_service_minutes", "sms_template", "menu_url",
                "business_type", "intake_fields",
            ])

        elif action == "save_pickup_sms":
            pickup_msg = request.POST.get("pickup_notification_message", "").strip()
            business.pickup_notification_message = pickup_msg
            business.save(update_fields=["pickup_notification_message"])

        elif action == "save_pickup_intake":
            pickup_questions = [q.strip() for q in request.POST.getlist("pickup_intake_questions") if q.strip()]
            business.pickup_intake_fields = pickup_questions
            business.save(update_fields=["pickup_intake_fields"])

        elif action == "save_pickup_settings":
            # Legacy alias — saves both fields together
            pickup_msg = request.POST.get("pickup_notification_message", "").strip()
            business.pickup_notification_message = pickup_msg
            pickup_questions = [q.strip() for q in request.POST.getlist("pickup_intake_questions") if q.strip()]
            business.pickup_intake_fields = pickup_questions
            business.save(update_fields=["pickup_notification_message", "pickup_intake_fields"])

        elif action == "toggle_queue":
            enable = request.POST.get("queue_enabled") == "1"
            if not enable:
                has_waiting = QueueEntry.objects.filter(
                    business=business, status=QueueEntry.Status.WAITING
                ).exists()
                if has_waiting:
                    return self._render(request, business, error="Cannot disable the queue while customers are waiting.")
            business.queue_enabled = enable
            business.save(update_fields=["queue_enabled"])

        elif action == "toggle_pickup":
            business.pickup_enabled = request.POST.get("pickup_enabled") == "1"
            business.save(update_fields=["pickup_enabled"])

        elif action == "add_staff":
            import phonenumbers as _pn
            raw = request.POST.get("phone", "").strip()
            name = request.POST.get("staff_name", "").strip()
            try:
                parsed = _pn.parse(raw, business.country)
                if not _pn.is_valid_number(parsed):
                    raise ValueError
                e164 = _pn.format_number(parsed, _pn.PhoneNumberFormat.E164)
                StaffPhone.objects.get_or_create(phone=e164, business=business, defaults={"name": name or e164})
            except Exception:
                return self._render(request, business, error="Invalid phone number.")

        elif action == "remove_staff":
            staff_id = request.POST.get("staff_id")
            StaffPhone.objects.filter(pk=staff_id, business=business).delete()

        elif action == "set_mode":
            new_mode = request.POST.get("mode", "")
            if new_mode in (Business.MODE_BATCH, Business.MODE_PERSON):
                try:
                    QueueService.set_mode(business, new_mode)
                except RuleViolationError as e:
                    return self._render(request, business, error=str(e))

        elif action == "closing_soon":
            try:
                QueueService.send_closing_soon_sms(business)
            except Exception:
                pass

        elif action == "reopen":
            business.is_closing = False
            business.save(update_fields=["is_closing"])

        elif action == "clear_queue":
            QueueService.clear_queue(business)

        return redirect("dashboard:settings", slug=slug)


class SkipEntryView(View):
    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)
        try:
            QueueService.skip(entry)
        except RuleViolationError:
            pass
        return redirect("dashboard:dashboard", slug=slug)


class CompleteEntryView(View):
    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)
        try:
            QueueService.complete(entry)
        except RuleViolationError:
            pass
        return redirect("dashboard:dashboard", slug=slug)


class NoShowEntryView(View):
    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        entry = get_object_or_404(QueueEntry, pk=entry_id, business=business)
        try:
            QueueService.no_show(entry)
        except RuleViolationError:
            pass
        return redirect("dashboard:dashboard", slug=slug)


class CompleteBatchView(View):
    def post(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        try:
            showed_up = int(request.POST.get("showed_up", 0))
        except (TypeError, ValueError):
            showed_up = 0
        try:
            QueueService.complete_batch(business, showed_up)
        except RuleViolationError:
            pass
        return redirect("dashboard:dashboard", slug=slug)


# ── Platform (superuser) views ────────────────────────────────────────────────


class PlatformLoginView(View):
    template_name = "dashboard/platform_login.html"

    def get(self, request):
        if _require_superuser(request):
            return redirect("platform:platform")
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user and user.is_superuser:
            login(request, user)
            return redirect("platform:platform")
        return render(request, self.template_name, {"error": "Invalid credentials."})


class PlatformLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("platform:platform_login")


class PlatformDashboardView(View):
    template_name = "dashboard/platform.html"

    def get(self, request):
        if not _require_superuser(request):
            return redirect("platform:platform_login")
        businesses = Business.objects.order_by("name")
        return render(request, self.template_name, {"businesses": businesses})

    def post(self, request):
        if not _require_superuser(request):
            return redirect("platform:platform_login")

        action = request.POST.get("action", "")

        if action == "create_business":
            name = request.POST.get("name", "").strip()
            slug = request.POST.get("slug", "").strip() or slugify(name)
            mode = request.POST.get("mode", Business.MODE_PERSON)
            business_type = request.POST.get("business_type", "retail").strip()
            logo_colour = request.POST.get("logo_colour", "#3B82F6").strip()
            colour_accent = request.POST.get("colour_accent", "#6366f1").strip()
            colour_border = request.POST.get("colour_border", "#e5e7eb").strip()
            country = request.POST.get("country", "CA").strip().upper()
            staff_phone = request.POST.get("staff_phone", "").strip()
            staff_name = request.POST.get("staff_name", "").strip()

            if not name or not slug:
                businesses = Business.objects.order_by("name")
                return render(request, self.template_name, {
                    "businesses": businesses,
                    "error": "Business name and slug are required.",
                })

            if Business.objects.filter(slug=slug).exists():
                businesses = Business.objects.order_by("name")
                return render(request, self.template_name, {
                    "businesses": businesses,
                    "error": f"Slug '{slug}' is already taken.",
                })

            queue_enabled = request.POST.get("queue_enabled", "1") == "1"
            pickup_enabled = request.POST.get("pickup_enabled", "0") == "1"

            business = Business.objects.create(
                name=name,
                slug=slug,
                mode=mode,
                business_type=business_type,
                logo_colour=logo_colour,
                colour_accent=colour_accent,
                colour_border=colour_border,
                country=country,
                queue_enabled=queue_enabled,
                pickup_enabled=pickup_enabled,
                is_active=True,
            )

            if staff_phone:
                import phonenumbers as _pn
                try:
                    parsed = _pn.parse(staff_phone, country)
                    if _pn.is_valid_number(parsed):
                        e164 = _pn.format_number(parsed, _pn.PhoneNumberFormat.E164)
                        StaffPhone.objects.create(
                            phone=e164,
                            business=business,
                            name=staff_name or e164,
                        )
                except Exception:
                    pass

        elif action == "toggle_active":
            biz_id = request.POST.get("business_id")
            biz = get_object_or_404(Business, pk=biz_id)
            biz.is_active = not biz.is_active
            biz.save(update_fields=["is_active"])

        elif action == "delete_business":
            biz_id = request.POST.get("business_id")
            Business.objects.filter(pk=biz_id).delete()

        return redirect("platform:platform")


class PickupReadyView(View):
    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        entry = get_object_or_404(PickupEntry, pk=entry_id, business=business)
        if entry.status == PickupEntry.Status.WAITING:
            PickupService.mark_ready(entry)
        return redirect("dashboard:dashboard", slug=slug)


class PickupPickedUpView(View):
    def post(self, request, slug, entry_id):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        entry = get_object_or_404(PickupEntry, pk=entry_id, business=business)
        if entry.status == PickupEntry.Status.READY:
            PickupService.mark_picked_up(entry)
        return redirect("dashboard:dashboard", slug=slug)


class PickupClosingSoonView(View):
    def post(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        PickupService.send_closing_soon_sms(business)
        return redirect("dashboard:settings", slug=slug)


class PickupClearView(View):
    def post(self, request, slug):
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return redirect(f"{reverse('dashboard:unified_login')}?slug={slug}")
        PickupService.clear_active_orders(business)
        return redirect("dashboard:settings", slug=slug)


class PickupStatusAPIView(View):
    def get(self, request, slug):
        from django.utils import timezone as tz
        business = get_object_or_404(Business, slug=slug)
        if not _require_session(request, business):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        entries = list(
            PickupEntry.objects.filter(
                business=business,
                status__in=[PickupEntry.Status.WAITING, PickupEntry.Status.READY],
            ).order_by("registered_at")
        )
        now = tz.now()

        def _entry_dict(e):
            minutes_waiting = int((now - e.registered_at).total_seconds() / 60)
            return {
                "id": e.pk,
                "order_number": e.order_number,
                "customer_name": e.customer_name,
                "status": e.status,
                "registered_at": e.registered_at.isoformat(),
                "minutes_waiting": minutes_waiting,
                "intake_answers": e.intake_answers or {},
            }

        active_orders = [_entry_dict(e) for e in entries]
        return JsonResponse({"active_orders": active_orders, "total_active": len(active_orders)})


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

        called_entries = list(
            QueueEntry.objects.filter(business=business, status=QueueEntry.Status.CALLED)
            .order_by("position")
        )

        return JsonResponse({
            "waiting": [_entry_to_dict(e) for e in waiting],
            "called": [_entry_to_dict(e) for e in called_entries],
            "called_last": _entry_to_dict(called_last) if called_last else None,
            "mode": business.mode,
            "batch_size": business.batch_size,
            "avg_service_minutes": business.avg_service_minutes,
        })
