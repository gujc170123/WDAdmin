# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from .views import SurveyOverviewListView, CleanTaskDetailView, EscapeTaskListCreateView, SignalView, \
    CleanTaskListCreateView, EscapeTaskDetailView, AnalysisTaskListCreateView, AnalysisTaskDetailView, \
    TrialCleanTaskListCreateView, QuestionFacetListView, SurveyModelFacetQuestionRelationOpsView


urlpatterns = [
    # 总揽表创建和显示
    url(r"^overview/$", SurveyOverviewListView.as_view(), name="overview-create-list"),
    # 总揽表检索与更新
    # url(r"^overview/(?P<pk>\d+)/$", SurveyOverviewRetrieveUpdateView.as_view(), name="overview-update-detail"),
    url(r"^trial/$", TrialCleanTaskListCreateView.as_view(), name="trial_clean_task"),
    # 清洗任务创建和列表
    url(r"^clean/$", CleanTaskListCreateView.as_view(), name="clean-task"),
    # 清洗任务详情与更新
    url(r"^clean/(?P<pk>\d+)/$", CleanTaskDetailView.as_view(), name="clean-task-detail"),
    # 转义任务create与list
    url(r"^escape/$", EscapeTaskListCreateView.as_view(), name="escape-task-create-list"),
    # 转义任务详情与更新
    url(r"^escape/(?P<pk>\d+)/$", EscapeTaskDetailView.as_view(), name="escape-task-detail"),
    # 解析任务创建与列表
    url(r"^analysis/$", AnalysisTaskListCreateView.as_view(), name="analysis-task-create-list"),
    # 解析任务与更新
    url(r"^analysis/(?P<pk>\d+)/$", AnalysisTaskDetailView.as_view(), name="analysis-detail"),
    # 停止 开始 接口 post方法
    url(r"^send_signal/$", SignalView.as_view(), name="send_signal"),
    # 获取任务对应的构面
    url(r"^facet/$", QuestionFacetListView.as_view(), name="get_facet"),
    # 问卷模型构面题目关联
    url(r"^question/relation/$", SurveyModelFacetQuestionRelationOpsView.as_view(), name="survey-ops-view"),
]