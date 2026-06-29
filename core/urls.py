from django.contrib import admin
from django.urls import include, path
from ninja import NinjaAPI

from blog.api import router as blog_router
from core.health import healthz, readyz

api = NinjaAPI()
api.add_router("/", blog_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    # Health checks for the Kubernetes probes.
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    # /metrics exposed by django-prometheus (RED + DB metrics).
    path("", include("django_prometheus.urls")),
]
