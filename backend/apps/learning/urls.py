from django.urls import path

from .views import (
    AllTimeBestView,
    DailyStudyAnswerView,
    DailyStudyStartView,
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
    # 일일공부. 하루 한 번이라 시작·답하기 둘뿐이고 끝내기가 없다 -
    # 마지막 문제를 풀면 서버가 닫는다.
    path("daily/", DailyStudyStartView.as_view(), name="daily-study"),
    path("daily/answer/", DailyStudyAnswerView.as_view(), name="daily-study-answer"),
]
