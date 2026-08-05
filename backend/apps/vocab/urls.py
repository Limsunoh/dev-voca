from rest_framework.routers import DefaultRouter

from .views import SentenceViewSet, WordViewSet

app_name = "vocab"

router = DefaultRouter()
router.register("words", WordViewSet, basename="word")
router.register("sentences", SentenceViewSet, basename="sentence")

urlpatterns = router.urls
