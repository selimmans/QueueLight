from django.db import connection
from django.http import JsonResponse
from django.views import View


class HealthCheckView(View):
    """
    Public endpoint for load balancer and uptime monitoring.
    Returns 200 when healthy, 503 when database is unreachable.
    No authentication required.
    """
    def get(self, request):
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception:
            db_ok = False

        payload = {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "unreachable",
        }
        return JsonResponse(payload, status=200 if db_ok else 503)
