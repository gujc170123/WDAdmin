# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from front.template_views import OpenSurveyJoinView, OpenProjectJoinView, LinkProjectJoinView

urlpatterns = [
    # 加入问卷
    url(r"^join-survey/$", OpenSurveyJoinView.as_view(), name="survey-join-view"),
    # 加入项目
    url(r"^join-project/$", OpenProjectJoinView.as_view(), name="project-join-view"),
    # 个人链接地址
    url(r"^(?P<personal_link>\w+)/$", LinkProjectJoinView.as_view(), name="project-join-view")

]