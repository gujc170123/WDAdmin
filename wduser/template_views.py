# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import base64
import random
from urllib import quote
import json
# from django.core.serializers import json
import datetime
from django.http import HttpResponseRedirect
from django.shortcuts import render
from rest_framework.response import Response

from assessment.models import AssessSurveyRelation, AssessProject, AssessUser, AssessSurveyUserDistribute
from front.models import PeopleSurveyRelation, SurveyInfo, UserQuestionAnswerInfo
from front.serializers import PeopleSurveyResultSimpleSerializer
from front.tasks import algorithm_task
from front.views import people_login
from survey.models import Survey
from utils.logger import get_logger
from utils.response import ErrorCode
from utils.views import WdTemplateView, AuthenticationExceptView
from wduser.models import People, AuthUser
from wduser.user_utils import UserAccountUtils

logger = get_logger("operation")


class SurveyAnswerCheckView(AuthenticationExceptView, WdTemplateView):
    # 问卷答题检查页面
    template_name = 'answer_check.html'


class OperationIndexView(AuthenticationExceptView, WdTemplateView):
    # 问卷答题检查页面
    template_name = 'ops_index.html'


def answer_check_rst(request):
    ctx = []
    if request.POST:
        account_name = request.POST['account_name']
        project_name = request.POST['project_name']
        project_ids = list(AssessProject.objects.filter_active(name=project_name).values_list("id", flat=True))
        uids = AuthUser.objects.filter(account_name=account_name).values_list("id", flat=True)
        pids = list(People.objects.filter(user_id__in=uids).values_list("id", flat=True))
        qs = PeopleSurveyRelation.objects.filter_active(
            people_id__in=pids, project_id__in=project_ids
        )
        if not qs.exists():
            print "not found join info"
        for o in qs:
            survey_infos = SurveyInfo.objects.filter_active(project_id=o.project_id, survey_id=o.survey_id)
            if survey_infos.exists():
                survey_info = survey_infos[0]
                has_submit = UserQuestionAnswerInfo.objects.filter_active(
                    people_id=o.people_id, survey_id=o.survey_id, project_id=o.project_id).exists()
                ctx.append({
                    "id": o.id,
                    "survey_name": survey_info.survey_name,
                    "project_name": survey_info.project_name,
                    "status": o.status_name,
                    "begin_answer_time": o.begin_answer_time,
                    "finish_time": o.finish_time,
                    "is_overtime": o.is_overtime,
                    "has_submit": has_submit
                })
        return render(request, 'answer_check_rst.html', {"result": ctx, "account_name": account_name})


def answer_reset(request):
    ctx = []
    if request.POST:
        account_name = request.POST['account_name']
        relation_id = request.POST['relation_id']
        o = PeopleSurveyRelation.objects.get(id=relation_id)
        o.status = 10
        o.begin_answer_time = None
        o.finish_time = None
        o.is_overtime = False
        o.save()
        survey_infos = SurveyInfo.objects.filter_active(project_id=o.project_id, survey_id=o.survey_id)
        if survey_infos.exists():
            survey_info = survey_infos[0]
            has_submit = UserQuestionAnswerInfo.objects.filter_active(
                people_id=o.people_id, survey_id=o.survey_id, project_id=o.project_id).exists()
            ctx.append({
                "id": o.id,
                "survey_name": survey_info.survey_name,
                "project_name": survey_info.project_name,
                "status": o.status_name,
                "begin_answer_time": o.begin_answer_time,
                "finish_time": o.finish_time,
                "is_overtime": o.is_overtime,
                "has_submit": has_submit
            })
        return render(request, 'answer_reset_rst.html', {"result": ctx, "account_name": account_name})


class ScoreCheckView(AuthenticationExceptView, WdTemplateView):
    # 问卷答题检查页面
    template_name = 'score_check.html'

    def get(self, request, *args, **kwargs):
        now = datetime.datetime.now()
        end_time = now - datetime.timedelta(days=7)
        projects = AssessProject.objects.filter_active(begin_time__lt=now, end_time__gt=end_time)
        infos = list(projects.values("name", "id"))
        return Response({"infos": infos})


class ScoreCheckRstView(AuthenticationExceptView, WdTemplateView):
    # 问卷答题检查页面
    template_name = 'score_check_rst.html'

    def get(self, request, *args, **kwargs):
        project_id = request.GET.get("pid", None)
        reset = request.GET.get("reset", 0)
        if not project_id:
            return Response()
        result_qs = PeopleSurveyRelation.objects.filter_active(
            project_id=project_id,
            status=PeopleSurveyRelation.STATUS_FINISH,
            dimension_score__isnull=True
        ).order_by('people_id')
        result_data = PeopleSurveyResultSimpleSerializer(instance=result_qs, many=True).data
        return Response({"infos": result_data, "count": len(result_data), "project_id": project_id, "reset": int(reset)})


class ScoreCheckRstResetView(AuthenticationExceptView, WdTemplateView):
    # 问卷答题检查页面
    template_name = 'score_check_rst.html'

    def post(self, request, *args, **kwargs):
        project_id = request.data.get("project_id", None)
        result_qs = PeopleSurveyRelation.objects.filter_active(
            project_id=project_id,
            status=PeopleSurveyRelation.STATUS_FINISH,
            model_score=0
        ).order_by('people_id')
        for o in result_qs:
            algorithm_task(o.id)
        return HttpResponseRedirect("/operation/score/check/rst?pid=%s&reset=1" % project_id)