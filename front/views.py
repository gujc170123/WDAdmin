# -*- coding:utf-8 -*-
from __future__ import unicode_literals

# Create your views here.
import base64
import json
import random

import datetime

import operator
import time

from django.contrib.auth import logout
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from rest_framework import status

from WeiDuAdmin import settings
from assessment.models import AssessOrganization, AssessUser, AssessSurveyUser, AssessSurveyOrganization, AssessProject, \
    AssessGatherInfo, AssessSurveyRelation, AssessSurveyUserDistribute
from assessment.serializers import AssessGatherInfoSerializer, AssessmentBasicSerializer
from front.front_utils import SurveyAlgorithm
from front.models import PeopleSurveyRelation, SurveyQuestionInfo, SurveyInfo, UserQuestionInfo, UserQuestionAnswerInfo, \
    UserSurveyBlockStatus, UserProjectSurveyGatherInfo
from front.serializers import PeopleSurveySerializer, SurveyQuestionInfoSerializer, UserQuestionInfoSerializer
from front.tasks import survey_question_sync, user_get_survey_ops, get_report, check_survey_open, algorithm_task, \
    send_one_user_survey
from question.models import Question
from research.models import ResearchModel, ResearchSubstandard, ResearchDimension
from survey.models import Survey
from utils import time_format3, time_format4, time_format5, get_random_int, get_random_char
from utils.cache.cache_utils import VerifyCodeExpireCache
from utils.logger import info_logger, err_logger, debug_logger
from utils.rpc_service.report_service import ReportService
from utils.regular import RegularUtils
from utils.response import ErrorCode, general_json_response
from utils.views import WdListCreateAPIView, WdListAPIView, WdCreateAPIView, AuthenticationExceptView, \
    WdRetrieveUpdateAPIView, WdRetrieveAPIView
from wduser.models import AuthUser, People, PeopleOrganization, Organization, EnterpriseInfo, EnterpriseAccount, \
    PeopleAccount
from wduser.serializers import UserBasicSerializer, OrganizationBasicSerializer
from wduser.user_utils import UserAccountUtils
from utils.math_utils import normsdist
from django.db import connection
import numpy as np


def str_check(str_obj):
    if type(str_obj) == int or type(str_obj) == long:
        str_obj = str(long(str_obj))
    elif type(str_obj) == float:
        str_obj = str(long(str_obj))
    return str_obj


def people_login(request, user, context):
    user_info = UserBasicSerializer(instance=user, context=context).data
    return user_info


# 9.13
def get_user_with_assess_id_and_account_name_qs(assess_qs_ids, user_qs):
    #
    for assess_qs_id in assess_qs_ids:
        all_people_id = AssessUser.objects.filter_active(assess_id=assess_qs_id).values_list('people_id', flat=True).distinct()
        all_people = People.objects.filter_active(id__in=all_people_id).values_list('user_id', flat=True).distinct()
        all_user = AuthUser.objects.filter(id__in=all_people).values_list('id', flat=True).distinct()
        if all_user.count() < 1:
            continue
        else:
            id_user_list = list(all_user)  # 企业下项目下的所有user_id
            id_account_name_list = user_qs.values_list('id', flat=True)  # acount_name 下找到的所有user_id:
        for account_name_id in id_account_name_list:
            if account_name_id in id_user_list:
                return ErrorCode.SUCCESS, u"ok", AuthUser.objects.get(id=account_name_id)
    return ErrorCode.ENTERPRISE_USER_ERROR, u'用户不在这个企业中', None


def link_login(link, account, pwd):
    enterprise_qs = EnterpriseInfo.objects.filter_active(enterprise_dedicated_link=link)
    if enterprise_qs.count() != 1:
        return ErrorCode.ENTERPRISE_LINK_ERROR, u'企业专属链接有误', None
    assess_qs_ids = AssessProject.objects.filter_active(enterprise_id=enterprise_qs[0].id).values_list('id', flat=True)
    if assess_qs_ids.count() < 1:
        return ErrorCode.ENTERPRISE_ASSESS_NONE_ERROR, u'企业没有项目', None
    # 这个account,能匹配到的所有用户
    all_user_want_login_all = AuthUser.objects.filter(Q(phone=account) | Q(email=account) | Q(account_name=account))
    all_user_want_login = all_user_want_login_all.filter(is_active=True)
    if all_user_want_login.count() == 0:
        return ErrorCode.USER_ACCOUNT_NOT_FOUND, u'找不到该用户', None
    # 找到企业下所有的AuthUser
    all_people_ids = AssessUser.objects.filter_active(assess_id__in=assess_qs_ids).values_list("people_id", flat=True).distinct()
    for user_want_login_obj in all_user_want_login:
        # 企业下的所有人和想登陆的人中能够在people中找到同一个
        if People.objects.filter_active(user_id=user_want_login_obj.id, id__in=all_people_ids).exists():
            return ErrorCode.SUCCESS, u"ok", user_want_login_obj
    return ErrorCode.ENTERPRISE_USER_ERROR, '企业下找不到该用户', None


class PeopleLoginView(AuthenticationExceptView, WdCreateAPIView):
    u"""
    测验用户登录
    两种登录方式
    1. 手机邮箱+密码+账户
    """
    def find_user_with_account(self, account, account_type=None):
        if account_type:
            pa_p_qs = PeopleAccount.objects.filter_active(account_value=account, account_type=account_type).values_list("people_id", flat=True).distinct()
        else:
            pa_p_qs = PeopleAccount.objects.filter_active(account_value=account).values_list("people_id", flat=True).distinct()
        if pa_p_qs.count() == 1:
            try:
                user_id = People.objects.get(id=pa_p_qs[0]).user_id
                user_obj = AuthUser.objects.get(id=user_id)
                return ErrorCode.SUCCESS, user_obj
            except:
                info_logger.info("peopke_id can not find people user obj")
                pass
        return ErrorCode.FAILURE, None

    def post(self, request, *args, **kwargs):
        link = request.data.get('enterprise_dedicated_link', None)
        account = request.data.get('account', None)
        pwd = request.data.get("pwd", None)
        assess_id_base64 = self.request.data.get("ba", None)
        if account is None or pwd is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        if True:
            if not link:
                user, err_code = UserAccountUtils.account_check(account)
                if err_code != ErrorCode.SUCCESS:
                    return general_json_response(status.HTTP_200_OK, err_code)
            else:
                ret, msg, user = link_login(link, account, pwd)
                if ret != ErrorCode.SUCCESS:
                    return general_json_response(status.HTTP_200_OK, ret, {'msg': msg})
        user, err_code = UserAccountUtils.user_login_web(request, user, pwd)

        enterprise = 0
        if assess_id_base64:
            assess_id = base64.b64decode(assess_id_base64)
            try:                
                project = AssessProject.objects.get(id=assess_id)
                enterprise = project.enterprise_id
            except:
                err_logger.error("project not found: %s" % assess_id)
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)

        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        user_info = people_login(request, user, self.get_serializer_context())
        user_info['enteprise'] = enterprise
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)

class PeopleActiveCodeLoginView(AuthenticationExceptView, WdCreateAPIView):
    u"""激活码登录"""
    POST_CHECK_REQUEST_PARAMETER = ('active_code', 'account')

    def post(self, request, *args, **kwargs):
        phone = email = None
        if RegularUtils.phone_check(self.account):
            phone = self.account
            people_qs = People.objects.filter_active(phone=self.account)
        elif RegularUtils.email_check(self.account):
            email = self.account
            people_qs = People.objects.filter_active(email=self.account)
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_FOUND)
        if not people_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_FOUND)
        people_qs = people_qs.filter(active_code=self.active_code, active_code_valid=True)
        if not people_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACTIVE_CODE_INVALID)
        user_qs = None
        if phone:
            user_qs = AuthUser.objects.filter(is_active=True, phone=phone)
        elif email:
            user_qs = AuthUser.objects.filter(is_active=True, email=email)
        if user_qs.exists():
            # 存在关联的帐号，不需要设置密码，直接登录进去
            user = user_qs[0]
            user, err_code = UserAccountUtils.user_login_web_without_pwd(request, user)
            user_info = people_login(request, user, self.get_serializer_context())
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
                'login': True, 'user_info': user_info, "login_account": self.account
            })
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
                'login': False
            })


class PeopleActiveCodeLoginSetPwdView(AuthenticationExceptView, WdCreateAPIView):
    u"""激活码设置密码"""
    POST_CHECK_REQUEST_PARAMETER = ('active_code', 'account', 'pwd')

    def post(self, request, *args, **kwargs):
        phone = email = None
        if RegularUtils.phone_check(self.account):
            phone = self.account
            people_qs = People.objects.filter_active(phone=self.account)
        elif RegularUtils.email_check(self.account):
            email = self.account
            people_qs = People.objects.filter_active(email=self.account)
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_FOUND)
        if not people_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_FOUND)
        people_qs = people_qs.filter(active_code=self.active_code, active_code_valid=True)
        if not people_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACTIVE_CODE_INVALID)
        user_qs = None
        if phone:
            user_qs = AuthUser.objects.filter(is_active=True, phone=phone)
        elif email:
            user_qs = AuthUser.objects.filter(is_active=True, email=email)
        if user_qs.exists():
            # 存在关联的帐号， 不能设置密码生成帐号
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_EXISTS)
        # 创建帐号
        people = people_qs[0]
        user, code = UserAccountUtils.user_register(
            self.pwd, phone=phone, email=email, role_type=AuthUser.ROLE_NORMAL)
        user, err_code = UserAccountUtils.user_login_web(request, user, self.pwd)
        user_info = people_login(request, user, self.get_serializer_context())
        people.user_id = user.id
        people.active_code_valid = False
        people.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            'login': True, 'user_info': user_info, "login_account": self.account
        })


class PeopleLogoutView(WdCreateAPIView):
    u"""用户退出"""

    def post(self, request, *args, **kwargs):
        try:
            logout(request)
        except Exception, e:
            err_logger.error("web logout error, msg(%s)" % e)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class PeopleRegisterView(AuthenticationExceptView, WdCreateAPIView):
    u"""
    测验用户注册
    1. 开放测验地址手机/邮箱
    2. 组织码
    """

    def survey_register_360(self):
        pass

    def survey_register_normal(self, account, pwd, survey_id_base64, assess_id_base64):
        u"""通过链接注册进入"""
        phone = email = None
        survey_id = 0
        assess_id = base64.b64decode(assess_id_base64)
        try:
            project = AssessProject.objects.get(id=assess_id)
        except:
            err_logger.error("project not found: %s" % assess_id)
            return ErrorCode.INVALID_INPUT
        if project.distribute_type != AssessProject.DISTRIBUTE_OPEN:
            err_logger.error("project is not open: %s" % project.id)
            return ErrorCode.INVALID_INPUT
        if RegularUtils.phone_check(account):
            people_qs = People.objects.filter_active(phone=account)
            phone = account
        elif RegularUtils.email_check(account):
            people_qs = People.objects.filter_active(email=account)
            email = account
        else:
            return ErrorCode.INVALID_INPUT
        user, code = UserAccountUtils.user_register(
            pwd, phone=phone, email=email, role_type=AuthUser.ROLE_NORMAL)
        if code != ErrorCode.SUCCESS:
            return code
        if people_qs.exists():
            people_qs.update(user_id=user.id)
            people = people_qs[0]
        else:
            people = People.objects.create(user_id=user.id, username=account, phone=phone, email=email)
        try:
            send_one_user_survey(project.id, people.id)
        except Exception, e:
            err_logger.error("people survey relation error, msg: %s" %e)
        return ErrorCode.SUCCESS, user, project.enterprise_id

    def org_code_register(self, account, pwd, org_code):
        u"""这边假设所有的用户都是先后台导入，创建了People，后台自动发送组织码，其他渠道获取的组织码，
        因为没有People，会注册不成功"""
        # porgs_check_qs = Organization.objects.filter_active(identification_code=org_code)
        # if porgs_check_qs.count() == 0:
        #     return ErrorCode.PROJECT_ORG_CODE_EMPTY_ERROR, None  # 组织码不存在
        # if porgs_check_qs.count() == 1:
        #     project = AssessProject.objects.get(id=porgs_check_qs[0].assess_id)
        #     if project.distribute_type == AssessSurveyRelation.DISTRIBUTE_IMPORT:
        #         return ErrorCode.PROJECT_NOT_OPEN_ERROR, None   # 项目是非开放测评
        # if porgs_check_qs.count() > 1:
        #     return ErrorCode.PROJECT_ORG_CODE_DOUBLE_ERROR, None   # 组织码重复

        phone = email = None
        if RegularUtils.phone_check(account):
            people_qs = People.objects.filter_active(phone=account)
            phone = account
        elif RegularUtils.email_check(account):
            people_qs = People.objects.filter_active(email=account)
            email = account
        else:
            return ErrorCode.INVALID_INPUT
        user, code = UserAccountUtils.user_register(
            pwd, phone=phone, email=email, role_type=AuthUser.ROLE_NORMAL)
        if not people_qs.exists():
            people = People.objects.create(user_id=user.id, username=account, phone=phone, email=email)
            pids = [people.id]
        else:
            pids = list(people_qs.values_list("id", flat=True))
        # org code 之前导入的人员关系，判断是否存在关系 # remove
        porgs = PeopleOrganization.objects.filter_active(
            people_id__in=pids, org_code=org_code)
        if not porgs.exists():
            for pid in pids:
                PeopleOrganization.objects.create(
                    people_id=pid,
                    org_code=org_code
                )
                break
        people_qs = People.objects.filter_active(id__in=list(pids))
        people_qs.update(user_id=user.id)
        # 加入项目
        people_id = pids[0]
        assess_id = AssessOrganization.objects.filter_active(organization_code=org_code).values_list("assess_id", flat=True)[0]
        send_one_user_survey(assess_id, people_id)
        return ErrorCode.SUCCESS, user

    def post(self, request, *args, **kwargs):
        account = self.request.data.get("account", None)
        verify_code = self.request.data.get("verify_code", None)
        pwd = self.request.data.get("pwd", None)
        org_code = self.request.data.get("org_code", None)
        survey_id_base64 = self.request.data.get("bs", None)
        assess_id_base64 = self.request.data.get("ba", None)
        if not account or not verify_code or not pwd:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        rst = VerifyCodeExpireCache(account).check_verify_code(verify_code)
        # verify_code check
        # TODO: 开发环境 校验码校验暂时去掉
        if not rst and not settings.DEBUG:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_VERIFY_CODE_INVALID)
        #  account check
        user, err_code = UserAccountUtils.account_check(account)
        if user is not None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_EXISTS)

        rst_code = ErrorCode.SUCCESS
        enterprise = 0
        # SUCCESS不合法，递交的参数没有组织码和assess_id_base64 也success
        if org_code:
            # 组织码注册
            rst_code, user = self.org_code_register(account, pwd, org_code)
            if rst_code != ErrorCode.SUCCESS:
                user_info = None
                return general_json_response(status.HTTP_200_OK, rst_code,
                                             {"is_login": err_code, "user_info": user_info})
        elif assess_id_base64:
            # 问卷连接注册
            rst_code, user, enterprise = self.survey_register_normal(account, pwd, survey_id_base64, assess_id_base64)
        # 注册后返回用户信息以便直接跳转登陆
        try:
            # 理论成功创建用户应该都合法，err_code只是复用代码
            user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
            user_info = people_login(request, user, self.get_serializer_context())
            user_info['enterprise'] = enterprise
        # except:
        except Exception, e:
            err_logger.error("Register_FOR_Login error, msg is %s" % e)
            user_info = None
        return general_json_response(status.HTTP_200_OK, rst_code, {"is_login": err_code, "user_info": user_info})


class UserAccountInfoView(WdRetrieveUpdateAPIView):
    u"""用户帐号信息"""
    model = AuthUser
    serializer_class = UserBasicSerializer

    def get_id(self):
        return self.request.user.id

    def get_object(self):
        return self.request.user

    def post_check_parameter(self, kwargs):
        rst_code =super(UserAccountInfoView, self).post_check_parameter(kwargs)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        phone = self.request.data.get("phone", None)
        email = self.request.data.get("email", None)
        verify_code = self.request.data.get("verify_code", None)
        old_pwd = self.request.data.get("old_pwd", None)
        pwd = self.request.data.get("pwd", None)
        account = None
        if phone:
            account = phone
        elif email:
            account = email
        if account and not verify_code:
            return ErrorCode.INVALID_INPUT
        if account:
            check_rst = VerifyCodeExpireCache(account).check_verify_code(verify_code)
            if not check_rst:
                return ErrorCode.USER_VERIFY_CODE_INVALID
            is_exists = False
            if phone:
                is_exists = AuthUser.objects.filter(is_active=True, phone=phone).exclude(id=self.get_id()).exists()
            elif email:
                is_exists = AuthUser.objects.filter(is_active=True, email=email).exclude(id=self.get_id()).exists()
            if is_exists:
                return ErrorCode.USER_ACCOUNT_EXISTS
        if old_pwd and pwd:
            user = self.get_object()
            user = UserAccountUtils.user_auth_pwd(user, old_pwd)
            # old_pwd = make_password(old_pwd)
            if not user or not user.is_authenticated:
                return ErrorCode.USER_PWD_MODIFY_OLD_PWD_ERROR
        return ErrorCode.SUCCESS

    def perform_update(self, serializer):
        super(UserAccountInfoView, self).perform_update(serializer)
        src_pwd = self.request.data.get("pwd", None)
        if src_pwd is not None:
            user = self.get_object()
            pwd = make_password(src_pwd)
            user.password = pwd
            user.save()
            UserAccountUtils.user_login_web(self.request, user, src_pwd)


class OrgInfoView(AuthenticationExceptView, WdListAPIView):
    u"""通过组织码获取组织"""

    model = Organization
    serializer_class = OrganizationBasicSerializer
    GET_CHECK_REQUEST_PARAMETER = ("org_code", )

    def get(self, request, *args, **kwargs):
        org_qs = Organization.objects.filter_active(identification_code=self.org_code)
        if not org_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"org_name": None})
        org = org_qs[0]
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"org_name": org.name})


class UserOrgInfoView(WdListAPIView):
    u"""用户组织信息"""

    def get(self, request, *args, **kwargs):
        user_id = self.request.user.id
        people_ids = People.objects.filter_active(user_id=user_id).values_list("id", flat=True)
        org_codes = PeopleOrganization.objects.filter_active(
            people_id__in=list(people_ids)).values_list("org_code", flat=True)
        org_info = {"org_name": None, "company_name": None}
        if not org_codes.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, org_info)
        orgs = Organization.objects.filter_active(identification_code__in=org_codes)
        if not orgs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, org_info)
        org = orgs[0]
        try:
            assess_obj = AssessProject.objects.get(id=org.assess_id)
            enterprise = EnterpriseInfo.objects.get(id=assess_obj.enterprise_id)
        except:
            try:
                enterprise = EnterpriseInfo.objects.get(id=org.enterprise_id)
            except:
                # 理论上有组织则必定可以搜到对应的公司和项目
                org_info['org_name'] = u'组织异常'
                org_info["company_name"] = u'公司异常'
                return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, org_info)
        org_info["org_name"] = org.name
        try:
            if orgs.count() > 1:
                names = list(orgs.values_list("name", flat=True))
                names_st = ','.join(names)
                org_info["org_name"] = names_st
        except:
            org_info["org_name"] = org.name
        org_info["company_name"] = enterprise.cn_name
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, org_info)


class SurveyJoinView(WdCreateAPIView):
    u"""加入开放测验
    0，点击链接，请求加入该问卷
    返回：
    1. 未登录，跳转登录/注册，注册带着该问卷信息
    2. 已经登录，加入入该测评，跳转个人测评页面
    """


class PeopleSurveyListView(WdListAPIView):
    u"""测验用户的测评列表"""

    model = PeopleSurveyRelation
    serializer_class = PeopleSurveySerializer
    FILTER_FIELDS = ('status', )

    # get查询
    def qs_filter(self, qs):
        user_id = self.request.user.id
        people_ids = People.objects.filter_active(user_id=user_id).values_list("id", flat=True)
        qs = qs.filter(people_id__in=list(people_ids))
        # TODO: 数据修正
        # qs.update(survey_id__in=SurveyInfo.objects.filter_active())
        #
        status = self.request.GET.get("status", None)
        if not status:
            return qs
        status = int(status)
        if status == PeopleSurveyRelation.STATUS_NOT_BEGIN:
            # 问卷未开始
            qs = qs.filter(status=PeopleSurveyRelation.STATUS_NOT_BEGIN)
        elif status == PeopleSurveyRelation.STATUS_DOING:
            # 已开放
            qs = qs.filter(status=PeopleSurveyRelation.STATUS_DOING)
        elif status == PeopleSurveyRelation.STATUS_DOING_PART:
            # 答卷中
            qs = qs.filter(status=PeopleSurveyRelation.STATUS_DOING_PART)
        elif status == PeopleSurveyRelation.STATUS_FINISH:
            # 已经完成
            qs = qs.filter(status=PeopleSurveyRelation.STATUS_FINISH)
        elif status == PeopleSurveyRelation.STATUS_EXPIRED:
            # 已经过期
            qs = qs.filter(status=PeopleSurveyRelation.STATUS_EXPIRED)
        return qs


class PeopleSurveyDetailView(WdListAPIView):
    u"""测验用户的测评详情"""

    model = PeopleSurveyRelation
    serializer_class = PeopleSurveySerializer
    GET_CHECK_REQUEST_PARAMETER = ("survey_id", "project_id")

    def get(self, request, *args, **kwargs):
        user_id = self.request.user.id
        people_ids = People.objects.filter_active(user_id=user_id).values_list("id", flat=True)
        survey_qs = PeopleSurveyRelation.objects.filter_active(
            people_id__in=list(people_ids),
            survey_id=self.survey_id,
            project_id=self.project_id,
            role_type=self.request.GET.get("role_type", PeopleSurveyRelation.ROLE_TYPE_NORMAL),
            evaluated_people_id=self.request.GET.get("evaluated_people_id", 0)
        )
        relation_obj = survey_qs[0]
        survey_data = PeopleSurveySerializer(instance=relation_obj).data
        survey_info_qs = SurveyInfo.objects.filter_active(survey_id=self.survey_id, project_id=self.project_id)
        if survey_info_qs.exists():
            survey_info = survey_info_qs[0]
            if survey_info.test_type == SurveyInfo.TEST_TYPE_BY_PART:
                user_get_survey_ops(
                    relation_obj.people_id,
                    relation_obj.survey_id,
                    relation_obj.project_id,
                    UserSurveyBlockStatus.BLOCK_PART_ALL,
                    relation_obj.role_type,
                    relation_obj.evaluated_people_id
                )
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, survey_data)


class PeopleSurveyOpenCheckView(WdListAPIView):
    u"""测验用户的测评详情"""

    model = PeopleSurveyRelation
    serializer_class = PeopleSurveySerializer
    GET_CHECK_REQUEST_PARAMETER = ("survey_id", "project_id")

    def get(self, request, *args, **kwargs):
        user_id = self.request.user.id
        people_ids = People.objects.filter_active(user_id=user_id).values_list("id", flat=True)
        err_code, info = check_survey_open(
            people_id=people_ids[0],
            project_id=self.project_id,
            surveyid=self.survey_id,
            role_type=self.request.GET.get("role_type", PeopleSurveyRelation.ROLE_TYPE_NORMAL),
            evaluated_people_id=self.request.GET.get("evaluated_people_id", 0),
            check_page=self.request.GET.get("check_page", None),
        )
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            "check_code": err_code,
            "check_info": info,

        })


class PeopleInfoGatherView(WdListCreateAPIView):
    u"""用户信息收集展示接口"""
    model = UserProjectSurveyGatherInfo
    GET_CHECK_REQUEST_PARAMETER = ("project_id", )
    POST_CHECK_REQUEST_PARAMETER = ("project_id", "infos")

    def post(self, request, *args, **kwargs):
        user_id = self.request.user.id
        peoples = People.objects.filter_active(
            user_id=user_id).order_by("-id")
        people = peoples[0]
        people_id = people.id
        if people.more_info:
            people_more_info = json.loads(people.more_info)
        else:
            people_more_info = []
        people_more_info_map = {}
        for p_info in people_more_info:
            people_more_info_map[p_info["key_name"]] = p_info
        is_modify = False
        for info in self.infos:
            project_id = self.project_id
            if info.get("assess_id", None) is not None:
                project_id = info.get("assess_id")
            qs = UserProjectSurveyGatherInfo.objects.filter_active(
                people_id=people_id,
                info_id=info["id"]
            )
            if qs.exists():
                qs.update(info_value=info["info_value"], option_id=info.get("option_id", 0))
            else:
                UserProjectSurveyGatherInfo.objects.create(
                    people_id=people_id, # project_id=project_id,
                    info_id=info["id"], info_value=info["info_value"],
                    option_id=info.get("option_id", 0)
                )
            if info["info_value"]:
                is_modify = True
                gather_obj = AssessGatherInfo.objects.get(id=info["id"])
                if gather_obj.info_name == u"姓名":
                    people.username = info["info_value"]
                else:
                    people_more_info_map[gather_obj.info_name] = {
                        'key_name': gather_obj.info_name,
                        'key_value': info["info_value"],
                        'key_id': info["id"]
                    }
        if is_modify:
            people_more_info = [people_more_info_map[k] for k in people_more_info_map]
            people.more_info = json.dumps(people_more_info)
            people.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def get(self, request, *args, **kwargs):
        user_id = self.request.user.id
        peoples = People.objects.filter_active(
            user_id=user_id).order_by("-id")
        people = peoples[0]
        people_id = people.id
        self.project_id = int(self.project_id)
        if self.project_id:
            gather_info = AssessGatherInfo.objects.filter_active(
                Q(assess_id=0) | Q(assess_id=self.project_id)).values("id", "info_name", "info_type", "config_info",
                    "assess_id", "is_required", "is_modified").distinct()
        else:
            project_ids = AssessUser.objects.filter_active(people_id=people_id).values_list("assess_id", flat=True)
            gather_info = AssessGatherInfo.objects.filter_active(
                Q(assess_id=0) | Q(assess_id__in=project_ids)).values("id", "info_name", "info_type", "config_info",
                    "assess_id", "is_required", "is_modified").distinct()

        data = []
        is_finish = True
        info_name_list = []
        for info in gather_info:
            #     这里可能会有2个项目下的信息有重复的
            if info["info_name"] and (info["info_name"] in info_name_list):
                continue
            else:
                info_name_list.append(info["info_name"])
            if info["config_info"]:
                info["config_info"] = json.loads(info["config_info"])
            qs = UserProjectSurveyGatherInfo.objects.filter_active(
                people_id=people_id,
                info_id=info["id"]
            ).order_by("-id")
            if not qs.exists():
                import_info = people.get_info_value(info["info_name"])
                if not import_info:
                    is_finish = False
                    info["info_value"] = None
                else:
                    info["info_value"] = import_info
            else:
                info["info_value"] = qs[0].info_value
            data.append(info)
        if is_finish and self.project_id:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"is_finish": is_finish})
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
                "is_finish": is_finish,
                "info_data": data
            })


class ProjectAdvertList(WdListAPIView):
    u"""轮播广告地址"""

    def get(self, request, *args, **kwargs):
        user_id = self.request.user.id
        people_ids = People.objects.filter_active(user_id=user_id).values_list("id", flat=True)
        project_ids = PeopleSurveyRelation.objects.filter_active(
            people_id__in=list(people_ids)).values_list("project_id", flat=True).distinct().order_by("-id")
        advert_urls = AssessProject.objects.filter_active(
            id__in=list(project_ids)).order_by("-id").values_list("advert_url", flat=True)[:5]
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            "urls": advert_urls
        })


class PeopleSurveyReportListView(WdListAPIView):
    u"""测验用户的测评报告列表"""

    model = PeopleSurveyRelation
    serializer_class = PeopleSurveySerializer
    CUSTOM_RESPONSE = True
    FILTER_FIELDS = ("report_status", )

    def qs_filter(self, qs):
        user_id = self.request.user.id
        people_ids = People.objects.filter_active(user_id=user_id).values_list("id", flat=True)
        qs = qs.filter(people_id__in=list(people_ids), status__gt=PeopleSurveyRelation.STATUS_DOING)
        qs = qs.filter(report_status__gt=PeopleSurveyRelation.REPORT_INIT)
        return super(PeopleSurveyReportListView, self).qs_filter(qs)

    def custom_data_results(self, detail):
        language = self.request.GET.get("language", SurveyAlgorithm.LANGUAGE_ZH)
        get_report.delay(detail, self.request.user.id, language=language)
        for result in detail["results"]:
            survey_info = result["survey_info"]
            project_id = survey_info["project_id"]
            survey_id = survey_info["survey_id"]
            rel_qs = AssessSurveyRelation.objects.filter_active(assess_id=project_id, survey_id=survey_id)
            if rel_qs.exists():
                result["people_view_report"] = rel_qs[0].people_view_report
            else:
                result["people_view_report"] = AssessSurveyRelation.CAN_NOT_VIEW_REPORT
            if int(result["report_status"]) == PeopleSurveyRelation.REPORT_FAILED:
                result["report_status"] = PeopleSurveyRelation.REPORT_GENERATING
        return detail


class ProjectSurveyGatherInfo(WdListCreateAPIView):
    u"""用户信息采集"""

    model = AssessGatherInfo
    serializer_class = None
    GET_CHECK_REQUEST_PARAMETER = ('project_id', 'survey_id')

    def get(self, request, *args, **kwargs):
        # todo: 设定问卷已读状态

        # 系统收集信息
        qs = AssessGatherInfo.objects.filter_active(assess_id=0)
        system_data = AssessGatherInfoSerializer(instance=qs, many=True).data
        # 项目收集信息
        qs = AssessGatherInfo.objects.filter_active(assess_id=self.project_id)
        project_data = AssessGatherInfoSerializer(instance=qs, many=True).data
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            'system_data': system_data, 'project_data': project_data
        })


class PeopleQuestionListView(WdListAPIView):
    u"""获取题目列表"""

    GET_CHECK_REQUEST_PARAMETER = ("survey_id", "project_id", "block_id")
    model = SurveyQuestionInfo
    serializer_class = SurveyQuestionInfoSerializer

    def get_answer(self, data, people, init=False):
        if init or data is None:
            if data is None:
                data = []
            for question_info in data:
                question_info["answer"] = []
            return data

        for question_info in data:
            answer = UserQuestionAnswerInfo.objects.filter_active(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                question_id=question_info["id"],
                block_id=self.block_id,
                role_type=self.role_type,
                evaluated_people_id=self.evaluated_people_id
            ).values("answer_id", "answer_score", "answer_time", "answer_content", "answer_index").order_by("id")
            question_info["answer"] = answer
        return data

    def get_normal_question(self, people):
        qs = SurveyQuestionInfo.objects.filter_active(
            survey_id=self.survey_id, project_id=self.project_id, block_id=self.block_id)
        if not qs.exists():
            survey_question_info = survey_question_sync(self.survey_id, self.project_id, self.block_id)
            data = json.loads(survey_question_info.question_info)
        else:
            data = json.loads(qs[0].question_info)
        data = self.get_answer(data, people)
        return data

    def get_random_question(self, people):
        user_question_qs = UserQuestionInfo.objects.filter_active(
            people_id=people.id,
            survey_id=self.survey_id,
            project_id=self.project_id,
            block_id=self.block_id
        )
        if user_question_qs.exists():
            data = json.loads(user_question_qs[0].question_info)
            data = self.get_answer(data, people)
        else:
            qs = SurveyQuestionInfo.objects.filter_active(
                survey_id=self.survey_id, project_id=self.project_id, block_id=self.block_id
            )
            if not qs.exists():
                survey_question_info = survey_question_sync(self.survey_id, self.project_id, self.block_id)
                src_question_info = json.loads(survey_question_info.question_info)
            else:
                src_question_info = json.loads(qs[0].question_info)
            passage_question_info = {}
            random_question_info = []
            for question_info in src_question_info:
                if question_info.get("question_passage_id", 0):
                    if question_info["question_passage_id"] not in passage_question_info:
                        passage_question_info[question_info["question_passage_id"]] = [question_info]
                    else:
                        passage_question_info[question_info["question_passage_id"]].append(question_info)
                else:
                    random_question_info.append(question_info)

            if self.survey_info.random_question:
                src_question_info = random_question_info
                random.shuffle(src_question_info)
                passage_count = len(passage_question_info)
                if passage_count > 0:
                    random_passage_ids = passage_question_info.keys()
                    random.shuffle(random_passage_ids)
                    new_src_question_info = []
                    left_question = src_question_info
                    for passage_id in random_passage_ids:
                        if left_question:
                            random_passage_index = random.randint(0, len(left_question)-1)
                        else:
                            random_passage_index = 0
                        new_src_question_info += left_question[:random_passage_index]
                        left_question = left_question[random_passage_index:]
                        new_src_question_info += passage_question_info[passage_id]
                    new_src_question_info += left_question
                    src_question_info = new_src_question_info
            if self.survey_info.random_options == SurveyInfo.RANDOM_OPTION_RANDOM:
                question_list = []
                for question in src_question_info:
                    question_category = question.get("question_category", None)
                    if question_category != Question.CATEGORY_PRESSURE:  # 非压力题随机
                        question_type = question.get("question_type", None)
                        if question_type in [Question.QUESTION_TYPE_SINGLE, Question.QUESTION_TYPE_MULTI]:
                            # 单选 多选
                            random.shuffle(question["options"]["option_data"])
                        elif question_type == Question.QUESTION_TYPE_MUTEXT:
                            # 互斥
                            random.shuffle(question["options"]["options"])
                        # elif question_type == Question.QUESTION_TYPE_SLIDE:
                        elif question_type in [Question.QUESTION_TYPE_SLIDE, Question.QUESTION_TYPE_NINE_SLIDE]:
                            # 滑块题， 增加九点题
                            if random.randint(0, 1):
                                max_value = question["options"]["max_value"]
                                min_value = question["options"]["min_value"]
                                max_desc = question["options"]["max_desc"]
                                min_desc = question["options"]["min_desc"]
                                question["options"]["max_value"] = min_value
                                question["options"]["min_value"] = max_value
                                question["options"]["max_desc"] = min_desc
                                question["options"]["min_desc"] = max_desc
                        elif question_type is None:
                            # 迫选组卷，没有question type
                            random.shuffle(question["options"])
                    question_list.append(question)
                src_question_info = question_list
            elif self.survey_info.random_options == SurveyInfo.RANDOM_OPTION_ORDER_RANDOM:
                question_list = []
                for question in src_question_info:
                    question_category = question.get("question_category", None)
                    if question_category != Question.CATEGORY_PRESSURE:  # 非压力题随机
                        question_type = question.get("question_type", None)
                        if question_type in [Question.QUESTION_TYPE_SINGLE, Question.QUESTION_TYPE_MULTI]:
                            # 单选 多选
                            if random.randint(0, 1):
                                new_data = list(reversed(question["options"]["option_data"])) #random.shuffle(question["options"]["option_data"])
                                question["options"]["option_data"] = new_data
                        elif question_type == Question.QUESTION_TYPE_MUTEXT:
                            # 互斥
                            if random.randint(0, 1):
                                new_data = list(reversed(question["options"]["options"]))
                                question["options"]["options"] = new_data
                        # elif question_type == Question.QUESTION_TYPE_SLIDE:
                        elif question_type in [Question.QUESTION_TYPE_SLIDE, Question.QUESTION_TYPE_NINE_SLIDE]:
                            # 滑块题, 九点题
                            if random.randint(0, 1):
                                max_value = question["options"]["max_value"]
                                min_value = question["options"]["min_value"]
                                max_desc = question["options"]["max_desc"]
                                min_desc = question["options"]["min_desc"]
                                question["options"]["max_value"] = min_value
                                question["options"]["min_value"] = max_value
                                question["options"]["max_desc"] = min_desc
                                question["options"]["min_desc"] = max_desc
                        elif question_type is None:
                            # 迫选组卷，没有question
                            if random.randint(0, 1):
                                new_data = list(reversed(question["options"]))
                                question["options"] = new_data
                    question_list.append(question)
                src_question_info = question_list
            UserQuestionInfo.objects.create(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                block_id=self.block_id,
                question_info=json.dumps(src_question_info)
            )
            data = self.get_answer(src_question_info, people)
        return data

    def check_save_survey_block(self, people):
        # TODO: 异步，性能优化
        user_get_survey_ops(people.id, self.survey_id, self.project_id, self.block_id,
                            self.role_type,
                            self.evaluated_people_id)
        # user_survey_qs = UserSurveyBlockStatus.objects.filter_active(
        #     people_id=people.id,
        #     survey_id=self.survey_id,
        #     project_id=self.project_id,
        #     block_id=self.block_id,
        # )
        # if user_survey_qs.exists():
        #     user_survey = user_survey_qs[0]
        #     if user_survey.status != UserSurveyBlockStatus.STATUS_READ:
        #         user_survey.status = UserSurveyBlockStatus.STATUS_READ
        #         user_survey.save()
        # else:
        #     UserSurveyBlockStatus.objects.create(
        #         people_id=people.id,
        #         survey_id=self.survey_id,
        #         project_id=self.project_id,
        #         block_id=self.block_id,
        #         status=UserSurveyBlockStatus.STATUS_READ
        #     )
        #     PeopleSurveyRelation.objects.filter_active(
        #         people_id=people.id,
        #         survey_id=self.survey_id,
        #         project_id=self.project_id,
        #     )

    def check_project(self, people):
        return check_survey_open(people.id, self.project_id, self.survey_id, self.role_type, self.evaluated_people_id)[0]

    def get(self, request, *args, **kwargs):
        survey_infos = SurveyInfo.objects.filter_active(survey_id=self.survey_id, project_id=self.project_id).order_by("-id")
        if not survey_infos.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"questions": []})
        survey_info = survey_infos[0]
        self.survey_info = survey_info
        self.role_type = self.request.GET.get("role_type", PeopleSurveyRelation.ROLE_TYPE_NORMAL)
        self.evaluated_people_id = self.request.GET.get("evaluated_people_id", 0)
        people_qs = People.objects.filter_active(user_id=self.request.user.id)
        if not people_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.PERMISSION_FAIL)
        people = people_qs[0]
        rst_code = self.check_project(people)
        if rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        # if (not survey_info.random_question and not survey_info.random_options):
        #     data = self.get_normal_question(people)
        # else:
        #     data = self.get_random_question(people)
        # 检查是不是按照维度顺序答题
        # 获得所有的块信息
        debug_logger.debug("survey_info.test_type is %s" % survey_info.test_type)
        if survey_info.test_type != SurveyInfo.TEST_TYPE_BY_QUESTION:
            block_info = json.loads(survey_info.block_info)
            if block_info:
                # 如果有块信息
                # info_logger.info("all_%s" % block_info)
                this_block = {}
                for block in block_info:
                    # info_logger.info("%s_%s" % (str_check(self.block_id), str_check(block.get("id", 0))))
                    if str(self.block_id) == str(block.get("id", 0)):
                        this_block = block
                        break
                # 判断当前块是不是顺序答题
                debug_logger.debug("this_block.order_number is %s" % this_block.get("order_number", 0))
                if this_block.get("order_number", 0):
                    # info_logger.info("t_%s" % this_block)
                    for block_i in block_info:
                        # 比这小的块有没有答
                        if this_block.get("order_number", 0) > block_i.get("order_number", 0):
                            def check_survey_block_finish(block_id, survey_id, project_id, people_id):
                                usbs_qs = UserSurveyBlockStatus.objects.filter(
                                    block_id=block_id, survey_id=survey_id, project_id=project_id, people_id=people_id)
                                if not usbs_qs.exists():
                                    return ErrorCode.FAILURE
                                if usbs_qs.exists():
                                    if usbs_qs[0].is_finish:
                                        return ErrorCode.SUCCESS
                                return ErrorCode.FAILURE
                            debug_logger.debug("block_id, survey_id, project_id, people_id is %s, %s, %s, %s" %(
                                block_i.get("id"), self.survey_id, self.project_id, people.id))
                            if check_survey_block_finish(block_i.get("id"), self.survey_id, self.project_id, people.id) != ErrorCode.SUCCESS:
                                # 提示， 请按照设定的维度顺序依次答题  报错码暂时待修改
                                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ANSWER_SURVEY_ORDER_ERROR)

        if survey_info.random_question or survey_info.random_options:
            data = self.get_random_question(people)
        else:
            data = self.get_normal_question(people)
        self.check_save_survey_block(people)
        #
        try:
            new_time_limit = None
            relation_qs = PeopleSurveyRelation.objects.filter_active(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                role_type=self.role_type,
                evaluated_people_id=self.evaluated_people_id
            )
            if relation_qs.exists():
                relation_obj = relation_qs[0]
                if self.survey_info.time_limit:
                    pass
        except:
            pass
        #
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"questions": data})


# 弃用
class PeopleBlockQuestionListView(WdListAPIView):
    u"""获取块题目列表"""

    GET_CHECK_REQUEST_PARAMETER = ("survey_id", "project_id", "block_id")
    model = SurveyQuestionInfo
    serializer_class = SurveyQuestionInfoSerializer

    def get_normal_question(self):
        qs = SurveyQuestionInfo.objects.filter_active(
            survey_id=self.survey_id, project_id=self.project_id, block_id=self.block_id)
        if not qs.exists():
            data = []
        else:
            data = json.loads(qs[0].question_info)
        return data

    def get_random_question(self):
        user_question_qs = UserQuestionInfo.objects.filter_active(
            people_id=self.request.user.id,
            survey_id=self.survey_id,
            project_id=self.project_id,
            block_id=self.block_id
        )
        if user_question_qs.exists():
            data = json.loads(user_question_qs[0].question_info)
        else:
            qs = SurveyQuestionInfo.objects.filter_active(
                survey_id=self.survey_id, project_id=self.project_id, block_id=self.block_id)
            if not qs.exists():
                data = []
            else:
                src_question_info = json.loads(qs[0].question_info)
                data = random.shuffle(src_question_info)
                UserQuestionInfo.objects.create(
                    people_id=self.request.user.id,
                    survey_id=self.survey_id,
                    project_id=self.project_id,
                    block_id=self.block_id,
                    question_info=json.dumps(data)
                )
        return data

    def get(self, request, *args, **kwargs):
        survey_info = SurveyInfo.objects.get(id=self.survey_id)
        if not survey_info.random_question and not survey_info.random_options:
            data = self.get_normal_question()
        else:
            data = self.get_random_question()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"questions": data})


class UserAnswerQuestionView(WdCreateAPIView):
    u"""用户回答"""

    model = UserQuestionAnswerInfo
    #serializer_class = None
    serializer_class = UserQuestionInfoSerializer

    POST_CHECK_REQUEST_PARAMETER = ('questions', 'survey_id', 'project_id', 'answer_count_time', 'block_id')

    def save_single(self, people, question_id, order_num, answer_time, user_question_answer_list, **kwargs):
        answer_id = kwargs.get("answer_id", 0)
        answer_content = kwargs.get("answer_content", None)
        score = kwargs.get("answer_score", 0)
        qs = UserQuestionAnswerInfo.objects.filter_active(
            survey_id=self.survey_id, project_id=self.project_id,
            people_id=people.id, question_id=question_id,
            block_id=self.block_id, role_type=self.role_type,
            evaluated_people_id=self.evaluated_people_id
        )
        if qs.exists():
            qs.update(
                answer_id=answer_id, answer_score=score,
                answer_content=answer_content, answer_time=answer_time
            )
        else:
            user_question_answer_list.append(
                UserQuestionAnswerInfo(
                    survey_id=self.survey_id, project_id=self.project_id,
                    people_id=people.id, question_id=question_id,
                    order_num=order_num, answer_id=answer_id, answer_score=score,
                    answer_content=answer_content, answer_time=answer_time,
                    block_id=self.block_id, role_type=self.role_type,
                    evaluated_people_id=self.evaluated_people_id
                )
            )

    def save_multi(self, people, question_id, order_num, answer_time, user_question_answer_list, **kwargs):
        answer_ids = kwargs.get("answer_ids", [])
        scores = kwargs.get("answer_scores", [])
        answer_content = kwargs.get("answer_content", None)
        UserQuestionAnswerInfo.objects.filter_active(
            survey_id=self.survey_id, project_id=self.project_id,
            people_id=people.id, question_id=question_id,
            block_id=self.block_id, role_type=self.role_type,
            evaluated_people_id=self.evaluated_people_id
        ).update(is_active=False)
        for answer_index, answer_id in enumerate(answer_ids):
            user_question_answer_list.append(
                UserQuestionAnswerInfo(
                    survey_id=self.survey_id, project_id=self.project_id,
                    people_id=people.id, question_id=question_id,
                    order_num=order_num, answer_id=answer_id, answer_score=scores[answer_index],
                    answer_content=answer_content, answer_time=answer_time,
                    block_id=self.block_id, role_type=self.role_type,
                    evaluated_people_id=self.evaluated_people_id
                )
            )

    def save_slide(self, people, question_id, order_num, answer_time, user_question_answer_list, **kwargs):
        score = kwargs.get("answer_score", 0)
        qs = UserQuestionAnswerInfo.objects.filter_active(
            survey_id=self.survey_id, project_id=self.project_id,
            people_id=people.id, question_id=question_id,
            block_id=self.block_id, role_type=self.role_type,
            evaluated_people_id=self.evaluated_people_id
        )
        if qs.exists():
            qs.update(
                answer_score=score,
                answer_time=answer_time
            )
        else:
            user_question_answer_list.append(
                UserQuestionAnswerInfo(
                    survey_id=self.survey_id, project_id=self.project_id,
                    people_id=people.id, question_id=question_id,
                    order_num=order_num, answer_score=score, answer_time=answer_time,
                    block_id=self.block_id, role_type=self.role_type,
                    evaluated_people_id=self.evaluated_people_id
                )
            )

    def save_mutext(self, people, question_id, order_num, answer_time, user_question_answer_list, **kwargs):
        answer_ids = kwargs.get("answer_ids", [])
        scores = kwargs.get("answer_scores", [])
        answer_indexs = kwargs.get("answer_indexs", [])
        UserQuestionAnswerInfo.objects.filter_active(
            survey_id=self.survey_id,
            project_id=self.project_id,
            people_id=people.id,
            question_id=question_id,
            block_id=self.block_id,
            role_type=self.role_type,
            evaluated_people_id=self.evaluated_people_id
        ).update(is_active=False)
        for answer_index, answer_id in enumerate(answer_ids):
            if answer_indexs:  # 向前兼容
                aindex = answer_indexs[answer_index]
            else:
                aindex = 0
            user_question_answer_list.append(
                UserQuestionAnswerInfo(
                    survey_id=self.survey_id,
                    project_id=self.project_id,
                    people_id=people.id,
                    question_id=question_id,
                    order_num=order_num,
                    answer_id=answer_id,
                    answer_score=scores[answer_index],
                    answer_time=answer_time,
                    answer_index=aindex,
                    block_id=self.block_id,
                    role_type=self.role_type,
                    evaluated_people_id=self.evaluated_people_id
                )
            )

    def save_survey_block(self, people, finish_submit=None):
        user_survey_qs = UserSurveyBlockStatus.objects.filter_active(
            people_id=people.id,
            survey_id=self.survey_id,
            project_id=self.project_id,
            block_id=self.block_id,
            role_type=self.role_type,
            evaluated_people_id=self.evaluated_people_id
        )
        is_finish = False
        if finish_submit:
            is_finish = True
        if user_survey_qs.exists():
            user_survey = user_survey_qs[0]
            user_survey.answer_count_time += self.answer_count_time
            user_survey.status = UserSurveyBlockStatus.STATUS_READ
            user_survey.is_finish = is_finish
            user_survey.save()
        else:
            UserSurveyBlockStatus.objects.create(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                block_id=self.block_id,
                status=UserSurveyBlockStatus.STATUS_READ,
                is_finish=is_finish,
                answer_count_time=self.answer_count_time,
                role_type=self.role_type,
                evaluated_people_id=self.evaluated_people_id
            )

    def finish_survey(self, people):
        if self.block_id == 0:
            qs = PeopleSurveyRelation.objects.filter_active(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                role_type=self.role_type,
                evaluated_people_id=self.evaluated_people_id
            )
            qs.update(
                status=PeopleSurveyRelation.STATUS_FINISH,
                report_status=PeopleSurveyRelation.REPORT_GENERATING,
                finish_time=datetime.datetime.now()
            )
            if self.survey_id!=164:                
                for o in qs:
                    algorithm_task.delay(o.id)
        else:
            survey_info_qs = SurveyInfo.objects.filter_active(survey_id=self.survey_id, project_id=self.project_id)
            if survey_info_qs.exists():
                block_info = json.loads(survey_info_qs[0].block_info)
                block_ids = []
                for block in block_info:
                    block_ids.append(int(block["id"]))
                survey_finish = True
                for block_id in block_ids:
                    block_info = UserSurveyBlockStatus.objects.filter_active(
                        people_id=people.id,
                        survey_id=self.survey_id,
                        project_id=self.project_id,
                        block_id=block_id,
                        role_type=self.role_type,
                        evaluated_people_id=self.evaluated_people_id
                    )
                    if not block_info.exists():
                        survey_finish = False
                        break
                    if not block_info[0].is_finish:
                        survey_finish = False
                        break
                if survey_finish:
                    qs = PeopleSurveyRelation.objects.filter_active(
                        people_id=people.id,
                        survey_id=self.survey_id,
                        project_id=self.project_id,
                        role_type=self.role_type,
                        evaluated_people_id=self.evaluated_people_id
                    )
                    qs.update(
                        status=PeopleSurveyRelation.STATUS_FINISH,
                        report_status=PeopleSurveyRelation.REPORT_GENERATING,
                        finish_time=datetime.datetime.now()
                    )
                    if self.survey_id!=164:
                        for o in qs:
                            algorithm_task.delay(o.id)
        # 判断该用户的该项目中的问卷是不是已经全部做完，返回项目跳转链接
        people_survey_list = PeopleSurveyRelation.objects.filter_active(project_id=self.project_id, people_id=people.id)
        for people_survey in people_survey_list:
            if PeopleSurveyRelation.STATUS_FINISH > people_survey.status:
                return None
        return AssessProject.objects.get(id=self.project_id).finish_url

    def post(self, request, *args, **kwargs):
        user_question_answer_list = []
        people_qs = People.objects.filter_active(user_id=self.request.user.id)
        self.role_type = self.request.data.get("role_type", PeopleSurveyRelation.ROLE_TYPE_NORMAL)
        self.evaluated_people_id = self.request.data.get("evaluated_people_id", 0)
        if not people_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.PERMISSION_FAIL)
        people = people_qs[0]
        if PeopleSurveyRelation.objects.filter_active(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                role_type=self.role_type,
                evaluated_people_id=self.evaluated_people_id,
                status=PeopleSurveyRelation.STATUS_FINISH
        ).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.PERMISSION_FAIL)
        question_map = {}
        for question in self.questions:
            question_id = question.get("question_id", None)
            question_map[question_id] = question
        new_questions = question_map.values()
        for question in new_questions:
            order_num = question.pop("order_num", None)
            question_id = question.pop("question_id", None)
            question_type = int(question.pop("question_type", None))
            answer_time = question.pop("answer_time", None)
            if question_type in [Question.QUESTION_TYPE_SINGLE, Question.QUESTION_TYPE_SINGLE_FILLIN]:
                # 单选题， 单选填空题
                self.save_single(people, question_id, order_num, answer_time, user_question_answer_list, **question)
            elif question_type in [Question.QUESTION_TYPE_MULTI_FILLIN, Question.QUESTION_TYPE_MULTI]:
                # 多选题， 多选填空题
                self.save_multi(people, question_id, order_num, answer_time, user_question_answer_list, **question)
            elif question_type in [Question.QUESTION_TYPE_SLIDE, Question.QUESTION_TYPE_NINE_SLIDE]:
                # 滑块题 , 九点量表题
                self.save_slide(people, question_id, order_num, answer_time, user_question_answer_list, **question)
            elif question_type == Question.QUESTION_TYPE_MUTEXT or question_type == Question.QUESTION_TYPE_FORCE_QUESTION \
                    or question_type == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
                # 互斥题 / 迫选组卷 /
                # 迫选排序题提交可以用这个
                self.save_mutext(people, question_id, order_num, answer_time, user_question_answer_list, **question)
        UserQuestionAnswerInfo.objects.bulk_create(user_question_answer_list)
        finish_submit = self.request.data.get("finish_submit", None)
        self.save_survey_block(people, finish_submit)
        # hot fix 限时问卷开始答题时间后移
        try:
            obj_people_surveys = PeopleSurveyRelation.objects.filter_active(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                role_type=self.role_type,
                evaluated_people_id=self.evaluated_people_id
            )
            for obj_people_survey in obj_people_surveys:
                if not obj_people_survey.begin_answer_time:
                    obj_people_survey.begin_answer_time = datetime.datetime.now()
                    obj_people_survey.save()
        except:
            pass
        if finish_submit:
            finish_url = self.finish_survey(people)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"finish_url": finish_url})
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"finish_url": None})


class ReportDataView(AuthenticationExceptView, WdCreateAPIView):
    u"""报告数据"""
    REPORT_MAP = {
        # 心理健康
        "EmployeeMentalHealth": 'self.get_mental_health_value',
        # 心理健康英文
        "EmployeeMentalHealth_EN": 'self.get_mental_health_value_en',
        # 工作价值观
        "WorkValueQuestionnaire": 'self.get_work_value',
        # 职业个性
        "DISC": 'self.get_professional_value',
        "DISC_NEW": 'self.get_professional_value_new',
        # 心理资本
        "PsychologicalCapital": 'self.get_psychological_capital_value',
        # 幸福能力
        'HAMeasurePersonal': 'self.get_ha_measure_value',
        # 幸福能力英文
        'HAMeasurePersonal_EN': 'self.get_ha_measure_value_en',
        # 幸福需求
        'HappinessNeeds': 'self.get_happiness_needs',
        # 能力测评
        "CapacityEvaluation": 'self.get_capacity_evaluation_value',
        "C1": 'self.get_c1_value',
        "C2": 'self.get_c2_value',
        # 员工自我提升
        'YGZWTS': 'self.get_ygzwts_value',
        # 行为风格
        "BehavioralStyle": 'self.get_xwfg_value',
        # 职业定向
        "ZYDX": 'self.get_zydx_value',
        # Personal EOI
        "PEOI": "self.get_peoi_value",
        # 行为风格修改
        "NewBehavioralStyle": "self.get_xxwfg_value",
        # maanshan能力测评
        "PECMAANSHAN": 'self.get_pec_maanshan',
        # 职业定向(new)
        "CO2019": 'self.getCO2019',
    }

    def getCO2019(self, personal_result_id):

        list_quotas = [u"技术/职能型",u"管理型",u"自主/独立型",u"安全/稳定型",u"创业型",u"服务型",u"挑战型",u"生活型"]
        dictquota_score = {u"技术/职能型":0,u"管理型":0.,u"自主/独立型":0,u"安全/稳定型":0,u"创业型":0,u"服务型":0,u"挑战型":0,u"生活型":0,}
        dictquota_desc = \
            {u"技术/职能型":
                {u"基本特征":
                    [u"技术/职能型职业锚，意味着您追求在技术/职能领域的成长和技能的不断提高，希望在工作中实践并应用这种技术/职能。您对自己的认可来自于您的专业水平，您喜欢面对专业领域内的挑战。",
                     u"作为技术/职能型职业锚的一员，您强调实际技术/功能等业务工作，注重个人在专业技能领域的进一步发展，希望有机会实践自己的技术才能，享受作为某方面专家带来的满足、愉悦。您通常不愿意选择一般管理型的工作，因为这是一种您难以施展自己技术才能的工种，也意味着您放弃在技术功能领域的成就。",
                     u"技术/职能型的您可能出现在许多领域，例如某些金融分析师专注于解决复杂的投资问题，一个工程师发现他非常擅长设计，一个销售员发现他独特的销售才能。"],
                 u"工作类型":u"您在职业选择时主要考虑工作的内容，即工作是否可以带来自己在专业方面的成功和技能的不断提高。喜欢领域内的挑战和独立开展工作，抵制难以施展自己技术才能的工作。",
                 u"薪酬福利":u"您希望薪酬福利可以反映技术、专业水平的高低。",
                 u"工作晋升":u"您看重技术或专业等级，而非职位的晋升。",
                 u"最佳认可方式":u"对您而言，来自本专业领域专家的肯定和认可，以及专业地位的提高，是最有效的激励方式。"},
             u"管理型":
                {u"基本特征":
                    [u"管理型职业锚，意味着您追求并致力于职位晋升，倾心于全面管理，独立负责一个单元，可以跨部门整合其他人的努力成果。管理型的您希望承担整体的责任，并将公司的成功与否看作衡量自己工作的标准。具体的技术/职能工作仅仅被看作是您通向全面管理层的必经之路。"
                     u"管理型职业锚的您强调实际的业务管理与控制，注重个人在一般管理与领导领域的进一步发展，希望有机会和时间展示自己的管理才能；管理型的您不愿意放弃任何在组织内获得更高职位的机会，您也愿意承担您所管理组织或单位的业绩与输出。"
                     u"如果您目前还处于技术或者职能工作的领域，您会把这看作是学习的必经过程，也愿意接受本功能组织的管理岗位，但您更愿意接受一般性管理的职位。希望能够依靠个人的分析能力、人际关系、团队领导能力、情商、以及负责任的态度，为本组织或者项目的成功贡献力量。"],
                 u"工作类型":u"管理型职业锚的您希望在工作中能够学习如何行使多项职责；如何综合利用来自多种渠道的信息；如何管理人数不断增加的员工队伍；以及如何运用人际交流技巧。",
                 u"薪酬福利":u"管理型职业锚的您认为薪酬是由所处职位所决定的，因此，管理型的您在管理职位上的追求，也代表了您对于高薪酬福利的期望。",
                 u"工作晋升":u"您拥护组织传统的职业发展道路，追求并致力于工作晋升，倾心于全面管理，独立负责一个部分，可以跨部门整合其他人的努力成果。管理型的您想去承担整体的责任，并将公司的成功与否看成自己的工作。",
                 u"最佳认可方式":u"您希望通过获得更高的薪水以及职位的晋升来得到认可，如果让您去管理大项目，或者邀请出席重要会议，或者派您去参加某些研讨会，使您得以提升自身管理技能，也是不错的认可方式。"},
             u"自主/独立型":
                {u"基本特征":
                    [u"自主/独立型职业锚，意味着您不会放弃任何可以以您的意志或方法定义您职业生涯发展的机会。您追求自主和独立，不愿意受别人约束，也不愿受程序、工作时间、着装方式等规范的制约。不管工作内容是什么，自主/独立型的您都希望能在工作过程中用自己的方式、工作习惯、时间进度和自己的标准来完成工作。"
                     u"为了追求自主、独立，您宁愿放弃安逸的工作环境或优厚的薪金待遇。"
                     u"自主/独立型的您，倾向于从事极具自由的职业，比如自由顾问、教授、独立的商务人士、销售员等等。如果您被局限在一个组织内，您希望职位能够具有灵活与独立性；您有时也会因为希望保留自主的权力而放弃晋升与发展的机会。"],
                 u"工作类型":u"您喜欢专业领域内职责描述清晰、时间明确的工作。对您而言，承包式或项目式工作，全职、兼职或是临时性的工作都是可以接受的。另外您倾向于为“有明确工作目标，却不限制工作完成方式的组织”效力。您能接受组织强加的工作目标，但希望按照自己喜欢的方式完成工作；",
                 u"薪酬福利":u"您喜欢基于工作绩效的工资、奖金，希望能当即付清；",
                 u"工作晋升":u"您希望基于自己以往的成就获得晋升，希望从新的岗位上获取更多的独立和自主权。如果新的职位赋予了您更高的头衔和更多责任，却剥夺了您自由工作的空间，您会感到难以接受；",
                 u"最佳认可方式":u"您最喜欢直接的表扬或认可，勋章、奖品、证书等奖励方式比晋升、获得头衔甚至是金钱更具吸引力。对您而言，如果能在工作上获取更大的自主空间，这将是最有效的激励方式。"},
             u"安全/稳定型":
                {u"基本特征":
                    [u"安全/稳定型职业锚的您主要关注点是争取一份稳定的职业，这种职业锚也显示了对于财务安全性（比如养老金、公积金或医疗保险）、雇佣安全性以及地区选择的重视。"
                     u"作为安全/稳定型中的一员，尽管您也可能因为才干获得在组织内的提升，但是您可能不太在意工作的内容或者是否能够得到职位的提升。"
                     u"安全/稳定型的您关注于围绕着安全与稳定构建全部的自我形象。安全/稳定型的您只有在已经获得职位的成功以及确定的稳定性后才能够显得放松。"],
                 u"工作类型":u"您希望获得一份长期的稳定职业，这些职业能够提供有保障的工作、体面的收入以及可靠的未来生活，这种可靠的未来生活通常是由良好的退休计划和较高的退休金来保证的，有可能的话，您会优先选择政府机关，医疗机构，教育行业，大型的外资或国有企业。",
                 u"薪资福利":u"您不追求一份令人羡慕的薪金，而更在意稳定长期的财务安全性。对于您来说，除了固定的薪资，您还在意福利的结构，包括各种保险，公积金，休假，固定投资等等。",
                 u"工作晋升":u"对于您来说，追求更为优越的职业或工作的晋升，如果意味着将要在您的生活中注入一种不稳定或保障较差的因素的话，那么您会觉得在一个熟悉的环境中维持一种稳定的、有保障的职业对您来说是更为重要的。",
                 u"最佳认可方式":u"来自组织对于您长期贡献与经验资历的表彰是组织对您最佳的认可方式；而一份长期的或无固定期限的合同，或者组织提供的完善的家庭保障计划，将是对您最好的激励方式。"},
             u"创业型":
                {u"基本特征":
                    [u"创业型职业锚，意味着您不会放弃任何可能创建属于您自己的团队或组织或企业的机会。您愿意基于自己的能力与意愿，承担风险并克服障碍。您愿意向其他人证明您能够依靠自己的努力创建一个企业。您可能为了学习与寻找机会而被雇佣，但是您一旦找到机会便会抽身而出。"
                     u"您愿意去证明您创建企业的成功，您的需求如此强烈使得您愿意去承受可能的失败直到最终成功。极强烈的创造欲使创业型的人要求标新立异、有所创造、并做好冒险的准备。"
                     u"大多数像您一样创业型职业锚的人成为了创业者、发明家或艺术家。但需要澄清的是，市场分析人员、研究开发人员、广告策划人员并不能归入这一类别，因为创业型人的主要动机和价值观是“创造”。"],
                 u"工作类型":u"您希望通过自己的努力创造新的公司、产品或服务。您相信自己是天才，并有很高的动力去证明您具有创造力，而且不断地接受新的挑战；",
                 u"薪资福利":u"您认为所有权和控制权对您才是最重要的，例如：年薪、股票或期权。您不会在意每月固定的薪资，或者定期的奖金，对您来说，获得与所有权与控制权所对应报酬才是最重要的；您希望得到金钱，但不是出于爱财的缘故，而是因为把金钱当作您完成了某件大事业的有形标志；",
                 u"工作晋升":u"您要求一定的权力和自由，可以不断去创造；",
                 u"最佳认可方式":u"您要求很高的自我认可和公众认可。创造完全属于自己的东西，例如：一件产品、服务、公司或反应成就的财富等。对于您来说，最佳的认可方式就是对您创造的“产品”的认可与赞扬，或者在公开场合给予您受之无愧的表扬。"},
             u"服务型":
                {u"基本特征":
                    [u"服务型职业锚的人一直在追求他们的核心价值，例如：帮助他人，改善人们的安全，通过新的产品消除疾病等。服务型的人一直追寻这种机会，即使变换公司，也不会接受无法实现这种价值的变动或工作提升。"
                     u"作为服务型职业锚的一员，意味着您不会放弃任何有可能创造某种价值的机会，比如改变人居环境，解决环境污染的问题，创造和谐的人际关系，帮助他人，改善人群的安全感，通过新产品的研发治疗疾病，以及其他方式。就算您所关注的工作或事宜有可能影响到组织的现状，您也会始终追求您的职业定位及其价值意义。您也会不愿意接受那些有可能使您不能关注于创造价值的职位转移或提升。"],
                 u"工作类型":u"您希望工作能够创造价值，对他人能有所帮助、使生活更美好。您希望能以自己的价值观影响组织乃至社会；",
                 u"薪资福利":u"您希望获得基于贡献的、公平的薪资，钱并不是您追求的根本；",
                 u"工作晋升":u"您希望通过认可您的贡献，给您更多的权力和自由来体现自己的价值；",
                 u"最佳认可方式":u"来自同事及上司的认可和支持，与他人共享自己的核心价值。通过自己的努力，给别人带来了帮助或促成了某项事业的成功。能给您继续提供为心中的理想打拼的机会，这才是对您的真正认可。"},
             u"挑战型":
                {u"基本特征":
                    [u"挑战型职业锚的您，喜欢解决看上去无法解决的问题，战胜强硬的对手，克服无法克服的障碍等。对挑战型的您而言，参加工作或职业的原因是工作允许您去战胜各种不可能。您需要新奇、变化和困难，如果工作非常容易，您马上就会厌倦这份工作。"
                     u"作为挑战型职业锚的一员，意味着您不会放弃任何发掘解决问题的方法，克服他人所不能克服的障碍，或者超越您竞争对手的机会。您认为自己可以征服任何事情或任何人；您将成功定义为“克服不可能的障碍，解决不可能解决的问题，或战胜非常强硬的对手”。随着自己的进步，您喜欢寻找越来越强硬的“挑战”，希望在工作中面临越来越艰巨的任务，并享受由战胜或征服而带来的成就感。"
                 u"需要说明的是，您的职业锚类型与技术/职能型之间存在一定差别，即技术/职能型的人只关注某一专业领域内的挑战并持续为之奋斗；而挑战型的人，一旦达成了成就或征服了困难，再让您去做同一类型的任务，就会感觉无聊之极。还有一些挑战型职业锚的人，将挑战定义成人际间的竞争。例如"],
                 u"工作类型":u"对您而言，一定水平的挑战是至关重要的，不管您的工作内容是什么，都需要有“挑战自我的机会”；",
                 u"薪酬福利":u"您希望基于所从事的项目或任务的挑战性、难度得到报酬。金钱并不是您的最终追求，您更看重工作中是否有挑战自我或挑战难题的机会；",
                 u"工作晋升":u"您希望自己的晋升能使自己的“工作为自己提供更多挑战困难或挑战自我的机会”，因而，如果职位提高了，挑战自我的机会减少了，那么您很快就会厌倦这个职位；",
                 u"最佳认可方式":u"您渴望战胜困难或征服对手后的成就感，因此，战胜挑战后的愉悦感会激励着您不断寻求难度更大的挑战。您对自己的认可基于挑战的成败，而不是外在的奖励，因此，对您来说，挑战即是认可，只要给您布置好下一个工作任务就行了。"},
             u"生活型":
                {u"基本特征":
                    [u"生活型职业锚的您，希望将生活的各个主要方面整合为一个整体，喜欢平衡个人的、家庭的和职业的需要，因此，生活型的您需要一个能够提供“足够弹性”的工作环境来实现这一目标。生活型的您甚至可以牺牲职业的一些方面，例如放弃职位的提升或调动，来换取三者的平衡。相对于具体的工作环境、工作内容，生活型的您更关注自己如何生活、在哪里居住、如何处理家庭事情及怎样自我提升等。"
                     u"生活型职业锚是综合了职业与家庭关系的一种职业定位。生活型职业锚现在变得越来越普遍，因为作为家庭主要成员的两方必须同时关注两个同样重要，但是有可能就是不同的职业选择。如果您在生活型方面的得分相对最高，意味着您不会放弃任何有助于整合或平衡个人的需求，与家庭的需求，或者与您职业的需求的机会。您期望那些与生活工作重要的因素能够相互融合成一体，因此，您也愿意去发展您的职业生涯以提供足够的灵活性满足这种融合。"],
                 u"工作类型":u"您希望为生活而工作，而不是为工作而生活，所以在工作上，您不会做过多份外之事。您期望您的工作内容是明确的。",
                 u"薪资福利":u"您不追求通过加班或参与项目的方式获得额外的收入，您追求属于您的那一份明确工作任务的所得。对于您来说，这份薪酬福利已经能够使您正常快乐的生活，而额外付出的努力获得的收入反而得不偿失。",
                 u"工作晋升":u"如果职位的晋升可能会带来对于生活家庭的负面的影响，您会毫不迟疑地拒绝；因为成功对您来说，不仅仅是在工作，而更是在生活与家庭上。",
                 u"最佳认可方式":u"弹性的工作时间安排可能是对您最有效的奖励。您不希望承担超出最低工作要求之外的其他工作，所以您也不会期待除了薪水以外的其他奖励。在您表现出色、工作高效的时候，如果能给您一个最大化非工作时间的机会，这将是对您最大的奖励！"}}

        list_scores = []
        list_mainquotas = []
        list_subquotas  = []
        dictquota_main = {}
        dictquota_sub = {}

        default_data = {
            "report_type": "",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "Score": list_scores,
                "MainTypes":list_mainquotas,
                "SubTypes":list_subquotas,
                "Main":dictquota_main,
                "Sub":dictquota_sub               
            }}

        frontname = settings.DATABASES['front']['NAME']
        sql_query = "select b.tag_value ,a.score from\
            (select question_id,answer_score score\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.question_id=b.object_id and b.tag_id=54\
            and b.is_active=True"

        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['co2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            else:
                default_data["msg"]["Age"] += u"岁"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())

            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                dictscore = {}
                for row in cursor.fetchall():
                    dictscore[row[0]]=row[1]
            
            dictquota_score[u"技术/职能型"] = dictscore['TF1']+dictscore['TF2']+dictscore['TF3']+dictscore['TF4']+dictscore['TF5']
            dictquota_score[u"管理型"] =dictscore['GM1']+dictscore['GM2']+dictscore['GM3']+dictscore['GM4']+dictscore['GM5']
            dictquota_score[u"自主/独立型"] = dictscore['AU1']+dictscore['AU2']+dictscore['AU3']+dictscore['AU4']+dictscore['AU5']
            dictquota_score[u"安全/稳定型"] = dictscore['SE1']+dictscore['SE2']+dictscore['SE3']+dictscore['SE4']+dictscore['SE5']
            dictquota_score[u"创业型"] =dictscore['EC1']+dictscore['EC2']+dictscore['EC3']+dictscore['EC4']+dictscore['EC5']
            dictquota_score[u"服务型"] = dictscore['SV1']+dictscore['SV2']+dictscore['SV3']+dictscore['SV4']+dictscore['SV5']
            dictquota_score[u"挑战型"] =dictscore['CH1']+dictscore['CH2']+dictscore['CH3']+dictscore['CH4']+dictscore['CH5']
            dictquota_score[u"生活型"] = dictscore['LS1']+dictscore['LS2']+dictscore['LS3']+dictscore['LS4']+dictscore['LS5']
            sortedlist = sorted(dictquota_score.items(), key=lambda d:d[1], reverse = True)
            
            for member in list_quotas:
                list_scores.append((member,dictquota_score[member]))
            
            No1 = sortedlist.pop(0)
            No2 = sortedlist.pop(0)
            list_mainquotas.append(No1[0])
            if No1[1] == No2[1]:
                list_mainquotas.append(No2[0])
                No1 = sortedlist.pop(0)
                No2 = sortedlist.pop(0)
            else :
                No1 = No2
                No2 = sortedlist.pop(0)

            list_subquotas.append(No1[0])
            if No1[1] == No2[1]:
                list_subquotas.append(No2[0])

            for ct in list_mainquotas:
                dictquota_main[ct] = dictquota_desc[ct]
            
            for ct in list_subquotas:
                dictquota_sub[ct] = dictquota_desc[ct]

        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS  

    def get_pec_maanshan(self, personal_result_id):

        dictquota_desc = {u"敬业尽责":u"按角色职责和规范要求工作并致力于与更高目标的达成",
                          u"积极进取":u"主动面对问题和挑战并承担解决，持续的努力投入",
                          u"合理认知":u"能以客观现实、全面的视角来看待事物并合理解释",
                          u"自我悦纳":u"客观评价自己，接纳肯定自己并对现实满意",
                          u"乐观自信":u"从客观、正面的角度积极看待问题，并相信自己有能力解决问题",
                          u"亲和利他":u"主动理解和关心他人并提供支持和帮助",
                          u"容纳差异":u"信任他人，能包容不足和差异并积极相处",
                          u"适应变化":u"接纳变化与多样，能灵活调整来融入环境和把握机会",}

        dictquota_score = {}                  

        default_data = {
            "report_type": "",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "Adv": [
                ],
                "Dis": [
                ],
            }}
        frontname = settings.DATABASES['front']['NAME']
        sql_query = "select b.tag_value ,a.score from\
                    (select question_id,LEAST(sum(answer_score),4) score\
                    from " + frontname + ".front_peoplesurveyrelation a,\
                    " + frontname + ".front_userquestionanswerinfo b\
                    where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
                    and a.project_id=b.project_id and a.is_active=true and b.is_active=true\
                    group by b.question_id) a,research_questiontagrelation b\
                    where a.question_id=b.object_id and b.tag_id=54\
                    and b.is_active=True"
        try:

            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.ROOT_HOST+'maanshan/'+personal_result_id
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", u"未知")
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())

            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                dictscore = {}
                for row in cursor.fetchall():
                    dictscore[row[0]]=row[1]
            
            weight = 25
            dictquota_score[u"敬业尽责"] = round(np.mean([dictscore['NM1'],dictscore['NM2']]) * weight,2)
            dictquota_score[u"积极进取"] = round(np.mean([dictscore['NM3'],dictscore['NM4']]) * weight,2)
            dictquota_score[u"合理认知"] = round(np.mean([dictscore['NM5'],dictscore['NM6']]) * weight,2)
            dictquota_score[u"自我悦纳"] = round(np.mean([dictscore['NM7'],dictscore['NM8']]) * weight,2)
            dictquota_score[u"乐观自信"] = round(np.mean([dictscore['NM9'],dictscore['NM10']]) * weight,2)
            dictquota_score[u"亲和利他"] = round(np.mean([dictscore['NM11'],dictscore['NM12']]) * weight,2)
            dictquota_score[u"容纳差异"] = round(np.mean([dictscore['NM13'],dictscore['NM14']]) * weight,2)
            dictquota_score[u"适应变化"] = round(np.mean([dictscore['NM15'],dictscore['NM16']]) * weight,2)
            sortedlist= sorted(dictquota_score.items(), key=lambda d:d[1], reverse = True)

            default_data["msg"]["Adv"].append({sortedlist[0][0]:dictquota_desc[sortedlist[0][0]]})
            default_data["msg"]["Adv"].append({sortedlist[1][0]:dictquota_desc[sortedlist[1][0]]})
            default_data["msg"]["Adv"].append({sortedlist[2][0]:dictquota_desc[sortedlist[2][0]]})

            default_data["msg"]["Dis"].append({sortedlist[-1][0]:dictquota_desc[sortedlist[-1][0]]})
            default_data["msg"]["Dis"].append({sortedlist[-2][0]:dictquota_desc[sortedlist[-2][0]]})
            default_data["msg"]["Dis"].append({sortedlist[-3][0]:dictquota_desc[sortedlist[-3][0]]})

        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS        

    def get_ygzwts_value(self, personal_result_id):
        u"""员工自我提升算法"""

        default_data = {
            "report_type": "员工自我提升",
            "msg": {
                "Name": "yyy",
                "TestTime": "2018.11.16",
                "chart": [
                    {"name": "尽职尽责", "score": 49},
                    {"name": "高效落地", "score": 555},
                    {"name": "主动承担", "score": 7},
                    {"name": "激情投入", "score": 76},
                    {"name": "严谨细致", "score": 45},
                    {"name": "精益求精", "score": 777},
                    {"name": "同理", "score": 3},
                    {"name": "利他", "score": 2},
                    {"name": "寻求成长", "score": 1},
                    {"name": "反思调整", "score": 0},
                    {"name": "接纳不足", "score": 999},
                    {"name": "自我肯定", "score": 3},
                    {"name": "正面积极", "score": 4},
                    {"name": "乐观向上", "score": 56},
                    {"name": "接纳变化", "score": 55533},
                    {"name": "灵活调整", "score": 9},
                ],
            }
        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            facet_score_map = json.loads(people_result.facet_score)
            for info in default_data["msg"]["chart"]:
                for facet_id in facet_score_map:
                    if facet_score_map[facet_id]["name"] == info["name"]:
                        if facet_score_map[facet_id]["name"] == u"主动承担":
                            if int(facet_score_map[facet_id]["substandard_id"]) == 4104:
                                # 主动承担 名称重复， 采用自我提升维度下面的
                                info["score"] = round(facet_score_map[facet_id]["score"], 2)
                                break
                        else:
                            info["score"] = round(facet_score_map[facet_id]["score"], 2)
                            break
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_mental_health_value(self, personal_result_id):
        u"""心理健康算法"""
        default_data = {"report_type": "心理健康模板", "msg": {
            "Name": "默认数据",
            "Sex": "男",
            "Age": "25",
            "CompletionTime": "38分20秒",
            "Validation": 25,
            "chart": [{"name": "躯体反应", "score": 6},
                      {"name": "回避行为", "score": 7},
                      {"name": "幻想行为", "score": 10},
                      {"name": "自责行为", "score": 20},
                      {"name": "强迫行为", "score": 25},
                      {"name": "偏执心理", "score": 21},
                      {"name": "嫉妒心理", "score": 13},
                      {"name": "人际适应", "score": 15},
                      {"name": "孤独感受", "score": 17},
                      {"name": "依赖心理", "score": 19},
                      {"name": "猜疑心理", "score": 14},
                      {"name": "焦虑情绪", "score": 25},
                      {"name": "冲动控制", "score": 17},
                      {"name": "抑郁倾向", "score": 21},
                      {"name": "环境适应", "score": 18},
                      {"name": "恐惧心理", "score": 19},
                      {"name": "身心同一", "score": 20},
                      ],
        }
                        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score:
                SurveyAlgorithm.algorithm_xljk(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value("性别", "未知")
            default_data["msg"]["Age"] = people.get_info_value("年龄", "未知")
            used_time = people_result.used_time
            default_data["msg"]["CompletionTime"] = u"%s分%s秒" % (used_time / 60, used_time % 60)
            default_data["msg"]["Validation"] = people_result.praise_score
            substandard_scores = []
            dimension_score_map = people_result.dimension_score_map
            for info in default_data["msg"]["chart"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"] == info["name"]:
                        info["score"] = dimension_score_map[dimension_id]["score"]
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_mental_health_value_en(self, personal_result_id):
        u"""心理健康算法英文"""
        default_data = {"report_type": "心理健康模板", "msg": {
            "Name": "",
            "Sex": "man",
            "Age": "25",
            "CompletionTime": "38分20秒",
            "Validation": 22,
            "chart": [{"name": "躯体反应", "score": 6, "en_name": "Tenseness"},
                      {"name": "回避行为", "score": 7, "en_name": "Avoidance Behavior"},
                      {"name": "幻想行为", "score": 10, "en_name": "Fantasy Behavior"},
                      {"name": "自责行为", "score": 20, "en_name": "Self-accusation Behaviour"},
                      {"name": "强迫行为", "score": 25, "en_name": "Compulsive Behavior"},
                      {"name": "偏执心理", "score": 21, "en_name": "Paranoid Psychological"},
                      {"name": "嫉妒心理", "score": 13, "en_name": "Jealous Psychology"},
                      {"name": "人际适应", "score": 15, "en_name": "Interpersonal Adaptation"},
                      {"name": "孤独感受", "score": 17, "en_name": "Loneliness"},
                      {"name": "依赖心理", "score": 19, "en_name": "Psychological Dependence"},
                      {"name": "猜疑心理", "score": 14, "en_name": "Suspicion Psychological"},
                      {"name": "焦虑情绪", "score": 25, "en_name": "Anxiety Emotion"},
                      {"name": "冲动控制", "score": 17, "en_name": "Impulse Control"},
                      {"name": "抑郁倾向", "score": 21, "en_name": "Depressive Tendency"},
                      {"name": "环境适应", "score": 18, "en_name": "Environmental Adaptation"},
                      {"name": "恐惧心理", "score": 19, "en_name": "Feared Psychology"},
                      {"name": "身心同一", "score": 20, "en_name": "psycho-physicalIdentity"},
                      ],
        }
                        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score:
                SurveyAlgorithm.algorithm_xljk(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value("性别", "未知")
            default_data["msg"]["Age"] = people.get_info_value("年龄", "未知")
            used_time = people_result.used_time
            default_data["msg"]["CompletionTime"] = u"%s分%s秒" % (used_time / 60, used_time % 60)
            default_data["msg"]["Validation"] = people_result.praise_score
            substandard_scores = []
            dimension_score_map = people_result.dimension_score_map
            for info in default_data["msg"]["chart"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"] == info["name"]:
                        info["score"] = dimension_score_map[dimension_id]["score"]
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_work_value(self, personal_result_id):
        u"""工作价值观算法"""
        order_array = [
            "挑战/成就", "自主/独立", "专业/技术", "变化/探索", "艺术/文化",
            "认可/表现", "地位/职位", "权力/影响", "利他/慈善", "社交/人际",
            "归属/团队", "经济/报酬", "安全/稳定", "舒适/家庭"
        ]
        default_data = {
            "report_type": "工作价值观",
            "msg": {
                "Name": "默认数据",
                "TestTime": "2018年08月06日",
                "ChartDataModel": [],
                "char": []
            }
        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["TestTime"] = time_format5(people_result.finish_time)
            substandard_scores = []
            substandard_score_map = people_result.substandard_score_map
            dismension_info = []
            for sub_name in order_array:
                find_sub_name = False
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == sub_name:
                        find_sub_name = True
                        substandard_scores.append({
                            "name": substandard_score_map[substandard_id]["name"],
                            "score": substandard_score_map[substandard_id]["score"]
                        })
                        substandard = ResearchSubstandard.objects.get(id=substandard_id)
                        dismension = ResearchDimension.objects.get(id=substandard.dimension_id)
                        dismension_info.append({
                            "name": substandard.name,
                            "Dimension": dismension.name

                        })
                        break
                if not find_sub_name:
                    substandard_scores.append({
                        "name": sub_name,
                        "score": 0,
                    })
                    dismension_info.append({
                        "name": sub_name,
                        "Dimension": u"未知"

                    })
            # sorted_substandard_scores = sorted(substandard_scores, key=operator.itemgetter('score'), reverse=False)
            default_data["msg"]["ChartDataModel"] = substandard_scores
            default_data["msg"]["char"] = dismension_info
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_professional_value(self, personal_result_id):
        u"""职业个性DISC算法"""
        default_data = {
            "report_type": "职业个性DISC",
            "msg": {
                "Name": "默认数据",
                "Sex": "男",
                "Age": "39",
                "CompleteTime": None,
                "ChartSelfImage_Indicator": [
                    {"name": "D", "score": 0},
                    {"name": "I", "score": 0},
                    {"name": "S", "score": 0},
                    {"name": "C", "score": 0}
                ],
                "ChartWorkMask_Indicator": [
                    {"name": "D", "score": 0},
                    {"name": "I", "score": 0},
                    {"name": "S", "score": 0},
                    {"name": "C", "score": 0}
                ],
                "ChartBR_UnderStress_Indicator": [
                    {"name": "D", "score": 0},
                    {"name": "I", "score": 0},
                    {"name": "S", "score": 0},
                    {"name": "C", "score": 0}
                ]
            }
        }
        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.substandard_score:
                SurveyAlgorithm.algorithm_disc(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", u"未知")
            substandard_score_map = people_result.substandard_score_map
            if people_result.finish_time:
                default_data["msg"]["CompleteTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["CompleteTime"] = time_format4(datetime.datetime.now())

            # difference
            for info in default_data["msg"]["ChartSelfImage_Indicator"]:
                if "difference" in substandard_score_map and info["name"] in substandard_score_map["difference"]:
                    info["score"] = substandard_score_map["difference"][info["name"]]
            # like
            for info in default_data["msg"]["ChartWorkMask_Indicator"]:
                if "like" in substandard_score_map and info["name"] in substandard_score_map["like"]:
                    info["score"] = substandard_score_map["like"][info["name"]]
            # not_like
            for info in default_data["msg"]["ChartBR_UnderStress_Indicator"]:
                # 兼容错误key
                if "not_lie" in substandard_score_map and info["name"] in substandard_score_map["not_lie"]:
                    info["score"] = substandard_score_map["not_lie"][info["name"]]
                if "not_like" in substandard_score_map and info["name"] in substandard_score_map["not_like"]:
                    info["score"] = substandard_score_map["not_like"][info["name"]]
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_professional_value_new(self, personal_result_id):
        from front.util.disc import test_job, test_statement
        res = self.get_professional_value(personal_result_id)[0]
        origin_msg = res["msg"]
        disc = res["disc"] = {
            "ChartWorkMask_Indicator": [],
            "ChartBR_UnderStress_Indicator": [],
            "ChartSelfImage_Indicator": [],
        }
        for title in ["ChartWorkMask_Indicator", "ChartBR_UnderStress_Indicator", "ChartSelfImage_Indicator"]:
            work_mask = origin_msg[title]

            for dic in work_mask:
                name = dic["name"]
                score = dic["score"]
                finally_score = test_job[title][name][score]
                dic["finally"] = finally_score
                if finally_score >= 14.5:
                    res["disc"][title].append([name, score])

        for item in disc:
            name_score_list = disc.get(item)
            name_score_list.sort(key=lambda x: x[1], reverse=True)
            # statement_key = disc.get(item)
            statement_key = ''.join([i[0] for i in name_score_list])
            if not statement_key:
                statement_key = u'下移位'
            if statement_key == "DISC":
                statement_key = u'上移位'
            statement = test_statement[statement_key]
            disc[item] = [statement_key, statement]

        return res, ErrorCode.SUCCESS

    def get_psychological_capital_value(self, personal_result_id):
        u"""心理资本算法"""

        default_data = {
            "report_type": "心理资本",
            "msg": {
                "Name": "Bob",
                "Sex": "男",
                "Age": "28",
                "CompletionTime": "30分20秒",
                "Validation": 0,
                "ChartDataModel": [
                    {"name": "进取性", "score": 0},
                    {"name": "支配性", "score": 0},
                    {"name": "亲和性", "score": 0},
                    {"name": "开放性", "score": 0},
                    {"name": "乐观性", "score": 0},
                    {"name": "变通性", "score": 0},
                    {"name": "内省性", "score": 0},
                    {"name": "独立性", "score": 0},
                    {"name": "坚韧性", "score": 0},
                    {"name": "自律性", "score": 0},
                    {"name": "悦纳性", "score": 0},
                    {"name": "稳定性", "score": 0},
                    {"name": "自信心", "score": 0},
                    {"name": "尽责性", "score": 0},
                    {"name": "容人性", "score": 0},
                    {"name": "利他性", "score": 0},
                ],
            }
        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value("性别", "未知")
            default_data["msg"]["Age"] = people.get_info_value("年龄", "未知")
            used_time = people_result.used_time
            default_data["msg"]["CompletionTime"] = u"%s分%s秒" % (used_time / 60, used_time % 60)
            default_data["msg"]["Validation"] = people_result.praise_score
            substandard_scores = []
            substandard_score_map = people_result.substandard_score_map
            for info in default_data["msg"]["ChartDataModel"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == info["name"]:
                        info["score"] = round(substandard_score_map[substandard_id]["normsdist_score"], 2)
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_ha_measure_value(self, personal_result_id):
        u"""幸福指数
        "score":标准分， "raw_score"：原始分，"percentage"：百分比
        """
        SCORE_MAP = [2.28, 6.69, 15.86, 30.85, 50.5, 69.15, 84.13, 93.31, 97.72, 100]
        default_data = {"report_type": "幸福能力", "msg": {
            "Name": "",
            "Sex": "男",
            "Age": "20",
            "TestTime": "2018.09.05",
            "ChartEudaemonia":
                [
                    {"name": "乐观积极", "score": 6, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "自信坚韧", "score": 8, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "合理归因", "score": 7, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "情绪调节", "score": 9, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "意义寻求", "score": 5, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "自主定向", "score": 7, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "专注投入", "score": 4, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "自我拓展", "score": 3, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "灵活变通", "score": 2, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "包容差异", "score": 9, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "亲和利他", "score": 7, "raw_score": 57.5, "percentage": '15.4%'},
                    {"name": "自我悦纳", "score": 6, "raw_score": 57.5, "percentage": '15.4%'},

                ]

        }
                        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_xfzs(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value("性别", "不详")
            default_data["msg"]["Age"] = people.get_info_value("年龄", "不详")
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            substandard_scores = []
            substandard_score_map = people_result.substandard_score_map
            for info in default_data["msg"]["ChartEudaemonia"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == info["name"]:
                        info["raw_score"] = round(substandard_score_map[substandard_id]["score"], 2)
                        percentage_score = round(substandard_score_map[substandard_id].get("normsdist_score", 0), 2)
                        info["percentage"] = "%s%%" % percentage_score
                        if percentage_score > 100:
                            info["score"] = 10
                        else:
                            for index, index_score in enumerate(SCORE_MAP):
                                if percentage_score <= index_score:
                                    info["score"] = index + 1
                                    break
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_ha_measure_value_en(self, personal_result_id):
        u"""幸福指数英文
        "score":标准分， "raw_score"：原始分，"percentage"：百分比
        """
        SCORE_MAP = [2.28, 6.69, 15.86, 30.85, 50.5, 69.15, 84.13, 93.31, 97.72, 100]
        default_data = {"report_type": "幸福能力", "msg": {
            "Name": "",
            "Sex": "man",
            "Age": "20",
            "TestTime": "2018.09.05",
            "ChartEudaemonia":
                [
                    {"name": "乐观积极", "score": 6, "en_name": "Optimistic and positive"},
                    {"name": "自信坚韧", "score": 8, "en_name": "Confident and tenacity"},
                    {"name": "合理归因", "score": 7, "en_name": "Reasoning"},
                    {"name": "情绪调节", "score": 9, "en_name": "Emotion regulation"},
                    {"name": "意义寻求", "score": 5, "en_name": "Meaning pursuit"},
                    {"name": "自主定向", "score": 7,"en_name": "Autonomy and direction"},
                    {"name": "专注投入", "score": 4, "en_name": "Devotion"},
                    {"name": "自我拓展", "score": 3, "en_name": "Self enhancing"},
                    {"name": "灵活变通", "score": 2, "en_name": "Flexibility"},
                    {"name": "包容差异", "score": 9, "en_name": "Diversity"},
                    {"name": "亲和利他", "score": 7, "en_name": "Affinity and altruism"},
                    {"name": "自我悦纳", "score": 6, "en_name": "Self acceptance"},

                ]

        }
                        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_xfzs(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value("性别", "unknown")
            default_data["msg"]["Age"] = people.get_info_value("年龄", "unknown")
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            substandard_scores = []
            substandard_score_map = people_result.substandard_score_map
            for info in default_data["msg"]["ChartEudaemonia"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == info["name"]:
                        info["raw_score"] = round(substandard_score_map[substandard_id]["score"], 2)
                        percentage_score = round(substandard_score_map[substandard_id].get("normsdist_score", 0), 2)
                        info["percentage"] = "%s%%" % percentage_score
                        if percentage_score > 100:
                            info["score"] = 10
                        else:
                            for index, index_score in enumerate(SCORE_MAP):
                                if percentage_score <= index_score:
                                    info["score"] = index + 1
                                    break
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_happiness_needs(self, personal_result_id):

        """
        chart1，chart2，chart3  需要根据指标分值 由高到低 进行排序
        report_type_id  : HappinessNeeds
        幸福需求的第一级指标是维度，第二级指标是指标
        """

        default_data = {"report_type": "幸福需求", "msg": {
            "Name": "666",
            "Sex": "男",
            "Age": "25",
            "TestTime": "2018年10月26日",
            # 指标（整体）
            "chart1": [
                # {'安全健康', 'score': 100, 'dimension': '安全保障需求'},
                # {'环境舒适', 'score': 90, 'dimension': '安全保障需求'},
                # {'物质保障', 'score': 80, 'dimension': '安全保障需求'},
                # {'休闲娱乐', 'score': 70, 'dimension': '安全保障需求'},
                # {'职业稳定', 'score': 60, 'dimension': '安全保障需求'},
                # {'亲和倾向', 'score': 40, 'dimension': '情感归属需求'},
                # {'友谊友爱', 'score': 30, 'dimension': '情感归属需求'},
                # {'关系信任', 'score': 20, 'dimension': '情感归属需求'},
                # {'人际支持', 'score': 20, 'dimension': '情感归属需求'},
                # {'群体归属', 'score': 20, 'dimension': '情感归属需求'},
                # {'寻求认可', 'score': 20, 'dimension': '尊重认可需求'},
                # {'获得肯定', 'score': 20, 'dimension': '尊重认可需求'},
                # {'声望地位', 'score': 20, 'dimension': '尊重认可需求'},
                # {'自我尊重', 'score': 10, 'dimension': '尊重认可需求'},
                # {'自主决定', 'score': 10, 'dimension': '尊重认可需求'},
                # {'目标定向', 'score': 10, 'dimension': '成长成就需求'},
                # {'能力成长', 'score': 10, 'dimension': '成长成就需求'},
                # {'探索创新', 'score': 10, 'dimension': '成长成就需求'},
                # {'成就导向', 'score': 10, 'dimension': '成长成就需求'},
                # {'权力影响', 'score': 10, 'dimension': '成长成就需求'},
                # {'助人利他', 'score': 10, 'dimension': '使命利他需求'},
                # {'责任担当', 'score': 10, 'dimension': '使命利他需求'},
                # {'意义追求', 'score': 10, 'dimension': '使命利他需求'},
                # {'使命驱动', 'score': 10, 'dimension': '使命利他需求'},
                # {'社会促进', 'score': 10, 'dimension': '使命利他需求'},

            ],
            # 指标（生活）
            "chart2": [
                # {'安全健康', 'score': 100, 'dimension': '安全保障需求'},
                # {'环境舒适', 'score': 100, 'dimension': '安全保障需求'},
                # {'物质保障', 'score': 100, 'dimension': '安全保障需求'},
                # {'休闲娱乐', 'score': 100, 'dimension': '安全保障需求'},
                # {'职业稳定', 'score': 100, 'dimension': '安全保障需求'},
                # {'亲和倾向', 'score': 40, 'dimension': '情感归属需求'},
                # {'友谊友爱', 'score': 30, 'dimension': '情感归属需求'},
                # {'关系信任', 'score': 20, 'dimension': '情感归属需求'},
                # {'人际支持', 'score': 20, 'dimension': '情感归属需求'},
                # {'群体归属', 'score': 20, 'dimension': '情感归属需求'},
                # {'寻求认可', 'score': 20, 'dimension': '尊重认可需求'},
                # {'获得肯定', 'score': 20, 'dimension': '尊重认可需求'},
                # {'声望地位', 'score': 20, 'dimension': '尊重认可需求'},
                # {'自我尊重', 'score': 10, 'dimension': '尊重认可需求'},
                # {'自主决定', 'score': 10, 'dimension': '尊重认可需求'},
                # {'目标定向', 'score': 10, 'dimension': '成长成就需求'},
                # {'能力成长', 'score': 10, 'dimension': '成长成就需求'},
                # {'探索创新', 'score': 10, 'dimension': '成长成就需求'},
                # {'成就导向', 'score': 10, 'dimension': '成长成就需求'},
                # {'权力影响', 'score': 10, 'dimension': '成长成就需求'},
                # {'助人利他', 'score': 10, 'dimension': '使命利他需求'},
                # {'责任担当', 'score': 10, 'dimension': '使命利他需求'},
                # {'意义追求', 'score': 10, 'dimension': '使命利他需求'},
                # {'使命驱动', 'score': 10, 'dimension': '使命利他需求'},
                # {'社会促进', 'score': 10, 'dimension': '使命利他需求'},

            ],
            # 指标（工作）
            "chart3": [
                # {'亲和倾向', 'score': 100, 'dimension': '情感归属需求'},
                # {'友谊友爱', 'score': 100, 'dimension': '情感归属需求'},
                # {'关系信任', 'score': 100, 'dimension': '情感归属需求'},
                # {'人际支持', 'score': 100, 'dimension': '情感归属需求'},
                # {'群体归属', 'score': 100, 'dimension': '情感归属需求'},
                # {'安全健康', 'score': 50, 'dimension': '安全保障需求'},
                # {'环境舒适', 'score': 40, 'dimension': '安全保障需求'},
                # {'物质保障', 'score': 30, 'dimension': '安全保障需求'},
                # {'休闲娱乐', 'score': 30, 'dimension': '安全保障需求'},
                # {'职业稳定', 'score': 30, 'dimension': '安全保障需求'},
                #
                # {'寻求认可', 'score': 20, 'dimension': '尊重认可需求'},
                # {'获得肯定', 'score': 20, 'dimension': '尊重认可需求'},
                # {'声望地位', 'score': 20, 'dimension': '尊重认可需求'},
                # {'自我尊重', 'score': 10, 'dimension': '尊重认可需求'},
                # {'自主决定', 'score': 10, 'dimension': '尊重认可需求'},
                # {'目标定向', 'score': 10, 'dimension': '成长成就需求'},
                # {'能力成长', 'score': 10, 'dimension': '成长成就需求'},
                # {'探索创新', 'score': 10, 'dimension': '成长成就需求'},
                # {'成就导向', 'score': 10, 'dimension': '成长成就需求'},
                # {'权力影响', 'score': 10, 'dimension': '成长成就需求'},
                # {'助人利他', 'score': 10, 'dimension': '使命利他需求'},
                # {'责任担当', 'score': 10, 'dimension': '使命利他需求'},
                # {'意义追求', 'score': 10, 'dimension': '使命利他需求'},
                # {'使命驱动', 'score': 10, 'dimension': '使命利他需求'},
                # {'社会促进', 'score': 10, 'dimension': '使命利他需求'},

            ],
            # 维度名  分值
            "chart4": [
                # {'安全保障需求', 'score': 100, },
                # {'使命利他需求', 'score': 90, },
                # {'成长成就需求', 'score': 80, },
                # {'尊重认可需求', 'score': 70, },
                # {'情感归属需求', 'score': 60, },
            ]
        }}
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_xfxq(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value("性别", "不详")
            default_data["msg"]["Age"] = people.get_info_value("年龄", "不详")
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format5(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format5(datetime.datetime.now())
            substandard_score_map = people_result.substandard_score_map
            dismension_names = []
            whole_substandard_names = []
            for substandard_id in substandard_score_map:
                substandard_info = substandard_score_map[substandard_id]
                if substandard_info["name"] not in dismension_names:
                    default_data["msg"]["chart4"].append({
                        "name": substandard_info["name"],
                        "score": round(substandard_info["whole_score"], 2),
                    })
                    dismension_names.append(substandard_info["name"])
                for csubstandard_info in substandard_info["child_substandard"]:
                    if csubstandard_info["name"] not in whole_substandard_names:
                        default_data["msg"]["chart1"].append({
                            "name": csubstandard_info["name"],
                            "score": round(csubstandard_info["whole_score"], 2),
                            "dimension": substandard_info["name"]
                        })
                        whole_substandard_names.append(csubstandard_info["name"])
                    if substandard_info["dismension_name"].find("工作") > -1:
                        default_data["msg"]["chart3"].append({
                            "name": csubstandard_info["name"],
                            "score": round(csubstandard_info["score"], 2),
                            "dimension": substandard_info["name"]
                        })
                    elif substandard_info["dismension_name"].find("生活") > -1:
                        default_data["msg"]["chart2"].append({
                            "name": csubstandard_info["name"],
                            "score": round(csubstandard_info["score"], 2),
                            "dimension": substandard_info["name"]
                        })

            default_data["msg"]["chart1"].sort(lambda x, y: cmp(x['score'], y['score']), reverse=True)
            default_data["msg"]["chart2"].sort(lambda x, y: cmp(x['score'], y['score']), reverse=True)
            default_data["msg"]["chart3"].sort(lambda x, y: cmp(x['score'], y['score']), reverse=True)
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_capacity_evaluation_value(self, personal_result_id):
        u"""能力测评算法"""

        default_data = {
            "report_type": "能力测评",
            "msg": {
                "Name": "",
                "TestTime": "2018.09.05",
                "chart": [
                    {"name": "客户驱动", "score": 0},
                    {"name": "系统推进", "score": 0},
                    {"name": "创新求变", "score": 0},
                    {"name": "情绪调节", "score": 0},
                    {"name": "跨界整合", "score": 0},
                    {"name": "激发信任", "score": 0},
                    {"name": "释放潜能", "score": 0},
                    {"name": "促进成长", "score": 0},
                    {"name": "自我超越", "score": 0},
                    {"name": "激情进取", "score": 0},
                    {"name": "客户思维", "score": 0},
                    {"name": "精益求精", "score": 0},
                    {"name": "思维能力", "score": 0},
                    {"name": "沟通能力", "score": 0},
                    {"name": "合作能力", "score": 0},
                    {"name": "学习能力", "score": 0},
                ],
            }
        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            substandard_score_map = people_result.substandard_score_map
            for info in default_data["msg"]["chart"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == info["name"]:
                        info["score"] = round(substandard_score_map[substandard_id]["score"], 2)
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_c1_value(self, personal_result_id):
        u"""能力测评算法1"""

        default_data = {
            "report_type": "能力测评1",
            "msg": {
                "Name": "",
                "TestTime": "2018.10.28",
                "chart": [
                    {"name": "客户驱动", "score": 49},
                    {"name": "系统推进", "score": 55},
                    {"name": "创新求变", "score": 7},
                    {"name": "共启愿景", "score": 76},
                    {"name": "跨界整合", "score": 45},
                    {"name": "激发信任", "score": 34},
                    {"name": "释放潜能", "score": 3},
                    {"name": "促进成长", "score": 2},
                    {"name": "自我超越", "score": 1},
                    {"name": "激情进取", "score": 0},
                    {"name": "客户思维", "score": 2},
                    {"name": "精益求精", "score": 3},

                ],
            }
        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            substandard_score_map = people_result.substandard_score_map
            for info in default_data["msg"]["chart"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == info["name"]:
                        info["score"] = round(substandard_score_map[substandard_id]["score"], 2)
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_c2_value(self, personal_result_id):
        u"""能力测评算法2"""

        default_data = {
            "report_type": "能力测评2",
            "msg": {
                "Name": "",
                "TestTime": "2018.10.30",
                "chart": [

                    {"name": "自我超越", "score": 1},
                    {"name": "激情进取", "score": 0},
                    {"name": "客户思维", "score": 2},
                    {"name": "精益求精", "score": 3},
                    {"name": "思维能力", "score": 4},
                    {"name": "沟通能力", "score": 56},
                    {"name": "合作能力", "score": 7},
                    {"name": "学习能力", "score": 9},

                ],
            }
        }

        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            substandard_score_map = people_result.substandard_score_map
            for info in default_data["msg"]["chart"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == info["name"]:
                        info["score"] = round(substandard_score_map[substandard_id]["score"], 2)
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    #  行为风格算法 获取值
    def get_xwfg_value(self, personal_result_id):
        u"""行为风格算法"""
        default_data = {
            "report_type": "行为风格模板",
            "msg": {
                "Name": "666",
                "Sex": "男",
                "Age": "25",
                "TestTime": "2018.10.12",
                "CompletionTime": "38分20秒",
                "Validation": 25,
                # name  维度名称，score: 强度转换分值  按照以下顺序取值
                "chart": [{"name": u"能量指向（外向-内向）", "score": 20},
                          {"name": u"信息加工方式（思考-情感）", "score": 30},
                          {"name": u"信息收集方式（感觉-直觉）", "score": 30},
                          {"name": u"行动方式（判断-知觉）", "score": 20},
                          ],
                # 对应方向 内向  情感  直觉  知觉 百分比得分,按照以下顺序取值
                "chart2": [{"name": u"内向", "score": 20},
                           {"name": u"直觉", "score": 30},
                           {"name": u"情感", "score": 30},
                           {"name": u"知觉", "score": 20},
                           ],
            }}
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            # if not people_result.dimension_score or not people_result.substandard_score:
                # SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
            time.sleep(2)
            SurveyAlgorithm.algorithm_xwfg(personal_result_id, form_type=Survey.FORM_TYPE_NORMAL)
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", u"未知")
            used_time = people_result.used_time
            default_data["msg"]["CompletionTime"] = u"%s分%s秒" % (used_time / 60, used_time % 60)
            # try:
            #     seconds = (people_result.finish_time - people_result.begin_answer_time).seconds
            #     minute_t = seconds / 60
            #     seconds_t = seconds % 60
            #     default_data["msg"]["CompletionTime"] = "{}分{}秒".format(minute_t, seconds_t)
            # except:
            #     default_data["msg"]["CompletionTime"] = "0分0秒"
            default_data["msg"]["Validation"] = people_result.praise_score
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            dimension_score_map = people_result.dimension_score_map
            for info in default_data["msg"]["chart"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][:3] == info["name"][:3]:
                        info["score"] = dimension_score_map[dimension_id]["change_score"]
                        break
            for info in default_data["msg"]["chart2"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["percente_name"][:1] == info["name"][:1]:
                        info["score"] = int(round(100 - abs(dimension_score_map[dimension_id]["percente_score"])))
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_xxwfg_value(self, personal_result_id):
        u"""行为风格算法"""
        default_data = {
            "msg": {
                "personal": {
                    "Name": "",
                    "Sex": "",
                    "Age": "",
                    "TestTime": "",
                },
                "style": None,
                "score": None,
            }
        }
        chart = [
            {"name": u"内向", },
            {"name": u"直觉", },
            {"name": u"情感", },
            {"name": u"知觉", },
        ]
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT

            SurveyAlgorithm.algorithm_xwfg(personal_result_id, form_type=Survey.FORM_TYPE_NORMAL)
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["personal"]["Name"] = people.display_name
            default_data["msg"]["personal"]["Sex"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["personal"]["Age"] = people.get_info_value(u"年龄", u"未知")

            if people_result.finish_time:
                default_data["msg"]["personal"]["TestTime"] = time_format5(people_result.finish_time)
            else:
                default_data["msg"]["personal"]["TestTime"] = time_format5(datetime.datetime.now())
            dimension_score_map = people_result.dimension_score_map

            for info in chart:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["percente_name"][:1] == info["name"][:1]:
                        info["score"] = int(round(100 - abs(dimension_score_map[dimension_id]["percente_score"])))
                        break
            score = [(100-int(i["score"]), i["score"]) for i in chart]
            judge = [("E", "I"), ("S", "N"), ("T", "F"), ("J", "P")]
            ret_score = {"l_score": [], "r_score": []}

            for i in score:
                ret_score["l_score"].append(i[0])
                ret_score["r_score"].append(i[1])
            # 行为风格特征  e.g.: ENTJ
            characteristics = ''
            for i in xrange(len(score)):
                j = 0 if score[i][0] >= int(score[i][1]) else 1
                characteristics += judge[i][j]

            character = {
                "ENFJ": {
                    "content": "教导型",
                    "description": [
                        "您善于社交、易感应、善劝服。您精力旺盛，热情洋溢，能很快理解他人情感的需要、动机和所忧虑的事情，因此能做到与他人保持协调。",
                        "您把注意力放在帮助他人，鼓励他人进步向上。您是催化剂，能引发出他人的最佳状态。既可以做有号召力的领袖，也可以做忠实的追随者。",
                        "您性情平和，心胸宽阔，且很圆滑，很会促进周边关系的和睦，对于批评和紧张特别敏感。",
                        "您容易看出他人的发展潜力，并倾力帮助他人发挥潜力，是体贴的助人为乐者。您愿意组织大家参与活动，使大家和睦又感到愉快。 ",
                        "您是理想主义者，看重自己的价值，对自己尊重敬仰的人、事业和公司都表现出一定的忠诚度。",
                        "您有责任感、谨慎、坚持不懈，同时对新观点很好奇。若能为人类的利益有所贡献，您会感到深受鼓舞。",
                        "您对现实以外的可能性，以及对他人的影响感兴趣，较容易发现别人看不到的意义和联系，并感到自己与万物息息相关，可以井然有序地安排生活和工作。",
                    ],
                    "blindness": [
                        "您较容易理想化，认为世界应是自己想象中的那样，不愿意接受与此相抵触的事情，较容易忽略理想所需要的现实和细节问题。",
                        "您依照情感行事，较少用逻辑，主要根据个人的价值观进行判断，有时容易无视行为所带来的后果，过度陷入别人的情感和问题中。",
                        "您追求避免冲突，有时会不够诚实和公平。试着更多地去关注事情，而不只是人，会更有助于您做出合理的决定。",
                        "您有很高的热情，急于迎接新的挑战，有时会做出错误的假设或过于草率的决定。建议您对计划中的细节多加注意，等获取足够多的信息之后再做决策。",
                        "您总想得到表扬，希望自己的才能和贡献得到赏识，您对于批评脆弱，容易忧虑，感到内疚，失去自信。当压力很大时，会变得烦躁、慌乱、吹毛求疵。",
                    ]
                },
                "ENFP": {
                    "content": "公关型",
                    "description": [
                        "您对周围的人和事物观察得相当透彻，能够洞察现在和将来。随时可以发现事物的深层含义和意义，并能看到他人看不到的事物内在的抽象联系。",
                        "您崇尚和谐善意、情感多样、热情、友好、体贴、情绪强烈，需要他人的肯定，也乐于称赞和帮助他人。您总是避免矛盾，更在意维护人际关系。",
                        "您富有活力，待人宽厚，有同情心，有风度，喜欢让人高兴。只要可能，您就会使自己适应他人的需要和期望。",
                        "您倾向于运用情感作出判断，决策时通常考虑他人的感受。您在意维护人际关系，愿意花费很多心思，结交各种各样的人，而不是做事。",
                        "您有丰富的想象力，善于创新，自信，富有灵感和新思想，警觉，善于寻找新方法，更注重理解，而不是判断。",
                        "您喜欢提出计划，并大力将其付储实施。您特别善于替别人发现机会，并有能力且愿意帮助他们采取行动抓住机会。",
                    ],
                    "blindness": [
                        "您较为理想化，容易忽视现实和事物的逻辑，只要感兴趣，什么都去做。",
                        "您通常在事情开始阶段或有变化的阶段较为投入，而对后续较为常规或沉闷的部分，难以持续投入。",
                        "您总是能轻易地想出很多新注意，喜欢着手许多事情，无法专注于一件事情，很少能把事情“从头做到尾”。",
                        "您总能看到太多的可能性，因此无法确定哪些事情是自己真正追求的。建议您认真选择一个目标，善始善终，以免浪费时间和挥霍自己的天赋。",
                        "您组织纪律性比较弱，不肯服从，无视限制和程序。您喜欢即兴发挥，不愿意筹备和计划，对细节没有兴趣。如果您要有所作为，应尽量使自己的新思路现实、可操作。与更注重实际的人一起工作会对您很有帮助，这也符合您的特点，因为您不喜欢独自工作。",
                    ]
                },
                "ENTJ": {
                    "content": "领导者型",
                    "description": [
                        "您直率、果断，能够妥善解决组织的问题，是天生的领导者和组织的创建者。",
                        "您擅长发现一切事物的可能性并愿意指导他人实现梦想，是思想家和长远规划者。",
                        "您逻辑性强，善于分析，能很快地在头脑里形成概念和理论，并能把可能性变成计划。树立自己的标准并一定要将这些标准强加于他人。",
                        "您看重智力和能力，讨厌低效率，如果形势需要，可以非常强硬。",
                        "您习惯用批判的眼光看待事物，随时可以发现不合逻辑和效率低的程序并强烈渴望修正它们。",
                        "您善于系统、全局地分析和解决各种错综复杂的问题，为了达到目的，您会采取积极行动，您喜欢研究复杂的理论问题，通过分析事情的各种可能性，事先考虑周到，预见问题，制定全盘计划和制度并安排好人和物的来源，推动变革和创新。",
                        "您愿意接受挑战，并希望其他人能够像自己一样投入，对常规活动不感兴趣。长于需要论据和机智的谈吐的事情，如公开演讲之类。",
                    ],
                    "blindness": [
                        "您较容易在没有了解细节和形势之前就草率地做决定。",
                        "您容易很客观、带有批判性地对待生活，容易对别人的情况和需要表现得较粗心、直率、无耐心。建议您注意倾听周围人的心声，并对别人的贡献表示赞赏。您需要学会在实施自己的计划之前听取别人的建议，以免独断专横。",
                        "您考虑问题非常理智，很少受无关因素影响。您没有时间和兴趣去体会情感，容易忽略他人的感受，显得不尽人情。但当您的感情被忽视或没有表达出来的时候，您会非常敏感。您需要给自己一点儿时间来了解自己的真实感情，学会正确地释放自己的情感，而不是爆发，并获得自己期望和为之努力的地位。",
                        "您容易夸大自己的经验、能力。您需要接受他人实际而有价值的协助，才能更好地提高能力并获得成功。"
                    ]
                },
                "ENTP": {
                    "content": "智多星型",
                    "description": [
                        "您喜欢挑战让您兴奋的事情，聪慧，许多事情都比较拿手，致力于自己才干和能力的增长。",
                        "您有较强的创造性和主动性，绝大多数是事业型的。您好奇心强，喜欢新鲜事物，关注事物的意义和发展的可能性。通常把灵感看得比什么都重要，多才多艺，适应性强且知识渊博，很善于处理挑战性的问题。",
                        "您能快速抓住事物的本质，喜欢从新的角度和独到的方式思考问题，对问题经常有自己独到的见解。",
                        "您机警而坦率，有杰出的分析能力，并且是优秀的策略家。",
                        "您不喜欢条条框框的限制和因循守旧的工作方式，习惯便捷的问题解决方法。",
                        "您喜欢自由的生活并善于发现其中的乐趣和变化。",
                        "您认为“计划赶不上变化”，并以实际行动证明大部分规定和规律都是有弹性，可伸缩的，通常会超出被认可和期望的限度。",
                        "您乐观，善于鼓舞他人，能用自己的热情感染他人。",
                    ],
                    "blindness": [
                        "您充满热情地寻找新鲜事物，但行事缺少稳定的计划和流程，经常依靠临场发挥，可能因为忽视必要的准备工作，而草率地身陷其中。",
                        "您的注意力容易游移，对目标的韧性和坚持性不够，缺乏足够的耐心，有时不能贯彻始终。一旦主要问题被解决了，就会转移到下一个目标，而不能坚持将一件事完完整整地结束。",
                        "您非常注重创造力和革新，容易忽略简单、常规的方法和一些重要的细节，不愿遵守规则和计划。建议多关注解决问题的常规方法。",
                        "您通常同时展开多项任务与活动，不愿丢掉任何一种可能性，致力于寻找新的变化，可能使别人的计划和时间安排受到影响。您要好好考虑一下自己的行动给他人带来的影响，这有助于您变得更可靠。",
                        "您有天生的直觉和预知能力，会使您误认为知道了别人的想法。建议您认真倾听他人，避免表现得不耐烦。",
                    ]
                },
                "ESFJ": {
                    "content": "主人型",
                    "description": [
                        "您非常重视与别人的关系，易觉察出他人的需要，并善于给他人实际关怀，待人友好、善解人意并有很强的责任心。看到周围的人舒适和快乐，也会感到快乐和满足，很健谈，因此非常受欢迎。",
                        "您热情，有活力，乐于合作，有同情心，机敏圆滑，希望得到别人的赞同和鼓励，冷淡和不友善会伤害您。",
                        "您需要和睦的人际关系，对于批评和漠视非常敏感，竞争和冲突会让您感觉到不愉快，因此尽力避免发生这样的事情。",
                        "您很实际、有条理，做事彻底，有一致性，对细节和事实有出色的记忆力，并且希望别人也如此。",
                        "您着眼于目前，在经验和事实之上做出决策，将事情安排妥当，喜欢自己成为活跃而有用的人物。",
                        "您能很好地适应日常的常规工作和活动，不喜欢做需要掌握抽象观点或客观分析的工作。喜爱自己的全部，对自己爱护有加。",
                        "您喜欢组织众人和控制形势，与他人合力圆满又按时地完成任务。喜欢安全和稳定的环境，支持现存制度，注重并很好地遵守社会约定规范。",
                        "您忠于自己的职责，并愿意超出自己的责任范围而做一些对别人有帮助或有益处的事情，在遇到困难和取得成功时，都很积极活跃，希望付出能得到回报或赞扬。",
                    ],
                    "blindness": [
                        "您过分在意别人的情感和想法，以至于总是给予别人额外的关心和帮助，有时态度强硬，容易侵占别人的空间，您需要考虑一下自己提供的帮助是不是他人的需要。当遇到冲突时，为了保护和睦的人际关系，通常采取回避或是妥协的方式，而非积极的、正面的处理。",
                        "您的敏感，做事总是希望得到别人的鼓励和赞赏，担心被忽视，不愿接受批评，很可能变得沮丧和郁闷。",
                        "您总是容易陷入情感和细节中，很难从问题中跳出来更宏观、更客观的对待；取悦或帮助他人的您很忽视自己的需求，难以说出“不”，怕让别人失望。",
                        "您通常很难变通，拒绝尝试新方法，习惯根据经验做出决定，以至于信息不足造成决策的草率。建议尽量开放地接受外部变化，放慢决定的速度。",
                    ]
                },
                "ESFP": {
                    "content": "表演者型",
                    "description": [
                        "您更多地从做事的过程中学到东西，而不是研究或读书。您相信自己五感所感触到的信息，喜欢有形的东西，能够看到并接受事物的本来面目，是现实的观察者，并具有运用常识处理问题的实际能力。",
                        "您对人和新的经历都感兴趣，善于观察，看重眼前事物。",
                        "您更多地从做事的过程中学到东西，而不是研究或读书。您相信自己五感所感触到的信息，喜欢有形的东西，能够看到并接受事物的本来面目，是现实的观察者，并具有运用常识处理问题的实际能力。",
                        "您热爱生活，适应性强且随遇而安，爱热闹，爱玩耍，热情、友好，表现欲强烈，有魅力和说服力。",
                        "您喜欢意料之外的事情并给他人带来快乐和惊喜；您的饱满情绪和热情能够吸引了别人，灵活、随和，很好相处。通常很少事先做什么计划，自信能够遇事随机应变，当机立断。讨厌框框，讨厌老一套，总能设法避开这些东西。",
                        "您善于处理人际关系，经常扮演和事老的角色，圆滑得体，富有同情心，愿意以实际的方式帮助他人，通常可以让别人接受自己的建议，不喜欢将自己的意愿强加别人，是非常好的交谈者，天生受人欢迎。",
                    ],
                    "blindness": [
                        "您对各种事情都好奇，以致于总是分心，工作受到干扰。做事容易拖拉，难以约束自己，显得不是那么尽职尽责。建议集中注意力，平衡工作和生活，努力把工作放在首位，借鉴一些成功的或已为人所接受的安排工作和控制时间的方法。",
                        "因为您积极活跃的个性，总是使您忙碌于具体的事务中，并无暇去制订计划，致使面临应急和变化时您会不知所措，您应该未雨绸缪，学会计划和预测事物的发展变化。",
                        "您经常忽视理论思考和逻辑分析，做决定时习惯于相信自己的感觉，或凭一时兴趣、冲动，有时不考虑结果。您对朋友的评价很高，并只看到他们积极的一面。您需要更进一步考虑事情的起因和结果，并学会拒绝。",
                    ]
                },
                "ESTJ": {
                    "content": "管家型",
                    "description": [
                        "您做事速度快，讲求效率，有责任感，善于自我约束，能够尽职尽责地完成工作。",
                        "您喜欢推进事情并掌控局势，敏锐，对细节有出色的记忆力，善于组织，能够系统化、结构化地通过有效的方式安排时间并达成目标。",
                        "您有计划、有条理、喜欢把事情安排的井井有条，按照计划和步骤行事。",
                        "您是一个有极强的逻辑性、非常喜欢做决定的人。您做事客观、善于分析，而且有很强的推理能力。通常根据自己的经验进行判断和决策，善于看到工作系统中不合逻辑，不协调和无效的部分，并做出积极改进。",
                        "您习惯从细节出发，关注现实，重视经验和感受。您关注实用价值，对于听到、看到、闻到、尝到、触摸到的“具体事物”更加感兴趣，而不是一些抽象的理念。您关注眼前，一般对于事情的远景和潜在价值难以关注到。",
                        "您性格外向，为人友好、直爽，处事讲求原则。通常是坚定的、可以信赖的伙伴。您喜欢传统，遵照规范办事，是原则和传统的良好维护者，您擅长判断人，严于律已，在人际关系上始终如一。",
                    ],
                    "blindness": [
                        "您看问题具有很强的批判性，注意力更多关注存在的问题，通常不能对别人的贡献表示赞赏和肯定。您需要留意和发现别人的才能和努力，并适时给予鼓励和表扬。当提出批评时，多注意技巧。",
                        "您喜欢把自己的标准强加给别人，对自己和他人都要求严格，通常被周围的人看成“独裁者”。您需要学会更加通融、开放，不要过于固执。建议以更加开放的观念和发展的眼光，看待周围的新事物，对不同的人，不同的事更有耐心和包容性。",
                        "您遵照逻辑和客观的原则做事，较少考虑自己的行为和决定给他人带来的影响。建议您更加留心和尊重自己及他人的情绪和感受。",
                        "您专注于实施自己细致的计划，容易错过外界的很多变化和信息，甚至难以停下来听一听别人的意见，您忽视了许多发展的可能性及事物潜在的关联关系。您需要学会放慢节奏，倾听别人的建议，考虑所有的可能性，更好地检查其它可以利用的资源，增加做事的周全性。",
                        "如果您希望更好地适应社会，并获取成功，您需要尝试多角度地理解和处理问题，加强灵活性，不要事事控制，尝试转换思维方式，并且懂得和接受生活中有介于黑与白之间的灰色区域。",
                    ]
                },
                "ESTP": {
                    "content": "企业家型",
                    "description": [
                        "您是敏锐的发现者，善于看出眼前的需要，并迅速做出反应来满足这种需要，天生爱揽事并寻求满意的解决办法。您精力充沛，积极解决问题，很少被规则或标准程式框住。能够想出容易的办法去解决难办的事情，以此使自己的工作变得愉快。",
                        "您天生的乐天派，积极活跃，随遇而安，乐于享受今天。对提供新经验的任何事物、活动、食物、服饰、人等都感兴趣，只愿享受今天，享受现在。",
                        "您好奇心强，思路开扩，容易接受事物，倾向于通过逻辑分析和推理做出决定，不会感情用事。如果形势需要，您会表现出坚韧的意志力。偏爱灵活地处理实际情况，而不是根据计划办事。",
                        "您长于行动，而非言语，喜欢处理各种事情，喜欢探求新方法。您具有创造性和适应性，有发明的才智和谋略，能够有效地缓解紧张氛，并使矛盾双方重归于好。",
                        "您性格外向，友好而迷人，很受欢迎，并且能在大多数社会情况中很放松自如。",
                    ],
                    "blindness": [
                        "由于您关注外界各种变化信息，喜欢处理紧急情况，不愿意制订规划去预防紧急情况的发生。常常一次着手许多事情，超出自己的负荷，不能履行诺言，可能使周围的人陷入混乱。您需要试着找到一些能让自己按时完成任务的方法。",
                        "您的注意力完全集中在有趣的活动上，喜欢不断地接受新的挑战，不愿意在目前沉闷的工作中消磨时间，难以估计自己行为带来的结果。您需要为自己订立一个行为标准。",
                        "当情况环境转变时，您很容易忽视他人的情感，变得迟钝和鲁莽。",
                    ]
                },
                "INFJ": {
                    "content": "博爱型",
                    "description": [
                        "您有计划、有条理，喜欢遵照固有的模式处理问题，乐于探求独特的方式以获得有意义的成长和发展。",
                        "您通过认同和赞扬与别人进行沟通，具有很强的说服力，您可以成为伟大的领导者。您的贡献被人尊敬和推崇。",
                        "您喜欢独处，性格复杂，有深度，是独立的思考者。您忠诚、有责任心，喜欢解决问题，通常在认真思考之后行动。您在同一时间内只专注一件事情。",
                        "您有敏锐的洞察力，相信灵感，努力寻求生活的意义和事件的内在联系。",
                        "您有坚定的原则，就算被别人怀疑，也相信自己的想法和决定，依靠坚韧不拔取得成功。",
                        "他人能随时体会到您的善良和体贴，但不太了解您，因为您总是做的含蓄和复杂。事实上您是非常重感情，忠于自我价值观，有强烈的愿望为大家做贡献，有时候您也很紧张和敏感，但表现的深藏不露；您倾向于拥有小范围的而深长久远的友谊。",
                    ],
                    "blindness": [
                        "您的完美和固执，使您易走极端。一旦决定后，拒绝改变，并抵制那些与您的价值相冲突的想法，以至于变的没有远见。",
                        "您专注的追求一个理想，不会听取别人的客观意见，因为自己的地位是不容置疑的。",
                        "您总是探寻事情的意义和价值，过于专注各种想法，会显得不切实际，而且经常会忽视一些常规的细节。",
                        "您需要留意周围的情况，并学会运用已被证实的信息，这样可以帮助您更好地在现实世界中发挥您的创造性思维。",
                        "您敏感，非常关注个人的感受和他人的反应，对任何批评都很介意，甚至会视为人身攻击。对您来讲，您需要客观地认识自己和周围的人际关系，更好地促进事情向正面转化。",
                    ]
                },
                "INFP": {
                    "content": "哲学家型",
                    "description": [
                        "您比较敏感，非常崇尚内心的平和，看重个人的价值，忠诚，并且理想化，一旦做出选择，就会约束自己完成。",
                        "您外表看起来沉默而冷静，但内心对他人的情感十分在意。您非常善良，有同情心，善解人意。",
                        "您重视与他人有深度、真实、共同进步的关系，希望参与有助于自己及他人的进步和内在发展的工作，欣赏那些能够理解您价值的人。",
                        "您有独创性、有个性，好奇心强，思路开阔，有容忍力。乐于探索事物的可能性，致力于自己的梦想和远见。",
                        "您很喜欢探索自己和他人的个性。一旦全身心地投入一项工作时，您往往发挥出冲刺式的干劲，全神贯注，全力以赴。您对人、事和思想信仰负责，一般能够忠实履行自己的义务。但是，对于意义不大的日常工作，您做起来可能有些困难。",
                    ],
                    "blindness": [
                        "您追求完美，会花很长时间酝酿自己的想法，难以用适当的方式来表达自己。您需要更加注重行动。",
                        "您经常忽略逻辑思考和具体现实，沉浸于梦想。当意识到自己的理想与现实之间的差距，您就容易灰心丧气。您需要听取他人更实际的建议，考虑方法的现实性和可行性。",
                        "您非常固执，经常局限在自己的想法里，对外界的客观具体事物没有兴趣，甚至忙的不知道周围发生了什么事情。",
                        "您总是用高标准来要求自己，投入太多的感情，导致您对批评相当敏感。压力很大的时候，您可能会非常怀疑自己或他人的能力，而变得吹毛求疵，又爱瞎判断，对一切都有抵触情绪。",
                    ]
                },
                "INTJ": {
                    "content": "专家型",
                    "description": [
                        "您考虑问题理智、清晰、简洁，不受他人影响，客观地批判一切，运用高度理性的思维做出判断，不以情感为依据。用批判的眼光审视一切，如果形势需要，会非常坚强和果断。",
                        "您不屈从于权威，并且很聪明，有判断力，对自己要求严格，近乎完美，甚至也这样去要求别人，尤其讨厌那些不知所措、混乱和低效率的人。",
                        "您有很强的自制力，以自己的方式做事，不会被别人的冷遇和批评干扰，是所有性格中最独立的。",
                        "您是优秀的策略家和富有远见的规划者，高度重视知识，能够很快将获取的信息进行系统整合，把情况的有利与不利方面看的很清楚。",
                        "您具有独特的、创造性的观点，喜欢来自多方面的挑战。在您感兴趣的领域里，会投入令人难以置信的精力、专心和动力。",
                    ],
                    "blindness": [
                        "您只注重自己，很少去理解他人，自以为是，对他人没有耐心，总是想当然地把自己的观点强加给别人，制定不切实际的高标准。您需要学会去了解别人的感受和想法，以避免您冒犯他人。",
                        "您过于注重远见卓识，很容易忽略和错过与自己理论模式不符的细节和现象。您爱玩弄智力游戏，说些对他人没有意义、似是而非的话语。您需要简化您既理论又复杂的想法，更好的与别人交流。",
                        "您过分独立的个性和工作习惯，使得您总是“拒绝”别人的参与和帮助，难以发现自己计划中的缺陷。建议您保持耐心，多向他人请教，这样可以帮助您提早了解一些不合实际的想法，或者在大量投入之前做出必要的修正和改进。",
                        "您有时会过于固执和死板，沉迷于一些出色的但不重要的想法中，并且事事要求完美；如果您想成功，您需要判断事情的重要性，学习接受生活并与他相处，学会放弃。",
                    ]
                },
                "INTP": {
                    "content": "学者型",
                    "description": [
                        "您极其聪慧，有逻辑性，善于处理概念性的问题，且有很强的创造灵感，对发现可能性更感兴趣。",
                        "您非常独立，有批判性和怀疑精神，深藏不露，内心通常在投入地思考问题，总是试图找运用理论分析各种问题；对一个观点或形势能做出超乎超于常人的、独立准确的分析，会提出尖锐的问题，也会向自己挑战以发现新的合乎逻辑的方法。",
                        "您擅长用极端复杂的方式思考问题，看重自己的才学，也喜欢向别人挑战；您更善于处理概念和想法，而不是与人打交道。喜欢有逻辑性的和目的性的交谈，但有时想法过于复杂以至于难与别人交流和让别人理解，也会只是为了高兴而就一点儿小事儿争论不休。",
                        "您能宽容很多不同的行为，只是在自己认为应该的时候才争论和提出问题，但是如果您的基本原则受到挑战，您就不在保持灵活性而以原则办事。",
                        "您是天才而有创意的思考者，喜欢投机和富于想像力的活动，对找到创造性解决问题的办法更感兴趣，而不是看到这些办法真正奏。",
                    ],
                    "blindness": [
                        "如果您没有机会运用自己的才能，或得不到赏识，会感到沮丧，爱打嘴仗，好争论，冷嘲热讽，消极的批判一切。",
                        "您过于注重逻辑分析，只要不合逻辑，就算对您再重要，也很有可能放弃它。",
                        "您过分理智，忽视情感和现实，察觉不到他人的需要，也不考虑自己的观点对他人的影响，以“不符合”逻辑为由，主观断定某些自己或他人看重的东西的是不重要的，不够实际。",
                        "当您把自己批判的思维用在人的身上时，您的直率会变成无心的伤害。您需要找到自己真正在乎的事，这将帮助您们更真实地对待自己的情感。",
                        "您对解决问题非常着迷，极善于发现想法中的缺陷，却很难把它们表达出来，您对常规的细节没有耐心，如果事情需要太多的琐碎细节，您会失去兴趣，也会因计划中很小的缺陷而陷入困境，您绝不容忍任何一点不合逻辑。",
                    ]
                },
                "ISFJ": {
                    "content": "照顾者型",
                    "description": [
                        "您具有友善、负责、认真、忠于职守的特点，只要您认为应该做的事，不管有多少麻烦都要去做，但却厌烦去做您认为毫无意义的事情。",
                        "您务实、实事求是，追求具体和明确的事情，喜欢做实际的考虑。善于单独思考、收集和考察丰富的外在信息。不喜欢逻辑的思考和理论的应用，拥有对细节很强的记忆力，诸如声音的音色或面部表情。",
                        "您与人交往时较为敏感，谦逊而少言、善良、有同情心，喜欢关心他人并提供实际的帮助，您们对朋友忠实友好，有奉献精神。虽然在很多情况下您有很强烈的反应，但通常不愿意将个人情感表现出来。",
                        "您做事有很强的原则性，尊重约定，维护传统。工作时严谨而有条理，愿意承担责任，您依据明晰的评估和收集的信息来做决定，充分发挥自己客观的判断和敏锐的洞察力。",
                    ],
                    "blindness": [
                        "您有高度的责任心，会陷入日常事务的细节中去，以至于没完没了的工作。每件事情您都会从头做到尾，这总是让您过度劳累，压力很大时，您会过度紧张，甚至产生消极情绪。",
                        "由于您的现实、细致，有时容易忽略事情的全局和发展变化趋势，难以预见存在的可能性。建议您周到考虑解决问题的不同方法和可能性，需要增强对远景的关注。",
                        "您总是替别人着想，以至于让人感觉“关心过度”，您需要学会给别人空间。在工作中，您过多的承受和忍耐，不太习惯表达，却将情绪在家庭和生活中发泄出来。",
                        "您不停地制订计划并保证完成，以致于经常花费更多的时间和投入更多的精力来完成工作，建议您给自己安排必要的娱乐和放松的活动，不要总是“低头拉车”，需要考虑“抬头看路”。",
                    ]
                },
                "ISFP": {
                    "content": "艺术家型",
                    "description": [
                        "您和蔼、友善、敏感，谦虚地看待自己的能力。您能平静愉悦地享受目前的生活，喜欢体验。珍视自由自在地安排自己的活动，有自己的空间，支配自己的时间。",
                        "您善于观察、务实、讲求实际，了解现实和周围的人，并且能够灵活地对他们的情况和需要做出反应，但很少寻求其动机和含义。",
                        "您是优秀的短期规划者，能够全身心地投到此时此刻的工作中，喜欢享受现今的经验而不是迅速冲往下一个挑战。",
                        "您有耐心，易通融，很好相处。您没有领导别人的愿望，往往是忠实的跟随者和很好的合作伙伴。",
                        "您很客观，而且能以一种实事求是的态度接受他人的行为，但您需要基本的信任和理解，需要和睦的人际关系，而且对矛盾和异议很敏感。",
                        "您很有艺术天份，对自然的美丽情有独钟，对直接从经验中和感觉中得到的信息非常感兴趣，喜欢为自己创造一种幽雅而个性化的环境，您希望为社会的福利和人类的幸福做些贡献。您内心深沉，其实很热情，不太喜欢表现。",
                    ],
                    "blindness": [
                        "您完全着眼于现在，从不喜欢寻找和发现那些您认为不存在的可能性，这使您无法发现更广阔的前景，也不能为将来做打算，不能很好地安排时间和精力。",
                        "您天生对他人具有高度的敏感，总是难以拒绝别人，有时为了满足他人的需求而拼命地工作，以至于在此过程中忽视了自己。",
                        "您过分忽视事物之间的内在联系和逻辑思考，难以理解复杂的事情。",
                        "您对他人的批评会感到生气或气馁，有时容易过分自责。您容易相信别人，很少对别人的动机有所怀疑，也不会发现别人行为背后的隐含意义。您们需要更注重自己的需求，而且要对别人的行为加以分析。在分析中加入一些客观和怀疑的态度会让您们更准确地判断人的性格。",
                    ]
                },
                "ISTJ": {
                    "content": "检查员型",
                    "description": [
                        "您是一个认真而严谨的人，勤奋而负有责任感，认准的事情很少会改变或气馁，做事深思熟虑，信守承诺并值得信赖。",
                        "您依靠理智的思考来做决定，总是采取客观、合乎逻辑的步骤，不会感情用事，甚至在遇到危机时都能够表现得平静。",
                        "您谨慎而传统，重视稳定性、合理性；您天生独立，需要把大量的精力倾注到工作中，并希望其它人也是如此，善于聆听并喜欢将事情清晰而条理的安排好。",
                        "您喜欢先充分收集各种信息，然后根据信息去综合考虑实际的解决方法，而不是运用理论去解决。",
                        "您对细节非常敏感，有很实际的判断力，决定时能够运用精确的证据和过去的经验来支持自己的观点，并且非常系统有条不紊，对那些不这样做的人没有耐心。",
                    ],
                    "blindness": [
                        "您非常固执，一旦决定的事情，会对其他的观点置之不理，并经常沉浸于具体的细节和日常的操作中。",
                        "您看问题有很强的批判性，通常持怀疑态度，您需要时常的换位思考，更广泛的收集信息，并理智的评估自己的行为带来的可能后果。",
                        "您非常独立，我行我素，不能理解不合逻辑的事情，忽视他人的情感，并对与您风格不同的人不能理解，非常挑剔；您要学会欣赏他人的优点并及时表达出来。",
                        "您非常有主见，时常会将自己的观点和标准强加给别人，而且无视那些不自信的人的建议。在处理问题时，强求别人按照自己的想法来做，对于未经检验或非常规的方法不加考虑。若能在以后多尝试和接受新颖的、有创造性的方法，您就能做出更有效的决策。",
                    ]
                },
                "ISTP": {
                    "content": "冒险家型",
                    "description": [
                        "您密切关注周围发生的事情，常常充当解决困难的人。一旦需要，会快速反应，抓住问题的核心以最有实效的方式予以解决。您好奇心强，对事实敏感，能很好的利用手头的资源。",
                        "您善于思考和分析，关注事情是什么，及可以解决什么具体问题，不关注理论。您喜欢客观独立地作决定，并把一切都清楚直接地安排妥当。您对技术工作很有天赋，是使用工具和双手工作的专家。",
                        "您非常独立，不愿受规则约束，以独有的好奇心和富有创意的幽默观察和分析生活。具备很好的迎接挑战和处理问题的能力，天性喜欢兴奋和行动，通常很喜欢户外活动和运动。",
                        "您通常是安静或沉默的，喜欢行动而非言语，看上去比较“酷”，时常被认为不太愿意接近人。",
                    ],
                    "blindness": [
                        "您非常实际，总能找到简捷的解决办法，这使您有时会偷工减料，不能完成所有的步骤和细节。您过分的关注眼下的结果，以至忽略了自己的决策和行动的长远影响。建议您学会做计划并坚持完成，以克服自己主动性弱的特点。",
                        "您总是独立分析，独自判断，不喜欢与别人分享自己的反应、情感和担忧，也不愿意把具体的情况甚至是最重要的部分与他人进行交流，使得周围的人行动或配合起来比较被动。",
                        "您非常喜欢多样化和新奇刺激，对所有的选择都持开放态度，所以您不善于做决定。您需要认真给自己一些约束，避免总是变动和无规律所带来的危害。",
                        "您通常无视自己的情感和需要，忽视他的人感受，对于自己的决定对他人产生的影响不够重视。",
                    ]
                },
            }

            character_result = character.get(characteristics, None)
            character[characteristics]["characteristics"] = characteristics
            default_data["msg"]["style"] = character_result
            default_data["msg"]["score"] = ret_score
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    #  职业定向算法 获取值
    def get_zydx_value(self, personal_result_id):
        u"""职业定向算法"""
        default_data = {
            "report_type": "职业定向模板",
            "msg": {
                "Name": "666",
                "Sex": "男",
                "Age": "25",
                "TestTime": "2018.10.12",
                # name  指标名称，score: 分值  按照下面顺序展示
                "chart": [
                    {"name": u"技术/职能型", "score": 30},
                    {"name": u"管理型", "score": 28},
                    {"name": u"自主/独立型", "score": 26},
                    {"name": u"安全/稳定型", "score": 24},
                    {"name": u"创造/创业型", "score": 18},
                    {"name": u"服务/奉献型", "score": 17},
                    {"name": u"挑战型", "score": 16},
                    {"name": u"生活型", "score": 10},
                      ],
            }
        }
        try:
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            time.sleep(2)
            # if not people_result.dimension_score or not people_result.substandard_score:
                # SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
            SurveyAlgorithm.algorithm_zydx(personal_result_id, form_type=Survey.FORM_TYPE_NORMAL)
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", u"未知")
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            dimension_score_map = people_result.dimension_score_map
            for info in default_data["msg"]["chart"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][:1] == info["name"][:1]:
                        info["score"] = dimension_score_map[dimension_id]["score"]
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def get_peoi_value(self, personal_result_id):
        u"""get personal EOI info for report"""

        SCORE_MAP = [2.28, 6.69, 15.86, 30.85, 50.5, 69.15, 84.13, 93.31, 97.72, 100]
        POSITIVE_COMMENTS = {'自主定向': '指南针/独立自主/超有主见/我就是我/霸总上身',
                             '意义寻求': '明灯/勇往直前/我都是有道理的/凭一句为什么荣登杀手榜',
                             '自我悦纳': '直面自己/以身作则/像我这样优秀的人',
                             '自我拓展': '潜力股/博学家/好奇宝宝',
                             '情绪调节': '神经大条/化悲愤为食欲、化干戈为玉帛',
                             '专注投入': '心无旁鹜/爷（老娘）在工作，生人勿扰！',
                             '亲和利他': '活雷锋/舍己为人',
                             '包容差异': '老好人/博爱/是个人就是咱兄弟姐妹',
                             '乐观积极': '精神胜利法/在坐的各位都是“勒色”',
                             '自信坚韧': '中流砥柱/金刚狼',
                             '合理归因': '战略家/帅才之能/把老婆说的对通用于职场',
                             '灵活变通': '条条大路通罗马/结果一样就好，何必操心过程？'}
        NEGATIVE_COMMENTS = {'自主定向': '方向痴/随波逐流/选择困难症/你是光，你是电，你是唯一的神话，所以你决定就好！',
                             '意义寻求': '迷茫/求大佬带带我/敢问路在何方？路不在脚下啊',
                             '自我悦纳': '信心不足/柔柔弱弱/专业潜水员/发言现场如刑场',
                             '自我拓展': '我老了，学不动了/懒癌末期/故其疾如风,其徐如林,侵掠如火，我自不动如山！',
                             '情绪调节': '敏感忧郁/此恨绵绵无绝期/崩溃是一种生活态度',
                             '专注投入': '想一出是一出/我真的真的工作很忙啊！要不咱们还是聊会？',
                             '亲和利他': '各人自扫门前雪，休管他人瓦上霜/Who are you ?',
                             '包容差异': '物以类聚,人以群分/你长的不像我，我们没啥好说的！',
                             '乐观积极': '林妹妹/世界末日要到了！',
                             '自信坚韧': '鸵鸟/help ! I hurt my little finger！',
                             '合理归因': '追牛角尖/一言不合就砸锅/霸气已开我就是道理！',
                             '灵活变通': '老顽固/雷打不动/方法何其多，选则永不变！'}
        NOPOSITIVECOMMENT = '优点？我没有！'
        NONEGATIVECOMMENT = '无敌，我是全能哒！'

        SUGGESTION = {'自主定向': '当你觉得生活迷茫无所适从的时候，可以选择给自己树立短期可达成的小目标，让自己一点一滴充实起来，比如每月读一本书。/学会为自己的生活和职场树立目标，你才不会觉得迷茫哦~',
                      '意义寻求': '每一次树立目标之后，是否就是无限期的拖延？把每一个目标一笔一划写在纸上，贴在自己随处可见的地方，完成一项目标就划掉一项。/将目标完成的步骤可视化，可以提高工作效率呢~',
                      '自我悦纳':  '是否别人夸奖自己每每觉得心虚？早上起来，整理好仪容，带着自信的微笑，认真告诉镜子里的自己，“你是最棒的！”/承认自己的优秀，是不错的体验呢~',
                      '自我拓展':  '对于从未接触到的工作你是否会觉得害怕？每当害怕的时候想一想新任务能给你带来什么？新的朋友？有趣的过程？丰厚的回报？/跨出你的舒适区，是成长的第一步也是关键一步！',
                      '情绪调节':  '站在人群中间的时候常常觉得手足无措吗？回想自己过去取得的成就，在内心暗自激励自己，“没有什么是我完不成的！”/学会在压力下调节情绪，你便是职场精英！',
                      '专注投入':  '工作中常常被周围环境所打扰？将容易引起兴趣的手机等物品在工作前收好，第一天间隔15分钟休息，第二天20分钟休息，以此类推，提高工作专注度。/专注工作，其实也没有这么难~',
                      '亲和利他':  '是否在不知不觉中忽视了他人想法？在完成一份工作计划的时候，先代入他人的角色，考虑别人的利益，他们会提出怎样的问题？做出怎样的抉择？/职场交际达人，都会的利他的技能~',
                      '包容差异':  '职场中被吐槽过为人严肃？办公桌上放上一盆绿植，保持良好的心情，时常微笑待人，带着包容的心态接触不同性格的人，你就会发现每种性格的人都有着不同的趣味！/包容差异，其实也是在包容自己~',
                      '乐观积极':  '你是否常常陷入消极悲观？试图让自己的生活充实丰富起来，去完成一些能让自己在短时间内能获得成就感的事情，为内心注入正能量。/世界很美好，你也很美好~',
                      '自信坚韧':  '遇到挫折你需要很长的恢复期？勇敢面对挫折，静下心、思考下将感到挫败感的原因一条条总结下，你会发现没什么大不了的。制定切实可行的改变计划，不要犹豫，勇敢投入其中，下次一定会做的更好。/勇敢的朋友，相信挫折只是你脚下的小石子。',
                      '合理归因':  '看待问题常受到思维的局限？尝试和朋友以及同事就一个话题无所拘束得聊天，将每个人的想法记录下来，发现自己思维的局限和不足。/头脑风暴之余，灵感悄然而至。',
                      '灵活变通':  '你是否害怕改变现状，不愿去尝试未知事物？从一件小事尝试以前从未使用过的方法，迈出第一步，培养自己。你将会尝到甜头。/不试试怎么会知道路只有一条呢？'}

        data = {"report_type": "幸福能力", "msg":
                    {
                    "name": "",
                    "image": "",
                    "total": "90",
                    "title": "",
                    "comment1": "",
                    "comment2": [],
                    "comment3": [],
                    "ChartEudaemonia":
                        [
                            {"name": "乐观积极", "score": 6},
                            {"name": "自信坚韧", "score": 8},
                            {"name": "合理归因", "score": 7},
                            {"name": "情绪调节", "score": 9},
                            {"name": "意义寻求", "score": 5},
                            {"name": "自主定向", "score": 7},
                            {"name": "专注投入", "score": 4},
                            {"name": "自我拓展", "score": 3},
                            {"name": "灵活变通", "score": 2},
                            {"name": "包容差异", "score": 9},
                            {"name": "亲和利他", "score": 7},
                            {"name": "自我悦纳", "score": 6},
                        ]
                    } 
               }

        average_value = 69.898
        standard_diff_value = 18.912
        positive_comments = []
        negative_comments = []
        negative_quotas = []

        try:
            #get personal assess status info
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)

            #exit when not completed
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return data, ErrorCode.INVALID_INPUT

            #calculate peoi when calculation not ready
            if not people_result.dimension_score or not people_result.substandard_score:
                SurveyAlgorithm.algorithm_xfzs(personal_result_id)
                people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            
            #initialize score map
            dimension_score_map = people_result.dimension_score_map
            substandard_score_map = people_result.substandard_score_map
            people = People.objects.get(id=people_result.people_id)
            total_score = 100
            normsdist_score = 100
            comment = []
            
            data["msg"]["name"] = people.display_name
            sex = people.get_info_value("性别", "男")
            if sex not in ["男", "女"]:
                sex = "男"

            #get dimension info
            for dimension in dimension_score_map:
                if dimension_score_map[dimension]["name"] == "个人幸福能力":
                    total_score = round(dimension_score_map[dimension]["score"], 2)
                    normsdist_score = normsdist(((total_score - average_value) *1.00)/total_score*1.00) * 100
                    data["msg"]["total"] = total_score
                    break

            #get title and comment
            if normsdist_score >= 98:
                data["msg"]["title"] = ["得力猛将","无冕之王","孤独求败"][random.randint(0,2)]
                data["msg"]["comment1"] = ["你在职场游刃有余，具有高超的职场幸福能力！",
                                           "请收下这对膝盖，幸福潜力MAX的你能hold住你的所有工作！"][random.randint(0,1)]
                if sex == "男":
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_man01%402x.png"
                else:
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_woman01%402x.png"
            elif normsdist_score>=84:
                data["msg"]["title"] = ["职场达人","活力本力","实干家"][random.randint(0,2)]
                data["msg"]["comment1"] = ["你是公认的职场达人！拥有较高的职场幸福能力。",
                                           "偶尔会烧脑但聪明的你，最后总能把压力变成幸福的动力。",
                                           "工作注定是你的恋人，虽然有时会给你添点小麻烦但也刺激着你更有活力。"][random.randint(0,2)]
                if sex == "男":
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_man02%402x.png"
                else:
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_woman02%402x.png"

            elif normsdist_score>=50:
                data["msg"]["title"] = ["职场高手","职场野狼"][random.randint(0,1)]
                data["msg"]["comment1"] = ["你是玩转职场的高手，在部分职场幸福能力上表现高超。",
                                           "吃鸡看脸的你，还需要修炼更多硬核的幸福潜力！",
                                           "有时候工作就像追女孩，你拼命追她拼命逃，你需要一点”撩”的技巧哦。"][random.randint(0,2)]
                if sex == "男":
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_man03%402x.png"
                else:
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_woman03%402x.png"
            else:
                data["msg"]["title"] = ["职场菜鸟","职场小奶猫"][random.randint(0,1)]
                data["msg"]["comment1"] = ["你在12项职场幸福能力上的表现部分有待提高和发展！",
                                           "犹如误入逃杀秀的小猫咪，总是紧张的你需要更多的方法来提升自己的职场幸福潜力",
                                           "职场的悲伤逆流成河，或许你需要一点幸福的能量？快来看有哪些幸福潜力能够提升吧。",
                                           "一入职场深似海，一谈工作误终生，现在的你急需提升职场活力哦。"][random.randint(0,3)]
                if sex == "男":
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_man04%402x.png"
                else:
                    data['msg']['image'] = "http://iwedoing-1.oss-cn-hangzhou.aliyuncs.com/report/%E4%B8%AA%E4%BA%BA%E5%B9%B8%E7%A6%8F%E8%83%BD%E5%8A%9B/pic_woman04%402x.png"

            #get quota info
            for info in data["msg"]["ChartEudaemonia"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"] == info["name"]:
                        if substandard_score_map[substandard_id]["score"] > 100:
                            comment = POSITIVE_COMMENTS[info["name"]].split('/')
                            positive_comments.append(comment[random.randint(0,len(comment)-1)])
                        elif substandard_score_map[substandard_id]["score"] < 75:
                            comment = NEGATIVE_COMMENTS[info["name"]].split('/')
                            negative_comments.append(comment[random.randint(0,len(comment)-1)])
                            negative_quotas.append(info["name"])

                        percentage_score = round(substandard_score_map[substandard_id].get("normsdist_score", 0), 2)
                        if percentage_score > 100:
                            info["score"] = 10
                        else:
                            for index, index_score in enumerate(SCORE_MAP):
                                if percentage_score <= index_score:
                                    info["score"] = index + 1
                                    break
                        break

            #get comments
            if not positive_comments:
                positive_comments.append(NOPOSITIVECOMMENT)
            if not negative_comments:
                negative_comments.append(NONEGATIVECOMMENT)

            data["msg"]["comment2"]=positive_comments+negative_comments

            for quota in negative_quotas:
                comment = SUGGESTION[quota].split('/')
                data["msg"]["comment3"].append(comment[random.randint(0,len(comment)-1)])

        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return data, ErrorCode.INVALID_INPUT
        return data, ErrorCode.SUCCESS


    def post(self, request, *args, **kwargs):
        u"""
        {
        "assess_project_id":45,
        "questionnaire_id":66,
        "user_id":67,
        "report_type_id": "BehavioralStyle"
        }
        :param request:
        :param args:
        :param kwargs:d
        :return:
        """
        # assess_project_id = self.request.data.get("assess_project_id", None)
        # questionnaire_id = self.request.data.get("questionnaire_id", None)
        # user_id = self.request.data.get("user_id", None)
        personal_result_id = self.request.data.get("people_result_id", None)
        report_type_id = self.request.data.get("report_type_id", None)
        try:
            data, err_code = eval(self.REPORT_MAP[report_type_id])(personal_result_id)
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": "people report data not found"})
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
                "report_data": data
            })
        except Exception, e:
            err_logger.error("ReportDataView error, msg is %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": "%s" %e})


class FinishTxTView(WdRetrieveAPIView):
    GET_CHECK_REQUEST_PARAMETER = ("project_id", )
    model = AssessProject
    serializer_class = AssessmentBasicSerializer

    # def get(self, request, *args, **kwargs):
    #     try:
    #         obj = AssessProject.objects.get(id=self.assess_id)
    #     except:
    #         err_logger.error("assessproject not exists error %s" % e)
    #         return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": "project found"})
    #     return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"finish_txt": obj.finish_txt})
    def get_object(self):
        return AssessProject.objects.get(id=self.project_id)


class ReportFinishCallback(AuthenticationExceptView, WdCreateAPIView):

    def post(self, request, *args, **kwargs):
        personal_result_id = self.request.data.get("people_result_id", None)
        report_status = self.request.data.get("report_status", None) # 0 ing, 1 success, 2 failed
        report_url = self.request.data.get("report_url", None)
        en_report_url = self.request.data.get("en_report_url", None)
        debug_logger.debug("report callback of %s, %s" %(personal_result_id, report_status))
        if report_status is None or personal_result_id is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        report_status = int(report_status)
        try:
            obj = PeopleSurveyRelation.objects.get(id=personal_result_id)
        except:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        else:
            if report_status == 1:  # success
                if obj.report_status != PeopleSurveyRelation.REPORT_SUCCESS or obj.report_url != report_url:
                    obj.report_status = PeopleSurveyRelation.REPORT_SUCCESS
                    if report_url:
                        obj.report_url = report_url
                    if en_report_url:
                        obj.en_report_url = en_report_url
                    obj.save()
            elif report_status == 2:  # failed
                if obj.report_status != PeopleSurveyRelation.REPORT_SUCCESS:
                    obj.report_status = PeopleSurveyRelation.REPORT_FAILED
                    obj.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class PeopleLoginOrRegistrerView(AuthenticationExceptView, WdCreateAPIView):
    POST_CHECK_REQUEST_PARAMETER = ("account", "account_type")

    def find_user_with_account(self, account_type, account, ep_id):
        pa_qs = PeopleAccount.objects.filter_active(account_type=account_type, account_value=account, enterprise_id=ep_id)
        if pa_qs.count() == 1:
            po_obj = People.objects.filter_active(id=pa_qs[0].people_id)[0]
            return AuthUser.objects.filter(id=po_obj.user_id)[0], 1
        elif pa_qs.count() == 0:
            return None, 0
        else:
            po_obj = People.objects.filter_active(id=pa_qs[0].people_id)[0]
            return AuthUser.objects.filter(id=po_obj.user_id)[0], 1
            # return None, 2

    def register_user_with_account(self, account, pwd):
        default_pwd = 'dh2018'
        # default_pwd = 'dh2018' if not pwd else pwd
        nickname = account
        username = nickname + get_random_char(6)
        authuser_obj = AuthUser.objects.create(
            username=username,
            account_name=account,
            nickname=nickname,
            password=make_password(default_pwd),
            active_code=get_random_int(8),
            active_code_valid=True
        )
        return authuser_obj, default_pwd

    def user_join_assess(self, assess_id, user, account_type, account, ep_id, org_code):
        po_obj, ret = People.objects.get_or_create(user_id=user.id, username=user.nickname)
        AssessUser.objects.get_or_create(assess_id=assess_id, people_id=po_obj.id)
        PeopleOrganization.objects.get_or_create(people_id=po_obj.id, org_code=org_code)
        PeopleAccount.objects.get_or_create(
            account_type=account_type,
            account_value=account,
            enterprise_id=ep_id,
            people_id=po_obj.id
        )
        send_one_user_survey(assess_id, po_obj.id)

    def post(self, request, *args, **kwargs):
        account = self.account
        account_type = int(self.account_type)
        pwd = request.data.get('password', None)
        assess_id = settings.dingzhi_assess_id
        ep_id = AssessProject.objects.get(id=assess_id).enterprise_id
        org_code = Organization.objects.filter(assess_id=assess_id).values_list("identification_code", flat=True)
        if not org_code.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_EMPTY_ERROR, {"msg": u"项目没有组织"})
        user, ret = self.find_user_with_account(account_type, account, ep_id)
        if ret == 2:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_EXISTS)
        if not user:
             user, pwd = self.register_user_with_account(account, pwd)
        if user and not pwd:
            user, err_code = UserAccountUtils.user_login_web_without_pwd(request, user)
        else:
            user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        user_info = UserBasicSerializer(instance=user, context=self.get_serializer_context()).data
        self.user_join_assess(assess_id, user, account_type, account, ep_id, org_code[0])
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"user_info": user_info, "login_account": account})