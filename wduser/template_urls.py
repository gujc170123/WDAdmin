# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from wduser.template_views import SurveyAnswerCheckView, answer_check_rst, answer_reset, OperationIndexView, \
    ScoreCheckView, ScoreCheckRstView, ScoreCheckRstResetView

urlpatterns = [
    #
    url(r"^$", OperationIndexView.as_view(), name="operation-index-view"),
    # 检查用户答题情况
    url(r"^answer/check/$", SurveyAnswerCheckView.as_view(), name="answer-check-view"),
    url(r"^answer/check/rst/$", answer_check_rst, name="answer-check-rst-view"),
    url(r"^answer/check/ops/reset/$", answer_reset, name="answer-check-reset-view"),
    # 重新算分
    url(r"^score/check/$", ScoreCheckView.as_view(), name="answer-check-view"),
    url(r"^score/check/rst$", ScoreCheckRstView.as_view(), name="answer-check-rst-view"),
    url(r"^score/check/rst/reset/$", ScoreCheckRstResetView.as_view(), name="answer-check-rst-reset-view"),

]