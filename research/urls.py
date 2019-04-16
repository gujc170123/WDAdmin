# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from research.views import ResearchModelListCreateView, ResearchDimensionListCreateAPIView, \
    ResearchSubstandardListCreateAPIView, ResearchModelOpsAPIView, ResearchModelDetailAPIView, \
    ResearchDimensionDetailView, ResearchDimensionCopyCreateAPIView, ResearchSubstandardDetailView, \
    ResearchSubstandardCopyCreateAPIView, TagListCreateAPIView, TagDetailAPIView, \
    ReportListCreateAPIView, ReportDetailView, ReportSurveyListCreateAPIView, ReportSurveyDetailView, \
    ReportSurveyAssessmentProjectListAPIView

urlpatterns = [
    # 新建模型  模型列表
    url(r"^model/$", ResearchModelListCreateView.as_view(), name="model-list-create"),
    # 模型详情修改，获取与删除
    url(r"^model/(?P<pk>\d+)/$", ResearchModelDetailAPIView.as_view(), name="model-detail-view"),
    # 模型的派生与发布
    url(r"^model/ops/$", ResearchModelOpsAPIView.as_view(), name="model-ops-view"),
    # 新建维度  维度列表
    url(r"^dimension/$", ResearchDimensionListCreateAPIView.as_view(), name="dimension-list-create"),
    # 维度修改 删除
    url(r"^dimension/(?P<pk>\d+)/$", ResearchDimensionDetailView.as_view(), name="dimension-detail-view"),
    # 维度拷贝
    url(r"^dimension/copy/$", ResearchDimensionCopyCreateAPIView.as_view(), name="dimension-copy-view"),
    # 新建指标  指标列表
    url(r"^substandard/$", ResearchSubstandardListCreateAPIView.as_view(), name="substandard-list-create"),
    # 指标的删除 更新
    url(r"^substandard/(?P<pk>\d+)/$", ResearchSubstandardDetailView.as_view(), name="substandard-detail-view"),
    # 指标拷贝
    url(r"^substandard/copy/$", ResearchSubstandardCopyCreateAPIView.as_view(), name="substandard-copy-view"),
    # 新建标签, 各个业务模型展示标签
    url(r"^tag/$", TagListCreateAPIView.as_view(), name="tag-list-create"),
    # 标签删除 标签修改
    url(r"^tag/(?P<pk>\d+)/$", TagDetailAPIView.as_view(), name="tag-detail-view"),
    # 新建报告  报告列表
    url(r"^report/$", ReportListCreateAPIView.as_view(), name="report-list-create"),
    # 报告删除 报告修改
    url(r"^report/(?P<pk>\d+)/$", ReportDetailView.as_view(), name="report-detail-view"),
    # 关联问卷 问卷列表
    url(r"^report_survey/$", ReportSurveyListCreateAPIView.as_view(), name="report_survey-list-view"),
    # 问卷删除
    url(r"^report_survey/(?P<pk>\d+)/$", ReportSurveyDetailView.as_view(), name="report-detail-view"),
    # 报告 问卷列表弹框，所有项目的问卷
    url(r"^report/project/survey/$", ReportSurveyAssessmentProjectListAPIView.as_view(), name="report-project-survey-view")

]
