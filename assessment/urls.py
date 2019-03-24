# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from assessment.views import AssessmentListCreateView, AssessRetrieveUpdateDestroyView, AssessSurveyRelationView, \
    AssessGatherInfoView, AssessProjectSurveyConfigView, AssessGatherInfoDetailView, AssessSurveyRelationDetailView, \
    AssessSurveyImportExportView, AssessUserListView, AssessSurveyRelationDistributeView, AssessSurveyUserExport, \
    Assess360UserListView, Assess360UserCopyView, Assess360TestUserStatisticsView, Assess360SurveyRelation, \
    DownloadReportView, AssessUserCreateView, AssessGatherAllInfoView, AssessUseDetailView, Assess360UpuserImportView

urlpatterns = [
    # 项目新建 项目 列表
    url(r"^project/$", AssessmentListCreateView.as_view(), name="assessment-view"),
    # 项目详情 项目修改  项目删除
    url(r"^project/(?P<pk>\d+)/$", AssessRetrieveUpdateDestroyView.as_view(), name="project-view-detail"),
    # 组织项目 个人项目  360项目 关联问卷
    url(r"^project/survey/relation/$", AssessSurveyRelationView.as_view(), name="project-survey-relation"),
    # 项目问卷设置
    url(r"^project/survey/relation/(?P<pk>\d+)/$", AssessSurveyRelationDetailView.as_view(), name="project-survey-relation-detail"),
    # 项目问卷分发信息
    url(r"^project/survey/relation/distribute/info/(?P<pk>\d+)/$", AssessSurveyRelationDistributeView.as_view(), name="project-survey-relation-distribute"),
    url(r"^project/distribute/info/$", AssessSurveyRelationDistributeView.as_view(), name="project-survey-relation-distribute"),
    # 项目问卷人员导出
    url(r"^project/survey/user/export/$", AssessSurveyUserExport.as_view(), name="project-survey-user-export"),
    # 收集信息设置
    url(r"^project/gather/info/$", AssessGatherInfoView.as_view(), name="project-survey-relation"),
    url(r"^project/gather/info/all/$", AssessGatherAllInfoView.as_view(), name="project-survey-relation-all"),
    # 信息修改 删除
    url(r"^project/gather/info/(?P<pk>\d+)/$", AssessGatherInfoDetailView.as_view(), name="project-survey-relation-detail"),
    # 自定义配置
    url(r"^project/survey/config/$", AssessProjectSurveyConfigView.as_view(), name="project-survey-config-view"),
    # 项目人员导入
    url(r"^project/user/import/$", AssessSurveyImportExportView.as_view(), name="project-user-import-view"),
    # 项目人员新增
    url(r"^project/user_create/$", AssessUserCreateView.as_view(), name="project-user-view"),
    # 项目人员列表 批量删除 新增
    url(r"^project/user/$", AssessUserListView.as_view(), name="project-user-view"),
    # 项目人员的修改
    url(r"^project/user/(?P<pk>\d+)/$", AssessUseDetailView.as_view(), name="project-user-view"),
    # 360 上级人员导入
    url(r"^project360/upuser/import/$", Assess360UpuserImportView.as_view(), name="project360-upuser-import-view"),
    # 360项目人员列表与设置
    url(r"^project360/user/$", Assess360UserListView.as_view(), name="project360-user-view"),
    # 360项目人员拷贝
    url(r"^project360/user/copy/$", Assess360UserCopyView.as_view(), name="project360-user-copy-view"),
    # 360项目被评价人员类别与统计
    url(r"^project360/user/statistics/$", Assess360TestUserStatisticsView.as_view(), name="project360-user-statistics-view"),
    # 360问卷设置
    url(r"^project360/survey/$", Assess360SurveyRelation.as_view(), name="project360-survey-relation-view"),
    # 报告下载
    url(r"^project/report/download/$", DownloadReportView.as_view(), name="project-report-download-view"),
]