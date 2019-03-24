# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from survey.views import OrgSurveyListCreateView, OrgSurveyOpsView, OrgSurveyDetailView, \
    SurveyModelFacetQuestionRelationOpsView, SurveyPreviewView, PersonalSurveyListCreateView, PersonalSurveyDetailView, \
    Survey360DetailView, Survey360ListCreateView, SurveyModelFacetOptionRelationOpsView

urlpatterns = [
    # 新建组织问卷，组织问卷列表
    url(r"^org/$", OrgSurveyListCreateView.as_view(), name="survey-list-create"),
    # 问卷修改
    url(r"^org/(?P<pk>\d+)/$", OrgSurveyDetailView.as_view(), name="survey-detail-view"),
    # 新建个人问卷，个人问卷列表
    url(r"^personal/$", PersonalSurveyListCreateView.as_view(), name="survey-list-create-personal"),
    # 个人问卷修改
    url(r"^personal/(?P<pk>\d+)/$", PersonalSurveyDetailView.as_view(), name="survey-detail-view-personal"),
    # 新建组织问卷，组织问卷列表
    url(r"^personal360/$", Survey360ListCreateView.as_view(), name="survey-list-create-360"),
    # 问卷修改
    url(r"^personal360/(?P<pk>\d+)/$", Survey360DetailView.as_view(), name="survey-detail-view"),
    # 问卷发布
    url(r"^ops/$", OrgSurveyOpsView.as_view(), name="survey-ops-view"),
    # 问卷模型构面题目关联
    url(r"^question/relation/$", SurveyModelFacetQuestionRelationOpsView.as_view(), name="survey-ops-view"),
    # 问卷模型构面选项关联
    url(r"^option/relation/$", SurveyModelFacetOptionRelationOpsView.as_view(), name="survey-ops-view"),
    # 迫选组卷预览
    url(r"^question/preview/$", SurveyPreviewView.as_view(), name="survey-preview-view"),

]