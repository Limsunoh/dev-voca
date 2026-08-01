from rest_framework.routers import DefaultRouter

from .views import WordViewSet

app_name = "vocab"

router = DefaultRouter()
router.register("words", WordViewSet, basename="word")

urlpatterns = router.urls
