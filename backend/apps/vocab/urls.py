from rest_framework.routers import DefaultRouter

from .views import SentenceViewSet, TalkViewSet, WordViewSet

app_name = "vocab"

router = DefaultRouter()
router.register("words", WordViewSet, basename="word")
router.register("sentences", SentenceViewSet, basename="sentence")
# 소리내어 읽기. 목록·상세·쓰기가 없어 ViewSet 이라 라우터가 만드는
# 경로는 question·grade 둘뿐이다.
router.register("talk", TalkViewSet, basename="talk")

urlpatterns = router.urls
