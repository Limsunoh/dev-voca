from django.urls import path

from .views import RoundAnswerView, RoundFinishView, RoundStartView

app_name = "learning"

urlpatterns = [
    path("rounds/", RoundStartView.as_view(), name="round-start"),
    path("rounds/answer/", RoundAnswerView.as_view(), name="round-answer"),
    path("rounds/finish/", RoundFinishView.as_view(), name="round-finish"),
]
