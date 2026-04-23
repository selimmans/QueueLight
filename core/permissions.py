"""Business scoping helpers for Queue Light.

All queryset scoping logic lives here so views stay thin and isolation rules
can be tested in one place.

Access model:
  - Platform admin (is_staff or is_superuser) → sees all data
  - Staff session (session has business_id) → scoped to that business only
  - Unauthenticated → customer-facing public endpoints only

Detail views return 404 (not 403) on cross-business access to avoid leaking
whether a record exists.
"""

from __future__ import annotations

from django.http import Http404


def get_session_business_id(request) -> int | None:
    """Return the business_id stored in the current staff session, or None."""
    return request.session.get("business_id")


def is_platform_admin(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.is_staff))


def scope_to_business(queryset, business_id: int):
    """Filter queryset to a single business."""
    return queryset.filter(business_id=business_id)


def assert_business_access(obj_business_id: int, session_business_id: int | None) -> None:
    """Raise Http404 if the session does not have access to this business.

    Never raises 403 — 403 reveals the record exists. Http404 leaks nothing.
    """
    if session_business_id is None:
        raise Http404
    if obj_business_id != session_business_id:
        raise Http404
