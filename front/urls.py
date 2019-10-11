# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from front.views import PeopleSurveyListView, PeopleQuestionListView, PeopleBlockQuestionListView, \
    PeopleSurveyReportListView, PeopleLoginView, PeopleRegisterView, UserAnswerQuestionView, OrgInfoView, \
    ProjectAdvertList, PeopleInfoGatherView, UserAccountInfoView, UserOrgInfoView, PeopleLogoutView, \
    PeopleActiveCodeLoginView, PeopleActiveCodeLoginSetPwdView, PeopleSurveyDetailView, PeopleSurveyOpenCheckView, \
    ReportDataView, FinishTxTView, ReportFinishCallback, PeopleLoginOrRegistrerView,BlockStatusView,AnonymousEntryView
# PeopleLinkCodeLoginView
from wduser.views import UserPwdForgetView

urlpatterns = [
    # 登录
    url(r"^login/$", PeopleLoginView.as_view(), name="people-user-login"),
    # 激活码登录
    url(r"^login/active_code/$", PeopleActiveCodeLoginView.as_view(), name="people-user-login-active-code"),
    url(r"^login/active_code/pwd/$", PeopleActiveCodeLoginSetPwdView.as_view(), name="people-user-login-active-code-pwd"),
    # 多账户登陆或注册/针对某个项目
    url(r"^login_register/account_type/$", PeopleLoginOrRegistrerView.as_view(), name="people-login-register"),
    # 退出
    url(r"^logout/$", PeopleLogoutView.as_view(), name="people-user-logout"),
    # 注册
    url(r"^register/$", PeopleRegisterView.as_view(), name="people-user-register"),
    # 忘记密码
    url(r"^forget/pwd/$", UserPwdForgetView.as_view(), name="user-pwd-forget-view"),
    # 帐号信息
    url(r"^userinfo/$", UserAccountInfoView.as_view(), name="user-info-view"),
    # 组织码检查
    url(r"^org/check/$", OrgInfoView.as_view(), name="org-info-check"),
    # 组织查看
    url(r"^orginfo/$", UserOrgInfoView.as_view(), name="user-org-info-view"),
    # 我的测评列表
    url(r"^surveys/$", PeopleSurveyListView.as_view(), name="survey-list-view"),
    url(r"^survey/detail/$", PeopleSurveyDetailView.as_view(), name="survey-detail-view"),
    # 校验问卷
    url(r"^survey/open-check/$", PeopleSurveyOpenCheckView.as_view(), name="survey-open-check-view"),
    # 测评信息收集
    url(r"^surveys/userinfo/$", PeopleInfoGatherView.as_view(), name="people-info-gather-view"),
    # 我的测评 项目中的轮播地址
    url(r"^carousel/$", ProjectAdvertList.as_view(), name="project-advert-list-view"),
    # 我的报告列表
    url(r"^surveys/report/$", PeopleSurveyReportListView.as_view(), name="survey-report-list-view"),
    # 获取题目 块题目，或者整体题目
    url(r"^question/$", PeopleQuestionListView.as_view(), name="question-list-view"),
    # 获取块题目（同时设置问卷为已读） # 弃用
    url(r"^block/question/$", PeopleBlockQuestionListView.as_view(), name="block-question-list-view"),
    # 答题
    url(r"^question/answer/$", UserAnswerQuestionView.as_view(), name="user-answer-view"),
    # 问卷的采集信息列表获取（同时设置问卷为已读）
    #
    ##
    # report 获取数据
    url(r"^report/data/$", ReportDataView.as_view(), name="user-report-data-view"),
    # 报告回掉
    url(r"^report/info/callback/$", ReportFinishCallback.as_view(), name="user-report-callback-view"),
    # 获取项目富文本：
    url(r"^finish/project_info/$", FinishTxTView.as_view(), name="finish-txt-view"),
    # confirm whether all blocks have been finished：
    url(r"^blockstatus/$", BlockStatusView.as_view(), name="block-status-view"),
    # anonymous entry(auto register,login,surveydeliver)
    url(r"^anonymousentry/$",AnonymousEntryView.as_view(), name="anonymous-entry-view"),
]