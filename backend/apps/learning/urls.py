from django.urls import path

from .views import (
    AllTimeBestView,
    RoundAnswerView,
    RoundFinishView,
    RoundStartView,
    StreakView,
    WeeklyBestView,
)

app_name = "learning"

urlpatterns = [
    path("rounds/", RoundStartView.as_view(), name="round-start"),
    path("rounds/answer/", RoundAnswerView.as_view(), name="round-answer"),
    path("rounds/finish/", RoundFinishView.as_view(), name="round-finish"),
    # 순위표. 셋 다 읽기 전용이라 GET 이다.
    path("leaderboards/weekly/", WeeklyBestView.as_view(), name="leaderboard-weekly"),
    path(
        "leaderboards/all-time/",
        AllTimeBestView.as_view(),
        name="leaderboard-all-time",
    ),
    path("leaderboards/streak/", StreakView.as_view(), name="leaderboard-streak"),
]
