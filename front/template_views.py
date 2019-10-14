# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import base64
import random
from urllib import quote
import json
# from django.core.serializers import json
from django.http import HttpResponseRedirect
from rest_framework.response import Response
from django.contrib.auth import logout
from WeiDuAdmin import settings
from assessment.models import AssessSurveyRelation, AssessProject, AssessUser, AssessSurveyUserDistribute, AnonymousEntry
from front.models import PeopleSurveyRelation
from front.tasks import send_one_user_survey
from front.views import people_login
from survey.models import Survey
from utils.logger import err_logger
from utils.response import ErrorCode
from utils.views import WdTemplateView, AuthenticationExceptView
from wduser.models import People, AuthUser
from wduser.user_utils import UserAccountUtils
import uuid


def open_people_assess_survey_user_distribute(assess_id, survey_id, people_id):
    # 项目问卷分发数组
    try:
        a = AssessSurveyUserDistribute.objects.get(assess_id=assess_id, survey_id=survey_id)
        a_list = json.loads(a.people_ids)
        if people_id not in a_list:
            a_list.append(people_id)
            a. people_ids = json.dumps(a_list)
            a.save()
    except:
        a = AssessSurveyUserDistribute.objects.create(assess_id=assess_id, survey_id=survey_id)
        a.people_ids = json.dumps([people_id])
        a.save()


class OpenSurveyJoinView(AuthenticationExceptView, WdTemplateView):
    u"""开放问卷加入"""

    def get(self, request, *args, **kwargs):
        bs = self.request.GET.get("bs", 0)
        ba = self.request.GET.get("ba", 0)
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            # 跳转登录页面
            err_logger.error("user is not is_authenticated")
            return HttpResponseRedirect("/#/login?bs=%s&ba=%s" % (bs, ba))
        survey_id = base64.b64decode(bs)
        assess_id = base64.b64decode(ba)
        try:
            survey = Survey.objects.get(id=survey_id)
        except:
            # 跳转我的测评页面
            err_logger.error("survey id %s is not found" % survey_id)
            return HttpResponseRedirect("/#/")
        relation_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id, survey_id=survey_id)
        if not relation_qs.exists():
            err_logger.error("project(%s) and survey(%s) relation is not found" % (assess_id, survey_id))
            # 跳转我的测评页面
            return HttpResponseRedirect("/#/")
        relation_obj = relation_qs[0]
        if relation_obj.distribute_type == AssessSurveyRelation.DISTRIBUTE_IMPORT:
            err_logger.error("project(%s) survey(%s) is not open" %(assess_id, survey_id))
            # 跳转我的测评页面
            return HttpResponseRedirect("/#/")

        user = self.request.user
        people_qs = People.objects.filter_active(user_id=user.id)
        if people_qs.exists():
            people = people_qs[0]
        else:
            people = People.objects.create(
                user_id=user.id, username=user.nickname, phone=user.phone, email=user.email)
        try:

            PeopleSurveyRelation.objects.create(
                people_id=people.id, survey_id=survey_id, project_id=assess_id,
                survey_name=survey.title
            )
        except:
            pass
        # TODO: 跳转我的测评页面
        return HttpResponseRedirect("/#/")


class OpenProjectJoinView(AuthenticationExceptView, WdTemplateView):
    u"""开放项目加入"""
    template_name = 'join.html'

    def get(self, request, *args, **kwargs):
        bs = 0
        ba = self.request.GET.get("ba", 0)
        assess_id = base64.b64decode(ba)
        try:
            project = AssessProject.objects.get(id=assess_id)
        except:
            # 跳转我的测评页面
            err_logger.error("project id %s is not found" % assess_id)
            # return HttpResponseRedirect("/#/")
            return Response({"err_code": 1})
        if project.distribute_type == AssessSurveyRelation.DISTRIBUTE_IMPORT:
            err_logger.error("project(%s) is not open" % (assess_id))
            return Response({"err_code": 2})

        logout(request)
        return HttpResponseRedirect("/#/login?bs=%s&ba=%s" % (bs, quote(ba)))
        # if not hasattr(request, 'user') or not request.user.is_authenticated:
        #     # 跳转登录页面
        #     err_logger.error("user is not is_authenticated")
        #     return HttpResponseRedirect("/#/login?bs=%s&ba=%s" % (bs, quote(ba)))
        # relation_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id, survey_been_random=False)
        # random_relation_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id, survey_been_random=True).values_list('survey_id', flat=True)
        # random_num = project.survey_random_number
        # if random_num is None:
        #     random_num = 0
        # if len(random_relation_qs) < random_num:
        #     random_num = len(random_relation_qs)
        # if (not relation_qs.exists()) and (not random_relation_qs):
        #     err_logger.error("project(%s) survey relation is not found" % (assess_id))
        #     # 跳转我的测评页面
        #     return HttpResponseRedirect("/#/")
        # user = self.request.user
        # people_qs = People.objects.filter_active(user_id=user.id)
        # if people_qs.exists():
        #     people = people_qs[0]
        # else:
        #     people = People.objects.create(
        #         user_id=user.id, username=user.nickname, phone=user.phone, email=user.email)
        # try:
        #     send_one_user_survey(assess_id, people.id)
        # except Exception, e:
        #     err_logger.error("add people to project error, %s, %s" %(people.id, assess_id))
        # # TODO: 跳转我的测评页面
        # return HttpResponseRedirect("/#/")

class OpenJoinView(AuthenticationExceptView, WdTemplateView):
    u"""开放项目加入"""
    template_name = 'join.html'

    def get(self, request, *args, **kwargs):
        bs = 0
        ba = self.request.GET.get("ba", 0)
        assess_id = base64.b64decode(ba)
        try:
            project = AssessProject.objects.get(id=assess_id)
        except:
            # 跳转我的测评页面
            err_logger.error("project id %s is not found" % assess_id)
            # return HttpResponseRedirect("/#/")
            return Response({"err_code": 1})
        if project.distribute_type == AssessSurveyRelation.DISTRIBUTE_IMPORT:
            err_logger.error("project(%s) is not open" % (assess_id))
            return Response({"err_code": 2})
        
        relation_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id, survey_been_random=False)
        random_relation_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id, survey_been_random=True).values_list('survey_id', flat=True)
        random_num = project.survey_random_number
        if random_num is None:
            random_num = 0
        if len(random_relation_qs) < random_num:
            random_num = len(random_relation_qs)
        if (not relation_qs.exists()) and (not random_relation_qs):
            err_logger.error("project(%s) survey relation is not found" % (assess_id))
            # 跳转我的测评页面
            return HttpResponseRedirect("/#/")

        user, code = UserAccountUtils.user_register(
            pwd, username=str(uuid.uuid4()), phone='', email='', role_type=AuthUser.ROLE_NORMAL)

        people = People.objects.create(
            user_id=user.id, username=user.nickname, phone=user.phone, email=user.email)
            
        try:
            send_one_user_survey(assess_id, people.id)
        except Exception, e:
            err_logger.error("add people to project error, %s, %s" %(people.id, assess_id))
        # TODO: 跳转我的测评页面
        return HttpResponseRedirect("/#/")

class LinkProjectJoinView(AuthenticationExceptView, WdTemplateView):
    # 个人链接登陆
    template_name = 'join.html'
    def get(self, request, *args, **kwargs):
        try:
            link = request.parser_context['kwargs']["personal_link"]
            if not link:
                return Response({"err_code": 3})
            authuser_obj = AuthUser.objects.get(dedicated_link=link, is_active=True)
        except:
            err_logger.error("link %s is not found" % link)
            return Response({"err_code": 4})
        people_qs = People.objects.filter_active(user_id=authuser_obj.id)
        if not people_qs.exists():
            return Response({"err_code": 5})
        authuser_obj, err_code = UserAccountUtils.user_login_web_without_pwd(request, authuser_obj)
        user_info = people_login(request, authuser_obj, self.get_serializer_context())
        email = user_info["email"]
        if not email:
            email = ''
        phone = user_info["phone"]
        if not phone:
            phone = ''
        account_name = user_info["account_name"]
        if not account_name:
            account_name = ''
        # user_info = json.dumps(user_info)
        response = HttpResponseRedirect('/#/')
        response.set_cookie('email', email)
        response.set_cookie('phone', phone)
        response.set_cookie('account_name', account_name)
        if err_code == ErrorCode.SUCCESS:
            return response
        elif err_code == ErrorCode.USER_HAS_LOGIN_ERROR or ErrorCode.USER_PWD_ERROR:
            return Response({"err_code": 7})
        else:
            return Response({"err_code": 6})

class AnonymousJoinView(AuthenticationExceptView, WdTemplateView):
    u"""Anonymous Join"""
    template_name = 'join.html'

    def get(self, request, *args, **kwargs):
        bs = 0
        ba = self.request.GET.get("ba", 0)
        assess_id = base64.b64decode(ba)

        logout(request)

        project = AssessProject.objects.filter_active(id=assess_id).first()
        if not project:
            err_logger.error("project id %s is not found" % assess_id)
            return Response({"err_code": 1})
        if project.distribute_type != AssessProject.DISTRIBUTE_ANONYMOUS:
            err_logger.error("project(%s) is forbidden for anonymous assess" % (assess_id))
            return Response({"err_code": 2})
        entry = AnonymousEntry.objects.filter_active(enterprise_id=project.enterprise_id).first()
        if not entry:
            entry = AnonymousEntry.objects.filter_active(enterprise_id=0).first()
        if not entry:        
            err_logger.error("no entry available")
            return Response({"err_code": 2})                
        url = entry.routine

        return HttpResponseRedirect("/#/%s/" % url)