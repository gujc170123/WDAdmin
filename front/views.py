# -*- coding:utf-8 -*-
from __future__ import unicode_literals

# Create your views here.
import base64
import json
import random,collections
import uuid
import datetime

from django.db.models import Q
import operator
import time
from datetime import date 

from django.contrib.auth import logout
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from rest_framework import status
from sales.models import Balance,Consume
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
    PeopleAccount, BaseOrganization
from wduser.serializers import UserBasicSerializer, OrganizationBasicSerializer
from wduser.user_utils import UserAccountUtils
from utils.math_utils import normsdist
from django.db import connection
import numpy as np
from django.db.models import Count


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
                info_logger.info("people_id can not find people user obj")
                pass
        return ErrorCode.FAILURE, None

    def post(self, request, *args, **kwargs):
        link = request.data.get('enterprise_dedicated_link', None)
        account = request.data.get('account', None)
        pwd = request.data.get("pwd", None)
        assess_id_base64 = self.request.data.get("ba", None)
        if account is None or pwd is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)

        enterprise = 0
        if assess_id_base64:
            assess_id = base64.b64decode(assess_id_base64)
            try:                
                project = AssessProject.objects.get(id=assess_id)
                enterprise = project.enterprise_id
                if not BaseOrganization.objects.filter(enterprise_id=enterprise).first():
                    enterprise = 0
            except:
                err_logger.error("project not found: %s" % assess_id)
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)    

        
        if not link:
            # enterprise check appended
            user, err_code = UserAccountUtils.account_check(account,enterprise=enterprise)
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, err_code)
        else:
            ret, msg, user = link_login(link, account, pwd)
            if ret != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ret, {'msg': msg})
                
        user, err_code = UserAccountUtils.user_login_web(request, user, pwd)

        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        user_info = people_login(request, user, self.get_serializer_context())
        if not user_info['enteprise']:
            user_info['enterprise'] =0
        else:
            user_info['enterprise'] = enterprise
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
            #check register balance
            balance = Balance.objects.filter(enterprise_id=project.enterprise_id,sku__lte=2,validto__gte=date.today()).first()
            if balance:
                if balance.number<1:
                    return ErrorCode.OVERLIMIT
                else:
                    Consume.objects.create(balance_id=balance.id,
                                           number=1)
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
            EnterpriseAccount.objects.create(enterprise_id=project.enterprise_id,account_name=user.account_name,user_id=user.id,people_id=people.id)
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
            if not BaseOrganization.objects.filter(enterprise_id=enterprise).first():
                enterprise = 0
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
        if not peoples:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_EXISTS)
        people = peoples[0]
        people_id = people.id
        
        tmpprofile = {}
        dictprofile = {}
        if self.project_id=='all':
            self.project_id=0
        else:
            # create people-organization relation if not exist
            user = AuthUser.objects.get(id=people.user_id)
            if user.organization:
                org = Organization.objects.get(assess_id=self.project_id,is_active=True,baseorganization_id=user.organization)
                AssessUser.objects.get_or_create(assess_id=self.project_id, people_id=people.id)            
                PeopleOrganization.objects.get_or_create(people_id=people.id,org_code=org.identification_code)
        gather_obj = AssessGatherInfo.objects.filter_active(assess_id=self.project_id)
        userupdate_argsdict = {}
        peopleupdateflag = False        

        # iterate user input infomration and update user gatherinfo
        # info is a dict structure with "id", "info_value", "option_id" members
        for info in self.infos:
            obj, created = UserProjectSurveyGatherInfo.objects.update_or_create(
                is_active=True,
                people_id=people_id,
                info_id=info["id"],
                defaults={
                    'people_id':people_id,
                    'info_id':info["id"],
                    'info_value':info["info_value"],
                    'option_id':info.get("option_id", 0)})
            tmpprofile[info["id"]]=[info["info_value"],info.get("option_id", None)]
        
        for gather in gather_obj:
            if gather.id not in tmpprofile.keys():
                continue
            if not tmpprofile[gather.id][0]:
                continue
            dictprofile[gather.info_name]=tmpprofile[gather.id][0]
            if not gather.info_id:
                continue
            if not gather.value_info:
                userupdate_argsdict[gather.info_id]= tmpprofile[gather.id][0]
                if gather.info_id=='nickname':
                    people.username = tmpprofile[gather.id][0]
                    peopleupdateflag = True
            elif tmpprofile[gather.id][1] is not None:
                values = json.loads(gather.value_info)
                idx = int(tmpprofile[gather.id][1])
                if len(values)>idx:
                    userupdate_argsdict[gather.info_id]= values[idx]

        # update people profile
        if people.more_info:
            originprofile = json.loads(people.more_info)        
        else:
            originprofile = None            
        if dictprofile:
            if originprofile:
                if type(originprofile) is list:
                    tmpprofile = originprofile[:]
                    originprofile = {}
                    for row in tmpprofile:
                        originprofile[row['key_name']]=row['key_value']
                originprofile.update(dictprofile)
                people.more_info = json.dumps(originprofile)
                peopleupdateflag = True
            else:
                people.more_info = json.dumps(dictprofile)
                peopleupdateflag = True
        if peopleupdateflag:
            people.save()

        # update user profile
        if userupdate_argsdict:
            user  = AuthUser.objects.get(id=user_id)
            for key, value in userupdate_argsdict.items(): 
                setattr(user, key, value)
            user.save()

        # if people.more_info:
        #     people_more_info = json.loads(people.more_info)
        # else:
        #     people_more_info = []
        # people_more_info_map = {}
        # for p_info in people_more_info:
        #     people_more_info_map[p_info["key_name"]] = p_info
        # is_modify = False
        # for info in self.infos:
        #     project_id = self.project_id
        #     if info.get("assess_id", None) is not None:
        #         project_id = info.get("assess_id")
        #     qs = UserProjectSurveyGatherInfo.objects.filter_active(
        #         people_id=people_id,
        #         info_id=info["id"]
        #     )
        #     if qs.exists():
        #         qs.update(info_value=info["info_value"], option_id=info.get("option_id", 0))
        #     else:
        #         UserProjectSurveyGatherInfo.objects.create(
        #             people_id=people_id, # project_id=project_id,
        #             info_id=info["id"], info_value=info["info_value"],
        #             option_id=info.get("option_id", 0)
        #         )
        #     if info["info_value"]:
        #         is_modify = True
        #         gather_obj = AssessGatherInfo.objects.get(id=info["id"])
        #         if gather_obj.info_name == u"姓名":
        #             people.username = info["info_value"]
        #         else:
        #             people_more_info_map[gather_obj.info_name] = {
        #                 'key_name': gather_obj.info_name,
        #                 'key_value': info["info_value"],
        #                 'key_id': info["id"]
        #             }
        # if is_modify:
        #     people_more_info = [people_more_info_map[k] for k in people_more_info_map]
        #     people.more_info = json.dumps(people_more_info)
        #     people.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def get(self, request, *args, **kwargs):
        user_id = self.request.user.id
        peoples = People.objects.filter_active(
            user_id=user_id).order_by("-id")
        people = peoples[0]
        people_id = people.id
        self.project_id = int(self.project_id)
        # get assess info to gather
        if self.project_id:
            # gather_info = AssessGatherInfo.objects.filter_active(
            #     Q(assess_id=0) | Q(assess_id=self.project_id)).values("id", "info_name", "info_type", "config_info",
            #         "assess_id", "is_required", "is_modified").distinct()
            gather_info = AssessGatherInfo.objects.filter_active(assess_id=self.project_id).values(
                "id", "info_name", "info_type", "config_info","assess_id", "is_required", "is_modified")
        else:
            # project_ids = AssessUser.objects.filter_active(people_id=people_id).values_list("assess_id", flat=True)
            # gather_info = AssessGatherInfo.objects.filter_active(
            #     Q(assess_id=0) | Q(assess_id__in=project_ids)).values("id", "info_name", "info_type", "config_info",
            #         "assess_id", "is_required", "is_modified").distinct()
            gather_info = AssessGatherInfo.objects.filter_active(assess_id=0).values(
                "id", "info_name", "info_type", "config_info","assess_id", "is_required", "is_modified")
        data = []
        is_finish = True
        info_name_list = []
        # merge gathered info and actual info
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
                            # when max_value equals 10 exit random
                            if random.randint(0, 1) and question["options"]["max_value"]<10:
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
                            # when max_value equals 10 exit random
                            if random.randint(0, 1) and question["options"]["max_value"]<10:
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
        reports = {70:'wv2019',89:'disc2019',96:'mbti2019',97:'ls2019',98:'ppsy2019',99:'pc2019',100:'co2019',147:'peoi2019',159:'mc2019',163:'peoi2019',167:'mc201990',172:'peoi2019',}
        if self.block_id == 0:
            qs = PeopleSurveyRelation.objects.filter_active(
                people_id=people.id,
                survey_id=self.survey_id,
                project_id=self.project_id,
                role_type=self.role_type,
                evaluated_people_id=self.evaluated_people_id
            )
            if self.survey_id in [70,89,96,97,98,99,100,147,159,163,167,172]:
                for o in qs:
                    o.status=PeopleSurveyRelation.STATUS_FINISH
                    o.report_status=PeopleSurveyRelation.STATUS_FINISH
                    o.finish_time=datetime.datetime.now()
                    o.report_url=settings.Reports[reports[self.survey_id]] % (o.id)
                    o.save()
            else:
                qs.update(
                    status=PeopleSurveyRelation.STATUS_FINISH,
                    report_status=PeopleSurveyRelation.REPORT_GENERATING,
                    finish_time=datetime.datetime.now()
                )
                # maanshan
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
                    if self.survey_id in [70,89,96,97,98,99,100,147,159,163,167,172]:
                        for o in qs:
                            o.status=PeopleSurveyRelation.STATUS_FINISH
                            o.report_status=PeopleSurveyRelation.STATUS_FINISH
                            o.finish_time=datetime.datetime.now()
                            o.report_url=settings.Reports[reports[self.survey_id]] % (o.id)
                            o.save()
                    else:
                        qs.update(
                            status=PeopleSurveyRelation.STATUS_FINISH,
                            report_status=PeopleSurveyRelation.REPORT_GENERATING,
                            finish_time=datetime.datetime.now()
                        )
                        # maanshan
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
            # create assess-user,people-organization relation
            user = AuthUser.objects.get(id=people.user_id)
            if user.organization:
                org = Organization.objects.get(assess_id=self.project_id,is_active=True,baseorganization_id=user.organization)
                AssessUser.objects.get_or_create(assess_id=self.project_id, people_id=people.id)            
                PeopleOrganization.objects.get_or_create(people_id=people.id,org_code=org.identification_code)
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
        # 中高层180
        "ZGC180": 'self.get_zgc180_value',
        # 中高层90
        "ZGC90": 'self.get_zgc90_value',        
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
        # 180MC
        "MC2019": 'self.getMC2019',
        # PEOI2019
        "PEOI2019": 'self.getPEOI2019',
        # PPSY2019
        'PPSY2019': 'self.getPPSY2019',
        # LS2019
        'LS2019': 'self.getLS2019',
        # WV2019
        'WV2019': 'self.getWV2019',
        # PC2019
        'PC2019': 'self.getPC2019',        
        # 90MC
        "MC2019_90": 'self.getMC2019_90',
        # MBTI_COMPLETE
        "MBTI2019F": "self.getMBTI2019_F",           
    }

    def getMBTI2019_F(self, personal_result_id):
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
            if not people_result.report_url:
                people_result.report_url= settings.Reports['mbti2019f'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
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
                'ENFJ':{'content':u'教导型','description':[u'您善于社交、易感应、善劝服。您精力旺盛，热情洋溢，能很快理解他人情感的需要、动机和所忧虑的事情，因此能做到与他人保持协调。',u'您把注意力放在帮助他人，鼓励他人进步向上。您是催化剂，能引发出他人的最佳状态。既可以做有号召力的领袖，也可以做忠实的追随者。',u'您性情平和，心胸宽阔，且很圆滑，很会促进周边关系的和睦，对于批评和紧张特别敏感。',u'您容易看出他人的发展潜力，并倾力帮助他人发挥潜力，是体贴的助人为乐者。您愿意组织大家参与活动，使大家和睦又感到愉快。',u'您是理想主义者，看重自己的价值，对自己尊重敬仰的人、事业和公司都表现出一定的忠诚度。',u'您有责任感、谨慎、坚持不懈，同时对新观点很好奇。若能为人类的利益有所贡献，您会感到深受鼓舞。',u'您对现实以外的可能性，以及对他人的影响感兴趣，较容易发现别人看不到的意义和联系，并感到自己与万物息息相关，可以井然有序地安排生活和工作。'],'blindness':[u'您较容易理想化，认为世界应是自己想象中的那样，不愿意接受与此相抵触的事情，较容易忽略理想所需要的现实和细节问题。',u'您依照情感行事，较少用逻辑，主要根据个人的价值观进行判断，有时容易无视行为所带来的后果，过度陷入别人的情感和问题中。',u'您追求避免冲突，有时会不够诚实和公平。试着更多地去关注事情，而不只是人，会更有助于您做出合理的决定。',u'您有很高的热情，急于迎接新的挑战，有时会做出错误的假设或过于草率的决定。建议您对计划中的细节多加注意，等获取足够多的信息之后再做决策。',u'您总想得到表扬，希望自己的才能和贡献得到赏识，您对于批评脆弱，容易忧虑，感到内疚，失去自信。当压力很大时，会变得烦躁、慌乱、吹毛求疵。'],'advantage':[u'通常具有优秀的交流及表达能力，某些人能够成为出色的演说家；',u'天生的领导才能及凝聚力，鞭策自己做出成绩，达到目的；',u'有组织能力，有较强的建立合作关系的能力，能够促进和谐，尊重不同意见；',u'兴趣广泛，头脑灵活，渴望推陈出新；',u'善于与别人感情交融，能预见别人的需要，真诚地关怀别人；',u'能统观全局，洞察行为与意识之间的联系；',u'对自己所信仰的事业尽职尽责；',u'有稳定平和的心态，有冲劲和闯劲，不患得患失。'],'disadvantage':[u'不愿意干与自己价值观相冲突的事情；',u'不愿与别人产生分歧或冲突，容易把人际关系理想化；',u'很难在竞争强、气氛紧张的环境下工作，逃避矛盾冲突，疏忽不愉快的事情；',u'对那些没有效率或死脑筋的人没有耐心；',u'在没有收集足够证据前，易于仓促决定，容易因轻率犯错误；',u'易于满足小范围管理，决不放弃控制权；',u'可能过于个人化地对待批评；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'工作环境轻松，可以接触各种各样的人，并与他们建立和维护亲密、互助的关系；',u'工作中可以接触到新观念，探究新方法，尤其那些可以帮助他人改善的方法；',u'有相当的自主权，并承担一定的责任，充分发挥组织和决策能力；',u'可以创造性地解决问题，做出的贡献能够得到别人的赏识和鼓励；',u'工作有较强的变化性、挑战性，允许您有条不紊地进行规划；',u'工作允许您同时掌控多个项目，但不要过多处理常规和细致的部分。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您喜欢那些经常有外出机会，果断和行动导向的企业文化；',u'您希望每天能与许多人接触，愿意积极的建立起广泛的社会关系网，建立起新的商业机会；',u'工作可以直接与客户打交道，如销售人员，商业拓展人员等。自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求不高','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织。',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）；',u'工作中您更相信您的直觉，而不是精细的计划和安排。',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化；',u'您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋；',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有很大风险性的事情。那些鼓励或奖励创新和新思想的企业文化，那些非传统的工作适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您喜欢能培养友好、合作和“温暖”工作氛围的企业文化；',u'办公室对您来说既是一个商业场合也是一个交朋友的地方；',u'您有很强的利他主义情感，并且期望大多数同事有着此种情感或价值观；',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化。那种崇尚内部竞争和敢闯敢干的企业肯定不是您成功的地方。']},'SuccessKey':[u'适当放慢您的做事速度；',u'不要事事控制，学会放手某些事情；',u'客观、理智地对待周围的一切，以免人为的将事情变复杂。'],'Proposal':[u'尽量避免盲目的信任和赞同；',u'需要正视冲突，并寻找有成效的解决办法； ',u'需要像关注人一样关注任务的细节；',u'需要仔细倾听外界的反馈信息，变得更加开放； ',u'目前不要考虑在压力大的环境中工作；',u'适合的时候，主动承担一些工作对您的发展更有利； ',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'广告关系主管、公共关系专家、对外交流董事、新闻工作者、资金筹备人、招聘人员、电视制片人、信息制图设计者、营销经理',u'公关专家、营销顾问、广告业务经理、公告撰稿人/公共写作者、广告创意指导、战略策划人、报刊宣传员、调研助理、编辑或艺术指导',u'特殊教育老师、双语种教育老师、儿童早教、艺术戏剧、音乐老师、儿童福利顾问、社会工作者、职业发展指导顾问、民意调查员、康复中心工作人员、社会学家、心理学家',u'营养专家、雇员辅助计划顾问、理疗专家、法律调停人',u'人力资源培训专员、推销培训员、旅游产品代理、小型企业经理、项目设计人、销售经理、管理顾问'],'Reason': [u'作为熟练的交流者，ENFJ型的人善于理解他人，使他人高兴，因此常常具备足够老练的外交手段。您们有时更喜欢口语而不是书面语言，即使您们同样是很好的写作者。您们对于直接与人接触的偏好，在这些职业中都能得到满足。',u'ENFJ型的人通常是思维广阔的人，能轻易看出一个想法、计划对于他人的效果。您们在计划中考虑别人的关注点，经常能得到创新和富有人情味的解决方法。您们聪明有趣，当自己的创意收到采纳时尤其能够得到满足感。',u'ENFJ型的人大多满足于对他人有积极影响力的工作。您们富于同情心，且能够鼓励他人，热诚而又有创造力。关注可能性，且能够以充满感染力和旺盛精力的风格激励客户在生活中进行积极的改变。乐于帮助别人发展个人的精神世界，乐于帮助他人获得可利用的资源。',u'这些领域对于他们有吸引力，因为这些工作既能够让您以创造性的方法给予人帮助，也能保持自身的独立和灵活。',u'咨询行业的许多工作可以给ENFJ型的人提供职业满足感，这样的工作中可以在和他人保持密切联系的同时保持独立性。富于创造力而精力充沛的您也善于产生新方案，并对他人施加积极的影响。']}},
                'ENFP':{'content':u'公关型','description':[u'您对周围的人和事物观察得相当透彻，能够洞察现在和将来。随时可以发现事物的深层含义和意义，并能看到他人看不到的事物内在的抽象联系。',u'您崇尚和谐善意、情感多样、热情、友好、体贴、情绪强烈，需要他人的肯定，也乐于称赞和帮助他人。您总是避免矛盾，更在意维护人际关系。',u'您富有活力，待人宽厚，有同情心，有风度，喜欢让人高兴。只要可能，您就会使自己适应他人的需要和期望。',u'您倾向于运用情感作出判断，决策时通常考虑他人的感受。您在意维护人际关系，愿意花费很多心思，结交各种各样的人，而不是做事。',u'您有丰富的想象力，善于创新，自信，富有灵感和新思想，警觉，善于寻找新方法，更注重理解，而不是判断。',u'您喜欢提出计划，并大力将其付储实施。您特别善于替别人发现机会，并有能力且愿意帮助他们采取行动抓住机会。'],'blindness':[u'您较为理想化，容易忽视现实和事物的逻辑，只要感兴趣，什么都去做。',u'您通常在事情开始阶段或有变化的阶段较为投入，而对后续较为常规或沉闷的部分，难以持续投入。',u'您总是能轻易地想出很多新注意，喜欢着手许多事情，无法专注于一件事情，很少能把事情“从头做到尾”。',u'您总能看到太多的可能性，因此无法确定哪些事情是自己真正追求的。建议您认真选择一个目标，善始善终，以免浪费时间和挥霍自己的天赋。',u'您组织纪律性比较弱，不肯服从，无视限制和程序。您喜欢即兴发挥，不愿意筹备和计划，对细节没有兴趣。如果您要有所作为，应尽量使自己的新思路现实、可操作。与更注重实际的人一起工作会对您很有帮助，这也符合您的特点，因为您不喜欢独自工作。'],'advantage':[u'能够打破常规思考，考虑事情发展可能出现的新情况；',u'敢于冒险、敢于尝试新事物，能克服障碍，能够在任何您真正感兴趣的领域中成功；',u'适应能力强，能迅速改变自己的行事速度及目标，兴趣广泛、对自己感兴趣的东西接受能力强；',u'对收集自己所需信息有一种天生的求知欲和技能；',u'能统观全局，能看出行为和思想之间的潜在含义交际能力强，能以有感染力的热诚和精力激励他人；',u'能洞察别人，能理解他们的需要和动机；',u'是富于创造的思考者，好的问题解决者；',u'能够把自己的天赋与别人的兴趣和能力集合起来，善于赋予适合的人以合适的职位/任务；',u'有稳定平和的心态，不患得患失。'],'disadvantage':[u'做事不太关注条理性，或不善于分清主次顺序，把握事情的轻重；',u'对缺乏独创性的人和事没有耐心；',u'通常不喜欢任何重复或例行的事务，不愿以传统或常规的方式行事；',u'易于烦躁或不耐烦，尤其是当工作上的创造性过程结束后；',u'不能容忍与过于严谨的机构或个人工作，组织性观念不强；',u'倾向于关注可能发生的事情，而非实际的或极可能发生的事情；',u'在工作细节的完成上有一定困难；',u'独自工作时经常效率较低；',u'斗志不足，容易松懈，有时不愿付出过多的努力；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'在人际友好、轻松的环境中与不同特点的人一起工作，避免冲突和矛盾；',u'工作充满乐趣，富于挑战，允许您自由发挥灵感和创造力，参与冒险；',u'可以创造新的想法、产品、服务或帮助别人，然后看到计划变为现实；',u'工作环境与您的理念、个人价值观一致；',u'规则和限制少，能够自己安排工作的进程和节奏；',u'工作不要求处理太多的重复性、程序性、常规性、琐碎的事物。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您喜欢那些经常有外出机会，果断和行动导向的企业文化。您希望每天能与许多人接触，愿意积极的建立起广泛的社会关系网，建立起新的商业机会。',u'工作可以直接与客户打交道，如销售人员，商业拓展人员等。自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求不高','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织。',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）；',u'工作中您更相信您的直觉，而不是精细的计划和安排。',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化；',u'您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋；',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有很大风险性的事情。那些鼓励或奖励创新和新思想的企业文化，那些非传统的工作适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您喜欢能培养友好、合作和“温暖”工作氛围的企业文化。',u'办公室对您来说既是一个商业场合也是一个交朋友的地方。',u'您有很强的利他主义情感，并且期望大多数同事有着此种情感或价值观。',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化。那种崇尚内部竞争和敢闯敢干的企业肯定不是您成功的地方。']},'SuccessKey':[u'判断和把握事情轻重，优先处理重要的事情；',u'集中精力于某一目标，尽量将事情计划和落实；',u'减少外界无关因素的干扰，对自己接受的事情坚持到底，不要轻易妥协。'],'Proposal':[u'设立事情的优先级，考虑轻重缓急，发展持之以恒；',u'需要关注重要的细节，避免总是丢三落四；',u'需要规划和计划，并运用时间管理技能；',u'目前不要考虑在压力大的环境中工作；',u'在适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'人力资源开发/培训/招聘人员、销售经理、小企业经理、市场（拓展）人员',u'公共关系、营销、市场开发、客户服务、艺术指导、广告人、战略规划人员',u'文科/艺术类教师、社会工作者、职业顾问、社会学者、心理学者、职业治疗、城市规划、营养学者',u'顾问、人力资源人员、策划、企业／团队培训人员、业务主管、销售等'],'Reason': [u'这些工作的创造性是吸引您的一个很明显的原因，它们能够让您新颖独特的想法充分发挥，尤其当环境无拘无束，并能从帮助别人中获得鼓励时。',u'您的特点是可以轻易的看到某个方法、计划或服务可能给别人带来的结果，善于深谋远虑，还可以发明一些富有创造意义的解决问题的方法。',u'您有活力、有感染力，喜欢能够对别人产生积极影响的工作，帮助他人找到新颖的解决方法。',u'那些自由灵活，可以实现您各种想法，尤其是能对别人产生一定影响的想法是您所喜欢的领域。']}},
                'ENTJ':{'content':u'领导者型','description':[u'您直率、果断，能够妥善解决组织的问题，是天生的领导者和组织的创建者。',u'您擅长发现一切事物的可能性并愿意指导他人实现梦想，是思想家和长远规划者。',u'您逻辑性强，善于分析，能很快地在头脑里形成概念和理论，并能把可能性变成计划。树立自己的标准并一定要将这些标准强加于他人。',u'您看重智力和能力，讨厌低效率，如果形势需要，可以非常强硬。',u'您习惯用批判的眼光看待事物，随时可以发现不合逻辑和效率低的程序并强烈渴望修正它们。',u'您善于系统、全局地分析和解决各种错综复杂的问题，为了达到目的，您会采取积极行动。',u'您喜欢研究复杂的理论问题，通过分析事情的各种可能性，事先考虑周到，预见问题，制定全盘计划和制度并安排好人和物的来源，推动变革和创新。',u'您愿意接受挑战，并希望其他人能够像自己一样投入，对常规活动不感兴趣。长于需要论据和机智的谈吐的事情，如公开演讲之类。'],'blindness':[u'您较容易在没有了解细节和形势之前就草率地做决定。',u'您容易很客观、带有批判性地对待生活，容易对别人的情况和需要表现得较粗心、直率、无耐心。建议您注意倾听周围人的心声，并对别人的贡献表示赞赏。您需要学会在实施自己的计划之前听取别人的建议，以免独断专横。',u'您考虑问题非常理智，很少受无关因素影响。您没有时间和兴趣去体会情感，容易忽略他人的感受，显得不尽人情。但当您的感情被忽视或没有表达出来的时候，您会非常敏感。您需要给自己一点儿时间来了解自己的真实感情，学会正确地释放自己的情感，而不是爆发，并获得自己期望和为之努力的地位。',u'您容易夸大自己的经验、能力。您需要接受他人实际而有价值的协助，才能更好地提高能力并获得成功。'],'advantage':[u'自信且有天生的领导才能；',u'敢于采取大胆行动，有不达目的不罢休的势头；',u'能看到事情的可能发展情况及其潜在的含义；',u'有创造性解决问题的能力，能客观地审查问题；',u'有追求成功的干劲和雄心，能够时刻牢记长期和短期目标；',u'对于在工作中胜任有强烈的动机，能逻辑地、分析地做出决定；',u'能创造方法体系和模式来达到您的目标；',u'擅长于从事技术性工作，学习新东西时接受能力强；',u'在有机会晋升到最高职位的机构中工作出色；',u'雄心勃勃，工作勤奋，诚实而直率，工作原则强；',u'有稳定平和的心态；',u'重视安全和保障。'],'disadvantage':[u'对那些反应不如您敏捷的人缺乏耐心；',u'容易唐突，缺乏交际手段；',u'对一些世俗的小事没有兴趣，对那些既定问题不愿再审查；',u'不愿花时间适当地欣赏、夸奖同事或别人；',u'易于过分强调工作，从而忽略了家庭的合谐；',u'爱发号施令、挑剔、严厉；',u'容易因工作至上而忽视工作的其他方面；',u'易于仓促作决定，有时会因急于做出决定而忽视有关的事实和重要细节；',u'可能不要求或不允许别人提供建议和帮助。'],'PositionMatch':[u'有组织、有条理的工作环境，在清晰而明确的指导原则下与他人一起工作；',u'充满挑战和竞争的氛围，需要创造性处理复杂而且难度较大的问题，提出合乎逻辑的解决办法；',u'领导、管理、组织和完善一个机构的运行体系，确保有效运转并达到计划目标；',u'能够提高并展示个人能力，能够不断得到提升，有机会接触到各种各样有能力而且有权力的人；',u'成果能够得到他人肯定，并得到合理的回报；',u'能够确立工作目标，并施展组织才能，管理监督他人，而不需要处理人际冲突。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您较为开放，适合那些经常有外出机会，果断和行动导向的企业文化。',u'您希望每天能与许多人接触，愿意主动的建立起广泛的社会关系网，建立起新的商业机会。工作可以直接与客户打交道，如销售人员，商业拓展人员等。自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化。在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同。',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化。',u'您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋。',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有较大风险性的事情。',u'那些鼓励或奖励创新和新思想的企业文化，那些非传统的工作适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力。',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系。',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'适当放慢做事速度和行动的节拍；',u'注重细节、增强做事的耐心；',u'体谅他人的需要和感受，提高人际敏感度。'],'Proposal':[u'适当学会鼓励和欣赏他人的贡献，不要吹毛求疵；',u'在埋头苦干之前，仔细检查各种可利用的现实资源；',u'三思而后行，使决策更完善；',u'需要学会认同和看重感情，体会自己和他人的感受；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'正确看待失败，碰到困难不要随意放弃。'],'SuitableJob':{'JobType': [u'管理顾问、经济学者、银行业、金融规划师、人力资源、项目经理、股票经纪人、风险投资、营销、采购人员',u'教育顾问、培训师、职业发展顾问、战略顾问',u'律师、法官、心理学者、飞行员、工程师',u'网络主管、系统主管、系统分析家、项目经理'],'Reason': [u'商业和金融领域对您的适用范围比较广，您喜欢担任有权威、有控制力且能管理他人的工作。同样，在金融领域您喜欢赚钱，喜欢竞争。',u'咨询业的多样性和独立性也较为吸引您，与不同商业背景的人打交道，付出获得回报，能满足您的企业家精神。',u'某些职业所提供的社会地位和影响力也是您所感兴趣的，这些职位上所面临的智力挑战较能吸引您。',u'擅于理解并处理复杂问题、具有较强的逻辑思维能力和优秀的组织能力的您，在许多与科技相关的职业上可以得到满足。']}},
                'ENTP':{'content':u'智多星型','description':[u'您喜欢挑战让您兴奋的事情，聪慧，许多事情都比较拿手，致力于自己才干和能力的增长。',u'您有较强的创造性和主动性，绝大多数是事业型的。您好奇心强，喜欢新鲜事物，关注事物的意义和发展的可能性。通常把灵感看得比什么都重要，多才多艺，适应性强且知识渊博，很善于处理挑战性的问题。',u'您能快速抓住事物的本质，喜欢从新的角度和独到的方式思考问题，对问题经常有自己独到的见解。',u'您机警而坦率，有杰出的分析能力，并且是优秀的策略家。',u'您不喜欢条条框框的限制和因循守旧的工作方式，习惯便捷的问题解决方法。',u'您喜欢自由的生活并善于发现其中的乐趣和变化。',u'您认为“计划赶不上变化”，并以实际行动证明大部分规定和规律都是有弹性，可伸缩的，通常会超出被认可和期望的限度。',u'您乐观，善于鼓舞他人，能用自己的热情感染他人。'],'blindness':[u'您充满热情地寻找新鲜事物，但行事缺少稳定的计划和流程，经常依靠临场发挥，可能因为忽视必要的准备工作，而草率地身陷其中。',u'您的注意力容易游移，对目标的韧性和坚持性不够，缺乏足够的耐心，有时不能贯彻始终。一旦主要问题被解决了，就会转移到下一个目标，而不能坚持将一件事完完整整地结束。',u'您非常注重创造力和革新，容易忽略简单、常规的方法和一些重要的细节，不愿遵守规则和计划。建议多关注解决问题的常规方法。',u'您通常同时展开多项任务与活动，不愿丢掉任何一种可能性，致力于寻找新的变化，可能使别人的计划和时间安排受到影响。您要好好考虑一下自己的行动给他人带来的影响，这有助于您变得更可靠。',u'您有天生的直觉和预知能力，会使您误认为知道了别人的想法。建议您认真倾听他人，避免表现得不耐烦。'],'advantage':[u'较为出色的交际才能，能使别人对自己的观点感到兴奋；',u'探险精神、创新意识以及克服困难的勇气，急切地“想知道盒子外边的世界”、能想出一些新的可能性；',u'在连续的、充满刺激的工作中表现最出色，杰出的创造性解决问题的技能；',u'有“走自己的路、让别人去说吧”的乐观主义激情；',u'兴趣受好广泛、易于接受新事物，学习新知识的信心和动力都很强大；',u'天生的好奇心理，快速地搜集所需信息的技能，擅长创新和客观公正的分析；',u'能够把握事情的全局，弄清思想和行为的长远影响，并能同时处理多个问题；',u'能灵活地适应新情况，有熟练的变换能力；',u'在社交生活中不会感到拘谨，能舒适地适应大多数社交场合；',u'自信，只要想做，什么都能做到。'],'disadvantage':[u'难以使自己有条不紊和富有条理，在区分出应该优先对待的事物以及做出决定方面有一定的困难；',u'过于自信，可能会不恰当地运用自己的能力和社会经历；',u'倾向于用“是不是有可能”来看待问题，而不是以可能性、可行性的大小来衡量事物；',u'很可能会不切实际地许诺，可能会表现出不可靠、不负责任；',u'对思维狭窄及思想顽固的人缺乏耐心；',u'当创造性的问题解决后，便对项目失去兴趣，对待细节和后续工作可能缺乏耐心，对自己要求不严格，不能做具体细节工作，不能贯彻始终；',u'不喜欢例行的、单调重复的工作，坚持以自己已经建立起的方式办事；',u'对事物容易感到厌烦，并且可能在不恰当的时候把注意力转移到别的事情上去；',u'对自己不信任的人耐心不够；',u'经常打断别人说话，可能由于过分自信而影响他们的能力；',u'斗志不足，容易松懈,通常不愿付出过多的努力，在压力和挫折面前不够坚持。'],'PositionMatch':[u'工作能够充分发挥您的创造性和开拓性，并能得到承认和鼓励；',u'在快速成长、变化的环境中工作，从事挑战性较大的任务；',u'有一定的弹性，较为灵活，能够自由的、不受各种死板制度限制地工作；',u'工作能让您体验到乐趣、活跃和兴奋，不要做重复的、繁琐的、简单的细节工作；',u'能够让您结识不同的人，与有能力的人或自己尊重的人交往，并开展有意义的合作；',u'工作能够不断提高自己的能力；',u'允许您设计或者发起一项计划，但不要深陷乏味的细节。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您喜欢经常有外出机会，果断和行动导向的企业文化。',u'您希望每天能与许多人接触，愿意积极的建立起广泛的社会关系网，建立起新的商业机会。工作可以直接与客户打交道，如销售人员，商业拓展人员等。',u'自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较低','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织。',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）。',u'工作中您更相信您的直觉，而不是精细的计划和安排。',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化。',u'您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋。',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有较大风险性的事情。',u'那些鼓励或奖励创新和新思想的企业文化，那些非传统的工作适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力；',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系；',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'在认识上确立事物优先等级，不要“眉毛胡子一把抓”；',u'在行动上“集中优势兵力，各个歼灭”；',u'遵守时间约定，信守承诺。'],'Proposal':[u'需要关注现在和事实；',u'需要承认和确认别人的投入和作出的努力；',u'加强工作的计划性与条理性，完善时间管理，提高工作效率；',u'需要喜欢在系统中为项目工作和遵守规则；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'管理顾问、培训师、职业顾问、摄影师、记者、城市规划、证券分析、经销人/代理人、风险资本家、企业家、发明家等。',u'编辑、广告创意人、公关人员、营销、主持人、制片人、贸易行销人员、作家、信息服务人员等。 ',u'战略策划人员、项目开发者、房地产代理/开发、城市规划、投资/财政计划人员等。 ',u'刑侦人员、社会科学者、政治分析者、行政管理人员、教育心理学者等。'],'Reason': [u'您喜欢那些能够创新、灵活和富于变化的工作，可以与很多人打交道，有一定的冒险性。',u'那些可以通过有趣和创新的途径来发展自己想法和观点的领域，那些快节奏变化丰富的领域会满足您极大的好奇心和启发您积极的想象力。',u'您具有开放的眼光，对问题有自己独到的见解，善于预测事态的发展趋势，所以一些规划和开发的工作非常适合您。',u'那些在高度紧张、激烈的重要场合能够充分发挥运用您的思想知识，快速发现事情的关键所在的工作也在您考虑的范围内。']}},
                'ESFJ':{'content':u'主人型','description':[u'您非常重视与别人的关系，易觉察出他人的需要，并善于给他人实际关怀，待人友好、善解人意并有很强的责任心。看到周围的人舒适和快乐，也会感到快乐和满足，很健谈，因此非常受欢迎。',u'您热情，有活力，乐于合作，有同情心，机敏圆滑，希望得到别人的赞同和鼓励，冷淡和不友善会伤害您。',u'您需要和睦的人际关系，对于批评和漠视非常敏感，竞争和冲突会让您感觉到不愉快，因此尽力避免发生这样的事情。',u'您很实际、有条理，做事彻底，有一致性，对细节和事实有出色的记忆力，并且希望别人也如此。',u'您着眼于目前，在经验和事实之上做出决策，将事情安排妥当，喜欢自己成为活跃而有用的人物。',u'您能很好地适应日常的常规工作和活动，不喜欢做需要掌握抽象观点或客观分析的工作。喜爱自己的全部，对自己爱护有加。',u'您喜欢组织众人和控制形势，与他人合力圆满又按时地完成任务。喜欢安全和稳定的环境，支持现存制度，注重并很好地遵守社会约定规范。',u'您忠于自己的职责，并愿意超出自己的责任范围而做一些对别人有帮助或有益处的事情，在遇到困难和取得成功时，都很积极活跃，希望付出能得到回报或赞扬。'],'blindness':[u'您过分在意别人的情感和想法，以至于总是给予别人额外的关心和帮助，有时态度强硬，容易侵占别人的空间，您需要考虑一下自己提供的帮助是不是他人的需要。当遇到冲突时，为了保护和睦的人际关系，通常采取回避或是妥协的方式，而非积极的、正面的处理。',u'您的敏感，做事总是希望得到别人的鼓励和赞赏，担心被忽视，不愿接受批评，很可能变得沮丧和郁闷。',u'您总是容易陷入情感和细节中，很难从问题中跳出来更宏观、更客观的对待；取悦或帮助他人的您很忽视自己的需求，难以说出“不”，怕让别人失望。',u'您通常很难变通，拒绝尝试新方法，习惯根据经验做出决定，以至于信息不足造成决策的草率。建议尽量开放地接受外部变化，放慢决定的速度。'],'advantage':[u'有很大的精力和动力来完成任务、创造成果；',u'能够有效地和别人协作，并且和他人建立起友好和睦的人际关系；',u'处理事实和细节问题时，能够记住并利用各种事实，具有客观的态度和一定的天资才能；',u'善于培养和帮助他人；对于别人良好的行为举止能够给予赞扬，并使他们更加发扬光大；',u'果断坚决、稳重可靠，工作勤奋，富有效率，认真，忠诚；',u'能够维护组织一向的价值观念和工作原则；',u'善于组织，有灵活的组织技能和明确的工作道德；',u'信奉工作在一个传统、稳定的组织里有其自身的优点和长处；',u'有较强的责任意识；别人可以信任您去实现自己的诺言；',u'乐意遵循已制订的例行公事和工作程序；',u'通情达理，视角现实；',u'不论工作还是消遣时间，都愿意为团体尽自己的力量。'],'disadvantage':[u'不太愿意尝试、接受新的和未经考验的观点和想法；',u'没有得到表扬和欣赏的时候可能会变得失望、泄气，在意他人对自己的评价；',u'可能只关注眼前需要，而对长远利益重视不够；',u'较难适应新环境，在不同的工作任务之间来回切换有时会困难；',u'容易表现得过于敏感；逃避难堪的场合，不喜欢在紧张的气氛中工作；',u'不愿意长时间独自工作，更期待想要和别人在一起；',u'容易将个人的喜好表露出来；',u'可能由于情感方面的负担而疲惫不堪；',u'在掌握的信息和资料还不够的情况下，容易作决定过快，较少考虑其他的选择；',u'只关注具体的细节之处，而不能整体把握一个情况或者事物的长远影响；',u'容易固执已见、武断地做出决定；',u'一个人在延长的时间里工作时可能会变得焦躁不安，需要参加社交活动。'],'PositionMatch':[u'在友好的环境中工作，与他人充分合作并能协调一致，能够感受到大家的赞赏和支持，并乐意把同事当做朋友；',u'工作制度完善，内容要求明确且易于理解，能有固定的、清晰的评价标准；',u'工作成果能够给人们带来实际的帮助，能够运用您的细致和计划性；',u'能够让您组织安排并督促自己和他人的工作，以确保事情尽可能顺利、有效的进行；',u'能够与别人建立温暖、坦诚的关系，通过有形或无形的方式帮助他人提高生活质量；',u'做常规的项目或工作，有一定的控制权，不要有太强的压力和应变要求。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您喜欢那些经常有外出机会，果断和行动导向的企业文化；',u'您希望每天能与许多人接触，愿意积极的建立起广泛的社会关系网，建立起新的商业机会；',u'工作可以直接与客户打交道，如销售人员，商业拓展人员等；',u'自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化。',u'在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同。',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您不会从事风险极大的事情，您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您很喜欢那种能培养友好、合作和“温暖”工作氛围的企业文化；',u'办公室对您来说既是一个商业场合也是一个交朋友的地方；',u'您有很强的利他主义情感，并且期望大多数同事有着此种情感或价值观；',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化。那种崇尚内部竞争和敢闯敢干的企业肯定不是您成功的地方。']},'SuccessKey':[u'就事论事，不要随便地把批评和不同意见视为对自己的人身攻击；',u'经常考虑事情发展的可能性和潜在的变化因素；',u'不紧不慢的办事情，要学会等待最佳时机。'],'Proposal':[u'需要开放的对待新的观念和事物，注意倾听他人；',u'需要学会客观面对和处理冲突；',u'需要考虑决策制定的逻辑性以及对全局的影响；',u'目前不要考虑在压力大的环境中工作；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'牙医、宠物医生、护士、健康保健医师、运动生理医师、临床矫正医师等。',u'小学/幼儿教师、社会工作者、志愿者、法律顾问、野外探险领导员、法院职员等。',u'公关人员、销售、零售业/餐饮业、保险代理、人力资源/教育顾问、信贷顾问、口笔译人员、房地产估价师、客户关系经理等。 ',u'客户服务人员、美容/美发顾问、旅游专家、秘书、房地产代理人、会议筹办者等。'],'Reason': [u'许多和您特点一样的人对卫生保健方面的工作较为感兴趣，这样的工作可以让您通过自己的技能、操作直接地帮助他人。',u'您喜欢做对社会有价值的事情，如传授他人知识、为他人排忧解难，自愿的为建立、维护组织奉献自己时间和精力。',u'您有较为出色的人际交往能力，那些可以接触客户或顾客，并通过广泛的合作来维持友好关系、又关注细节的工作对您有较大的吸引力。',u'服务业可以发挥您关心照顾他人、主动处理问题、关注细节的特点，直接与他人打交道，提供服务使您感到轻松舒适。']}},
                'ESFP':{'content':u'表演者型','description':[u'您对人和新的经历都感兴趣，善于观察，看重眼前事物。',u'您更多地从做事的过程中学到东西，而不是研究或读书。您相信自己五感所感触到的信息，喜欢有形的东西，能够看到并接受事物的本来面目，是现实的观察者，并具有运用常识处理问题的实际能力。',u'您热爱生活，适应性强且随遇而安，爱热闹，爱玩耍，热情、友好，表现欲强烈，有魅力和说服力。',u'您喜欢意料之外的事情并给他人带来快乐和惊喜；您的饱满情绪和热情能够吸引了别人，灵活、随和，很好相处。通常很少事先做什么计划，自信能够遇事随机应变，当机立断。讨厌框框，讨厌老一套，总能设法避开这些东西。',u'您善于处理人际关系，经常扮演和事老的角色，圆滑得体，富有同情心，愿意以实际的方式帮助他人，通常可以让别人接受自己的建议，不喜欢将自己的意愿强加别人，是非常好的交谈者，天生受人欢迎。'],'blindness':[u'您对各种事情都好奇，以致于总是分心，工作受到干扰。做事容易拖拉，难以约束自己，显得不是那么尽职尽责。建议集中注意力，平衡工作和生活，努力把工作放在首位，借鉴一些成功的或已为人所接受的安排工作和控制时间的方法。',u'因为您积极活跃的个性，总是使您忙碌于具体的事务中，并无暇去制订计划，致使面临应急和变化时您会不知所措，您应该未雨绸缪，学会计划和预测事物的发展变化。',u'您经常忽视理论思考和逻辑分析，做决定时习惯于相信自己的感觉，或凭一时兴趣、冲动，有时不考虑结果。您对朋友的评价很高，并只看到他们积极的一面。您需要更进一步考虑事情的起因和结果，并学会拒绝。'],'advantage':[u'工作时精力充沛，并充满乐趣；',u'对迅速发生的改变和转变能良好适应；',u'对被人的需要敏感，渴望以真正的方法帮助他人；',u'是个有协作精神的团队队员；',u'具有使工作有趣、让人兴奋的能力；',u'务实但又有丰富的常识；',u'忠实于自己关心的人和组织；',u'有上进心，在工作中容易创造一个生机勃勃、充满乐趣的气氛；',u'具有一定柔韧性，并且愿意冒险，乐于尝试新事物；',u'渴望合作，并以真实准确的方法帮助他人；',u'能清楚地评估目前的资源和情况，并且能立刻看到应该做什么。'],'disadvantage':[u'难以独自工作，尤其是持续一段的工作，期待与他人合作；',u'不喜欢提前准备，在组织时间上存在不足；',u'难以看到目前不存在的机会和选择；',u'将失败当作针对个人的批评和负面回应的倾向；',u'难以快速做出决定；',u'冲动，且容易被诱惑或迷惑；',u'不喜欢过多的条条框框和官僚作风；',u'如果涉及到个人感情，就难以做出有逻辑的决定；',u'抵制确立长期目标，经常难以达到最后期限；',u'较难律己或律人；',u'斗志不足，容易松懈，通常不愿付出过多的努力；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'在轻松、友好的环境里工作，能和他人在一起积极的工作，工作具有一定的丰富性、乐趣性和自主性；',u'能够不断地从实际经验中学习，通过搜集的具体、细致的资料中，发挥自己灵活的判断力，寻找解决问题的方法；',u'能够促进大家的合作，充分动员他人的能力和热情，熟练处理人际关系和争执冲突，消除紧张气氛；',u'工作能让您体验到快乐和惊喜，能有自我发挥的空间，少受层级结构、规则和条条框框的限制；',u'可以直接和客户打交道，能深入参与和实践，而不愿意排除在外；',u'能够应对突发或处理紧迫的事情，并考虑周边人的需求。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您喜欢经常有外出机会，以及果断和行动导向的企业文化；',u'您希望每天能与许多人接触，愿意积极的建立起广泛的社会关系网，建立起新的商业机会；',u'工作可以直接与客户打交道，如销售人员，商业拓展人员等；',u'自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较低','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织；',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）；',u'工作中您更相信您的直觉，而不是精细的计划和安排；',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您不会从事风险极大的事情，您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您很喜欢那种能培养友好、合作和“温暖”工作氛围的企业文化；',u'办公室对您来说既是一个商业场合也是一个交朋友的地方。您有很强的利他主义情感，并且期望大多数同事有着此种情感或价值观；',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化。那种崇尚内部竞争和敢闯敢干的企业肯定不是您成功的地方。']},'SuccessKey':[u'考虑现实中潜在的发展性信息；',u'尽量理智客观的看待事情，不要太感性或凭一时兴致；',u'遵守时间约定，信守承诺。'],'Proposal':[u'在决定时需要照顾逻辑关系；',u'在管理项目之前需要事先计划；',u'需要平衡工作努力和社交活动；',u'需要在时间管理上下功夫；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'幼儿/小学教师、体育教练、社会工作者、健康/福利顾问、生物学者、内科/儿科医生、药剂师等。',u'旅游专业人员、演员、制片人、摄影/摄像师、节目主持人、画家、野外探险领导人、警察、漫画/卡通制作者等。',u'营销策划、销售、公共关系、融资者、零售商、仲裁人员、保险代理/经纪房地产经纪人。',u'秘书、警察、园艺设计师、地质学者、生物/动物学家、环境学者等。'],'Reason': [u'您充满活力、热诚，教育和社会工作给您提供了直接与别人工作、利用技术帮助别人的机会。',u'您喜欢和朋友在一起并娱乐他人，喜欢在不断变化的环境里，有审美感，所以一些演艺界、艺术领域的工作较为适合您。',u'您也应该考虑那些与他人可以高度互动、自由不刻板的工作，或是可以发挥您处理人际关系能力和收集信息能力的工作。',u'服务业吸引您的地方是可以发挥您热心、友好的特点，可以提供您与人交往和使用您的技能的机会。']}},
                'ESTJ':{'content':u'管家型','description':[u'您做事速度快，讲求效率，有责任感，善于自我约束，能够尽职尽责地完成工作。',u'您喜欢推进事情并掌控局势，敏锐，对细节有出色的记忆力，善于组织，能够系统化、结构化地通过有效的方式安排时间并达成目标。',u'您有计划、有条理、喜欢把事情安排的井井有条，按照计划和步骤行事。',u'您是一个有极强的逻辑性、非常喜欢做决定的人。您做事客观、善于分析，而且有很强的推理能力。通常根据自己的经验进行判断和决策，善于看到工作系统中不合逻辑，不协调和无效的部分，并做出积极改进。',u'您习惯从细节出发，关注现实，重视经验和感受。您关注实用价值，对于听到、看到、闻到、尝到、触摸到的“具体事物”更加感兴趣，而不是一些抽象的理念。您关注眼前，一般对于事情的远景和潜在价值难以关注到。',u'您性格外向，为人友好、直爽，处事讲求原则。通常是坚定的、可以信赖的伙伴。您喜欢传统，遵照规范办事，是原则和传统的良好维护者，您擅长判断人，严于律已，在人际关系上始终如一。'],'blindness':[u'您看问题具有很强的批判性，注意力更多关注存在的问题，通常不能对别人的贡献表示赞赏和肯定。您需要留意和发现别人的才能和努力，并适时给予鼓励和表扬。当提出批评时，多注意技巧。',u'您喜欢把自己的标准强加给别人，对自己和他人都要求严格，通常被周围的人看成“独裁者”。您需要学会更加通融、开放，不要过于固执。建议以更加开放的观念和发展的眼光，看待周围的新事物，对不同的人，不同的事更有耐心和包容性。',u'您遵照逻辑和客观的原则做事，较少考虑自己的行为和决定给他人带来的影响。建议您更加留心和尊重自己及他人的情绪和感受。',u'您专注于实施自己细致的计划，容易错过外界的很多变化和信息，甚至难以停下来听一听别人的意见，您忽视了许多发展的可能性及事物潜在的关联关系。您需要学会放慢节奏，倾听别人的建议，考虑所有的可能性，更好地检查其它可以利用的资源，增加做事的周全性。',u'如果您希望更好地适应社会，并获取成功，您需要尝试多角度地理解和处理问题，加强灵活性，不要事事控制，尝试转换思维方式，并且懂得和接受生活中有介于黑与白之间的灰色区域。'],'advantage':[u'注重实践、关心结果；',u'能强有力地承担自己的义务；必要的时候能够快刀斩乱麻、意志坚定；',u'务实，对既定目标坚韧不拔，能够自始至终地关注着公司（或组织）的目标；',u'办事精确、很少出差错，有要把工作做好的强烈愿望；',u'有很好地遵循已经建立起的工作安排和工作程序的习惯；',u'能够敏感地察觉出不合逻辑、不连贯、不现实以及不称职的人或事；',u'具备很好的组织能力；能很客观地做出决定；',u'相信传统模式的可取之处，并且能够遵循传统模式；',u'很强的责任心；别人可以信任您去实现自己的诺言；',u'追求工作的效率和成果；',u'在推销或谈判时有说服力，也较为坚定，有时甚至是坚韧不拔。'],'disadvantage':[u'对不遵守程序的人或对重要细节不重视的人可能会缺乏耐心；',u'不愿意尝试、接受新的和未经考验的观点和想法；',u'对变动感到不安，比较排斥革新；',u'不能忍受没有效率的工作，或需花很多时间才能完成的程序或工作；',u'只考虑眼前需要而较少关注长远利益，对当前不存在的可能性没有兴趣；',u'有为了实现自己的利益而无视别人的需要的趋向；',u'难以看到将来的可能性；',u'对于方针或决定将会对别人造成什么样的影响缺乏敏感；',u'当追求目标时总想凌驾于别人之上。'],'PositionMatch':[u'喜欢在稳定、讲究规范的环境中工作，要求有明确的前景和清晰的等级制度；',u'工作氛围友好，与勤奋有责任心的同事一起工作；',u'工作能够发挥您的逻辑、推理、计划、控制和组织能力；',u'工作任务要明确、具体、有可操作性和实际结果；',u'对您的工作，要有公平、合乎逻辑、明确、客观的衡量和评价标准；',u'遵循已有的程序，组织必要的资源，采取必要的措施，并控制事情的进度和最后期限；',u'工作允许您自己进行决策，并负责组织管理，能给您一定的控制权，让您承担较大的责任。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您喜欢那些经常有外出机会，果断和行动导向的企业文化。',u'您希望每天能与许多人接触，愿意积极的建立起广泛的社会关系网，建立起新的商业机会。',u'工作可以直接与客户打交道，如销售人员，商业拓展人员等。',u'自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化。',u'在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同。',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您不会从事风险极大的事情，您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力；',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系；',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'放慢决策和行动节奏；',u'多为别人着想，学会换位思考；',u'要能灵活变通，适当开放。'],'Proposal':[u'在决策前，需要考虑问题的各个方面，包括人的因素的影响；',u'需要督促自己仔细考虑变动所带来的得失；',u'需要作出特殊的努力以夸赞别人的成绩；　',u'适合的时候，主动承担一些工作对您的发展更有利。'],'SuitableJob':{'JobType': [u'营销（实物）、厨师、教师、政府职员、警察/侦察人员、健康/安全专家、保险代理、采购、法院工作人员、预算分析人员、估价人员等。',u'机械工程师、计算机分析人员、网络管理员、技术培训师、审计师、药剂师等。',u'项目经理、行政人员、工厂主管、数据库管理、财务、建筑、银行官员、信息总监、后勤与供应人员、业务运作顾问等。',u'牙医、内科医生、法官、股票经纪人、教师、律师、土木机械工程师、校长等。'],'Reason': [u'您喜欢在一个要求严格、遵循标准化的操作程序环境中工作，这些工作可以让您与现实的实物或切实的工程项目打交道。',u'您善于搜集、整理、分析和演绎推理具体的信息资料，所以那些能够充分发挥您技术分析方面和机械操作方面能力的工作也较为适合。',u'管理类的工作您会很喜欢，您可以发号施令、作决定，并且监督他人。统计发现很多这种特点的人在中层管理职位上做得较为出色。',u'专业工作领域对您的吸引力在于它使您在一个具体的、已建立完善、有光辉历程的机构里具有较高的威望。']}},
                'ESTP':{'content':u'企业家型','description':[u'您是敏锐的发现者，善于看出眼前的需要，并迅速做出反应来满足这种需要，天生爱揽事并寻求满意的解决办法。',u'您精力充沛，积极解决问题，很少被规则或标准程式框住。能够想出容易的办法去解决难办的事情，以此使自己的工作变得愉快。',u'您天生的乐天派，积极活跃，随遇而安，乐于享受今天。对提供新经验的任何事物、活动、食物、服饰、人等都感兴趣，只愿享受今天，享受现在。',u'您好奇心强，思路开扩，容易接受事物，倾向于通过逻辑分析和推理做出决定，不会感情用事。如果形势需要，您会表现出坚韧的意志力。偏爱灵活地处理实际情况，而不是根据计划办事。',u'您长于行动，而非言语，喜欢处理各种事情，喜欢探求新方法。您具有创造性和适应性，有发明的才智和谋略，能够有效地缓解紧张氛，并使矛盾双方重归于好。',u'您性格外向，友好而迷人，很受欢迎，并且能在大多数社会情况中很放松自如。'],'blindness':[u'由于您关注外界各种变化信息，喜欢处理紧急情况，不愿意制订规划去预防紧急情况的发生。',u'常常一次着手许多事情，超出自己的负荷，不能履行诺言，可能使周围的人陷入混乱。您需要试着找到一些能让自己按时完成任务的方法。',u'您的注意力完全集中在有趣的活动上，喜欢不断地接受新的挑战，不愿意在目前沉闷的工作中消磨时间，难以估计自己行为带来的结果。您需要为自己订立一个行为标准。',u'当情况环境转变时，您很容易忽视他人的情感，变得迟钝和鲁莽。'],'advantage':[u'敏锐的观察力，对实际讯息的出色记忆力；',u'明白该做什么，明白现实的对待完成工作的必要条件；',u'精力充沛，工作时充满活力；',u'具备随机应变的能力；',u'能够使工作有趣和兴奋；',u'享受参加团队工作的乐趣；',u'有实际、现实的观察力和丰富的常识；',u'您在工作中创造生动有趣的气氛；',u'适应力较强，愿意冒险和尝试新事物；',u'愿意接受不同和跟随潮流。'],'disadvantage':[u'不喜欢事先准备，在时间管理上存在一定困难；',u'对别人的感觉迟钝，或对别人的感觉过于疏忽；',u'无法看到眼前不存在的机会和选择；',u'缺乏耐心，无法忍受行政细节和手续；',u'很难作决定，或优先考虑计划；',u'易冲动，易受诱惑或迷惑；',u'较难以看到事情的长远影响；',u'不喜欢过多的规矩和条条框框的官僚作风；',u'抵抗制定长远目标，坚信计划赶不上变化；',u'斗志不足，容易松懈，通常不愿付出过多的努力；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'在一个没有太多规则约束的环境中工作，完成自己的任务后可以享受自由的时间；',u'工作可以发挥您“救火”的能力，利用直接的经验，寻找解决问题的最佳方案；',u'在工作中，接触真实的人和事务，进行有形产品的制造或服务，而不是理论和思想领域的；',u'工作充满挑战，允许您用冒险的方式处理紧急情况；',u'工作能发挥您敏锐的观察力、理解力以及对事实的记忆力；',u'工作能让您结识各种不同的人，并能与讲究实际、充满活力的同事坦诚相处。'],'SocialRequire':{'summary':u'您对组织的社会性要求高','detail':[u'您喜欢那些经常有外出机会，果断和行动导向的企业文化。',u'您希望每天能与许多人接触，愿意积极的建立起广泛的社会关系网，建立起新的商业机会。',u'工作可以直接与客户打交道，如销售人员，商业拓展人员等。',u'自信、有挑战性，发现或创造新的市场机会，有这样工作空间的环境适合您。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求不高','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织。',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）；',u'工作中您更相信您的直觉，而不是精细的计划和安排。',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您不会从事风险极大的事情，您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力；',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系；',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'全面审视现实情况，三思而后行；',u'考虑别人的情感；',u'分清事情的轻重缓急，作好计划，善始善终。'],'Proposal':[u'需要抑制独断而忽视他人感情的方面表现；',u'需要在迅速决定之前，事先计划，考虑细节，三思而行；',u'注意规划性，发展持之以恒；',u'需要关注物质享受以外的东西；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'警察、消防员、侦探、调查员、房地产经纪人、情报人员、稽查员、投资、保险经纪人、预算分析师等。',u'记者、旅游代理、摄像、主持人、演员、拍卖行业等。',u'承包商、厨师、电器工程师、电信网络专家、后勤和供给人员、财务主管、运动生理学者、教师、园艺设计、摄影师、野外探险领导人。 ',u'管理顾问、网络经销、汽车商人、特许经营、批发/零售商等。'],'Reason': [u'要求您在迅速改变的环境中快速思考/反应的服务领域可以满足您的好奇心和观察力。',u'您喜欢冒险，喜欢有一定刺激，所以某些娱乐性的工作会带给您职业满足。',u'您善于进行手工操作，这种操作可以带给您经济、技术的提高，且可以不断实践。',u'那些过多约束的环境不是您需要考虑的工作环境，通常自由、多样化，能够提供冒险机会的工作对您更有适应性。']}},
                'INFJ':{'content':u'博爱型','description':[u'您有计划、有条理，喜欢遵照固有的模式处理问题，乐于探求独特的方式以获得有意义的成长和发展。',u'您通过认同和赞扬与别人进行沟通，具有很强的说服力，您可以成为伟大的领导者。您的贡献被人尊敬和推崇。',u'您喜欢独处，性格复杂，有深度，是独立的思考者。您忠诚、有责任心，喜欢解决问题，通常在认真思考之后行动。您在同一时间内只专注一件事情。',u'您有敏锐的洞察力，相信灵感，努力寻求生活的意义和事件的内在联系。',u'您有坚定的原则，就算被别人怀疑，也相信自己的想法和决定，依靠坚韧不拔取得成功。',u'他人能随时体会到您的善良和体贴，但不太了解您，因为您总是做的含蓄和复杂。事实上您是非常重感情，忠于自我价值观，有强烈的愿望为大家做贡献，有时候您也很紧张和敏感，但表现的深藏不露；您倾向于拥有小范围的而深长久远的友谊。'],'blindness':[u'您的完美和固执，使您易走极端。一旦决定后，拒绝改变，并抵制那些与您的价值相冲突的想法，以至于变的没有远见。',u'您专注地追求一个理想，不会听取别人的客观意见，因为自己的地位是不容置疑的。',u'您总是探寻事情的意义和价值，过于专注各种想法，会显得不切实际，而且经常会忽视一些常规的细节。',u'您需要留意周围的情况，并学会运用已被证实的信息，这样可以帮助您更好地在现实世界中发挥您的创造性思维。',u'您敏感，非常关注个人的感受和他人的反应，对任何批评都很介意，甚至会视为人身攻击。对您来讲，您需要客观地认识自己和周围的人际关系，更好地促进事情向正面转化。'],'advantage':[u'诚实正直，从而鼓励着人们重视您的想法；',u'对于那些您认为很重要的项目专注且执着，对自己信仰的事业尽职尽责；',u'坚决果断，有说服力的领导，并有高度的组织能力；',u'有创造力，能提出独树一帜的解决问题的办法；',u'与别人感情交融，能预见别人的需要，对别人真正关心，愿意帮助别人成长和发展；',u'能透视看到事情发展的宏观图像以及意识与行动间未来的潜在联系；',u'有理解复杂概念的能力；',u'独立，有较强的个人信念；',u'有做出成绩、不达目的不罢休的干劲。'],'disadvantage':[u'不够灵活，思维单一，有时过分的专心致志，结果可能导致死板；',u'很难做与自己价值观相冲突的事；',u'做事过于讲究计划性，缺少弹性；',u'易于仓促下判断，且一旦做出决定不愿再回头过来审视一下，更不愿撤销决定；',u'不擅长处理矛盾；',u'很难拉下面子客观、直接地训诫下属；',u'交流方式可能太复杂，或很难把复杂的想法简明地表达出来，令他人不易理解；',u'斗志不足，容易松懈，通常不愿付出过多的努力；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'工作符合您的个人价值观和信念，能让您在人格上和职业上都保持诚实正直的品质；',u'工作环境友好、没有紧张的关系，您的努力能得到别人的精神支持，想法能得到重视；',u'工作最好能提供创立新颖的观点和方法的空间，有计划地解决工作中出现的各种问题；',u'最好能一对一的开展工作，实施自己的想法，为别人的提供帮助或服务，促进别人的成长和发展；',u'能够独立的工作，自由的表达自己，并自主安排自己的时间及环境，对自己的工作进程和工作成果有极大的支配权；',u'能让您提供一种您所信仰并且为之自豪的产品或服务。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。',u'您喜欢社会性要求不高的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网；',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化。',u'在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同。',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化；',u'您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋；',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有很大风险性的事情；',u'鼓励或奖励创新和新思想的企业文化更适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您喜欢那种能培养友好、合作和“温暖”工作氛围的企业文化；',u'办公室对您来说既是一个商业场合也是一个交朋友的地方。您有很强的利他主义情感，并且期望大多数同事有着此种情感或价值观；',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化。那种崇尚内部竞争和敢闯敢干的企业肯定不是您成功的地方。']},'SuccessKey':[u'注意事情的细节和现实情况；',u'开放、灵活一点；',u'理智、客观的看待周围的人和事。'],'Proposal':[u'培养坚决果断的风格，以便更有实效的促进事情的正面转化；',u'学会自我鼓励和激励；',u'和他人一起检讨自己，更客观对待自己的不足和进步；',u'需要放松，对于目前情况下能够完成的事情，应当报有更开放的态度；',u'目前不要考虑在压力大的环境中工作；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'社会工作者、文科类教师、职业治疗师',u'作家、媒体策划、室内/商品设计师、编辑/影片制作等。',u'人力资源人员、营销人员、策划人员、口译/笔译人员、项目经理。',u'企业组织发展顾问、企业培训人员、职业顾问、技术顾问等。 '],'Reason': [u'您喜欢运用自己的观点和知识帮助别人，喜欢学习，在咨询或帮助别人的时候自己也得到提高是您所追求的。',u'有艺术感或有美感的工作对您较有吸引力，您可以运用您的才能创造出独特的作品，同时把自己的观点和想象力融入其中，并且可以独立完成。',u'您对事情较有使命感，尽职尽责，因此愿意解决个体或社会问题，这类工作也是您需要考虑的。',u'在商业领域里，与人打交道解决以人为本的问题，营造有效的工作环境也是您所喜欢的。']}},
                'INFP':{'content':u'哲学家型','description':[u'您比较敏感，非常崇尚内心的平和，看重个人的价值，忠诚，并且理想化，一旦做出选择，就会约束自己完成。',u'您外表看起来沉默而冷静，但内心对他人的情感十分在意。您非常善良，有同情心，善解人意。',u'您重视与他人有深度、真实、共同进步的关系，希望参与有助于自己及他人的进步和内在发展的工作，欣赏那些能够理解您价值的人。',u'您有独创性、有个性，好奇心强，思路开阔，有容忍力。乐于探索事物的可能性，致力于自己的梦想和远见。',u'您很喜欢探索自己和他人的个性。一旦全身心地投入一项工作时，您往往发挥出冲刺式的干劲，全神贯注，全力以赴。您对人、事和思想信仰负责，一般能够忠实履行自己的义务。但是，对于意义不大的日常工作，您做起来可能有些困难。'],'blindness':[u'您追求完美，会花很长时间酝酿自己的想法，难以用适当的方式来表达自己。您需要更加注重行动。',u'您经常忽略逻辑思考和具体现实，沉浸于梦想。当意识到自己的理想与现实之间的差距，您就容易灰心丧气。您需要听取他人更实际的建议，考虑方法的现实性和可行性。',u'您非常固执，经常局限在自己的想法里，对外界的客观具体事物没有兴趣，甚至忙的不知道周围发生了什么事情。',u'您总是用高标准来要求自己，投入太多的感情，导致您对批评相当敏感。压力很大的时候，您可能会非常怀疑自己或他人的能力，而变得吹毛求疵，又爱瞎判断，对一切都有抵触情绪。'],'advantage':[u'对工作忠于职守；',u'考虑周到细致且能集中注意力深入某个问题或观点；',u'渴望打破常规思考，并考虑新的可能情况；',u'进行您所信仰的工作会使您们振奋鼓舞；',u'擅长独立工作，能与您尊敬的人保持频繁、有意义的支持性交流关系；',u'对收集所需信息有一种天生的好奇与技巧；',u'能统观全局以及看到意识与行为之间的联系；',u'能洞察别人的需要和动机；',u'适应能力强，能很快改变您的行事速度及目标；',u'能够理解他人，在一对一的基础上能极好地与人工作。'],'disadvantage':[u'必须控制方案或计划，否则您可能会失去兴趣；',u'有变得无秩序性的倾向，很难把握优先处理的事，计划性较弱；',u'不愿做与自己价值观相冲突的工作；',u'天生的理想主义，这样可能使您得不到现实的期望；',u'讨厌以传统的或惯常的方式行事；',u'较难在竞争的、气氛紧张的环境中工作下去；',u'在处理及完成重要细节问题上缺乏纪律或原则性；',u'在预计做某事要求多长时间时有不切实际的倾向；',u'不愿惩戒直接肇事者，不愿批评别人；',u'如果工作没有向您坚信的目标发展，您可能会垂头丧气；',u'可能较难灵活的对于您的想法进行必要的改变；',u'斗志不足，容易松懈,通常不愿付出过多的努力；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'在一个注重合作、没有压力和人际冲突的环境中，与其它富有创造性和同情心的同事一起工作；',u'在一个没有太多限制、灵活的机构中工作，有私人的工作空间和足够的时间；',u'工作能够符合个人的价值观，能够帮助他人成长和发展，挖掘他人的潜力；',u'工作允许您深入地与他人沟通和合作，理解、帮助、激励他人，并有机会接触到您尊敬的人；',u'在工作中，您可以发挥您的创造力，并能得到鼓励和嘉奖，自己的能力不断得到提升；',u'给您足够的时间，深化您的想法，并为实现它们而坚定地工作。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。您喜欢这样的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网。',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求不高','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织；',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）；',u'工作中您更相信您的直觉，而不是精细的计划和安排；',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化；',u'您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋；',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有较大风险性的事情；',u'鼓励或奖励创新和新思想的企业文化的企业更适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您很喜欢能培养友好、合作和“温暖”工作氛围的企业文化；',u'办公室对您来说既是一个商业场合也是一个交朋友的地方；',u'您有较强的利他主义情感，并且期望大多数同事有着此种情感或价值观；',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化；',u'崇尚内部竞争和敢闯敢干的企业不是您成功的地方。']},'SuccessKey':[u'客观地看待问题，注重理想和现实的结合；',u'注意思考的逻辑性和做事的计划性；',u'不要过于约束自己，保持进退尺度和节奏的把握。'],'Proposal':[u'增强做事计划性和条理性，以及持续推进工作的韧性；',u'重视客观事实和逻辑推理；',u'时刻需要考虑方法的现实性和可行性；',u'正视矛盾和冲突，学着说“不”；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'记者、娱乐业人士、建筑师、演员、编辑、室内设计师、制片人、艺术指导等。',u'顾问、心理学专家、社会工作者、人文/艺术教授、口笔译人员、职业顾问、医学顾问等。',u'营养学者、健康护理医师、整容医师等。',u'人力资源人员、人力资源顾问、企业培训师、项目经理等。'],'Reason': [u'您喜欢以独创的、个人的形式表达自己和观点，并且有自由与灵活的空间也是您对工作的要求。',u'教书与咨询这两个职业领域能使您有机会为别人工作，帮助他们成长，发挥他们的潜能。',u'您愿意与客户（病人）接近亲密的工作，且保持工作上的自主性。',u'您喜欢与人合作，喜欢设计和创新，让人感觉到您的付出既重要又独特。']}},
                'INTJ':{'content':u'专家型','description':[u'您考虑问题理智、清晰、简洁，不受他人影响，客观地批判一切，运用高度理性的思维做出判断，不以情感为依据。用批判的眼光审视一切，如果形势需要，会非常坚强和果断。',u'您不屈从于权威，并且很聪明，有判断力，对自己要求严格，近乎完美，甚至也这样去要求别人，尤其讨厌那些不知所措、混乱和低效率的人。',u'您有很强的自制力，以自己的方式做事，不会被别人的冷遇和批评干扰，是所有性格中最独立的。',u'您是优秀的策略家和富有远见的规划者，高度重视知识，能够很快将获取的信息进行系统整合，把情况的有利与不利方面看的很清楚。',u'您具有独特的、创造性的观点，喜欢来自多方面的挑战。在您感兴趣的领域里，会投入令人难以置信的精力、专心和动力。'],'blindness':[u'您只注重自己，很少去理解他人，自以为是，对他人没有耐心，总是想当然地把自己的观点强加给别人，制定不切实际的高标准。您需要学会去了解别人的感受和想法，以避免您冒犯他人。',u'您过于注重远见卓识，很容易忽略和错过与自己理论模式不符的细节和现象。您爱玩弄智力游戏，说些对他人没有意义、似是而非的话语。您需要简化您既理论又复杂的想法，更好地与别人交流。',u'您过分独立的个性和工作习惯，使得您总是“拒绝”别人的参与和帮助，难以发现自己计划中的缺陷。建议您保持耐心，多向他人请教，这样可以帮助您提早了解一些不合实际的想法，或者在大量投入之前做出必要的修正和改进。',u'您有时会过于固执和死板，沉迷于一些出色的但不重要的想法中，并且事事要求完美；如果您想成功，您需要判断事情的重要性，学习接受生活并与他相处，学会放弃。'],'advantage':[u'能看到事情的可能发展情况及其潜在含义；',u'能够理解复杂而困难的事务，喜欢复杂理论及智力上的挑战；',u'富于想象，善于创造体系，有创造性解决问题的能力，能客观地审查问题；',u'即使在面对阻挠时也会义无返顾地去实现目标；',u'自信且对自己的设想会不顾一切地采取行动去实行；',u'对于在工作中胜任和胜出有强烈的动机；',u'能很好适应一个人单独工作、独立、自主；',u'标准高、工作原则性强；',u'能创造方法体系和模式来达到您的目标；',u'擅长于从事技术性工作；',u'擅长理论和技术分析以及逻辑的解决问题；',u'坚决果断，有高度的组织能力。'],'disadvantage':[u'完成创造性的问题解决之后可能会对项目丧失兴趣；',u'易于像紧逼自己工作一样去逼着别人工作；',u'对那些反应不如您敏捷的人缺乏耐心；',u'可能和那些他们认为能力不如自己的人不太容易共同工作；',u'唐突、不机智、缺乏交际手段，尤其在您匆忙时；',u'对一些世俗的小事没有兴趣；',u'对自己的观点顽固地坚持；',u'具有一定想要去改善那些根本没有必要改善事物的倾向；',u'不愿花时间适当地欣赏、夸奖雇员、同事和别人；',u'对既定的问题不愿再审查；',u'易于过份强调工作，从而损害了家庭的和谐；',u'对一些工作所要的“社会细节”没有耐心；',u'可能会因太过于独立而不能适应合作的环境。'],'PositionMatch':[u'在运行顺利和谐、对人际没有过多要求的环境中，独立的开展工作，最好能够和聪明或有能力的人进行交流；',u'工作有高度的自主和控制力，权力不断增加，可以通过自己的努力，改变或推进事情的进展；',u'能够发挥您的独创性，提出解决问题的独到办法，并控制它们的执行，从而促进体系或制度的完善；',u'可以致力于实现您的美好想法，以合乎逻辑而且有序的方式进行工作，并能对您的坚持不懈进行嘉奖；',u'工作不要求反复执行那些实际的、常规的和以细节为核心的任务；',u'工作可以让您不断地追求高标准、高质量，采用新方法，从而提升您的能力和权威，并得到公平的回报。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。您喜欢这样的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网；',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求不高','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织。',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）；',u'工作中您更相信您的直觉，而不是精细的计划和安排；',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化。您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋。',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有较大风险性的事情；',u'鼓励或奖励创新和新思想的企业文化更适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力；',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系；',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'建立良好人际关系，听取他人的不同意见，认同别人的价值；',u'将完美的想法与实际相结合，充分考虑事情的可行性；',u'放弃一些控制，更多平衡您的工作和个人生活。'],'Proposal':[u'需要积极的听取他人的反馈和建议，学会欣赏他人；',u'需要更加现实，学会放弃那些不实际的想法；',u'需要重视自己的决策给他人带来的影响；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'电信顾问、管理顾问、经济学者、策划、金融分析者、预算分析家、资产鉴定人员等。',u'科学家/研究员、电脑系统分析员/程序员/工程师、技术人员、设计工程师软件开发、网页设计、网络主管、生物医学人员、商业分析员等。',u'教师、行政管理人员、数学家、心理学者、外科医生、生物医学研究人员等。',u'律师、法官、新闻分析家/撰稿人、建筑师、投资/商业分析家、飞行员、侦察/情报专家等。'],'Reason': [u'商业和金融领域的职业都要求有高度发展的分析能力，这些正是您在工作中追求的。',u'您喜欢运用创造力来开发奇特的方法体系，这些技术领域的逻辑体系，不断发展的高技术设备和产品打交道机会对您也较为合适。',u'高等教育和医学领域的高度复杂体系，在工作的同时自己也得到提高是您在工作中追求的。',u'能够独立的研究与策划，注重长远计划开发的职业也是在您考虑范围之内。']}},
                'INTP':{'content':u'学者型','description':[u'您极其聪慧，有逻辑性，善于处理概念性的问题，且有很强的创造灵感，对发现可能性更感兴趣。',u'您非常独立，有批判性和怀疑精神，深藏不露，内心通常在投入地思考问题，总是试图找运用理论分析各种问题；对一个观点或形势能做出超乎超于常人的、独立准确的分析，会提出尖锐的问题，也会向自己挑战以发现新的合乎逻辑的方法。',u'您擅长用极端复杂的方式思考问题，看重自己的才学，也喜欢向别人挑战；您更善于处理概念和想法，而不是与人打交道。喜欢有逻辑性的和目的性的交谈，但有时想法过于复杂以至于难与别人交流和让别人理解，也会只是为了高兴而就一点儿小事儿争论不休。',u'您能宽容很多不同的行为，只是在自己认为应该的时候才争论和提出问题，但是如果您的基本原则受到挑战，您就不在保持灵活性而以原则办事。',u'您是天才而有创意的思考者，喜欢投机和富于想像力的活动，对找到创造性解决问题的办法更感兴趣，而不是看到这些办法真正奏。'],'blindness':[u'如果您没有机会运用自己的才能，或得不到赏识，会感到沮丧，爱打嘴仗，好争论，冷嘲热讽，消极的批判一切。',u'您过于注重逻辑分析，只要不合逻辑，就算对您再重要，也很有可能放弃它。',u'您过分理智，忽视情感和现实，察觉不到他人的需要，也不考虑自己的观点对他人的影响，以“不符合”逻辑为由，主观断定某些自己或他人看重的东西的是不重要的，不够实际。',u'当您把自己批判的思维用在人的身上时，您的直率会变成无心的伤害。您需要找到自己真正在乎的事，这将帮助您们更真实地对待自己的情感。',u'您对解决问题非常着迷，极善于发现想法中的缺陷，却很难把它们表达出来，您对常规的细节没有耐心，如果事情需要太多的琐碎细节，您会失去兴趣，也会因计划中很小的缺陷而陷入困境，您绝不容忍任何一点不合逻辑。'],'advantage':[u'急切地“想知道盒子外面的世界”，能想出一些新的可能性；',u'能够理解复杂和高度抽象的概念；',u'杰出的创造性地解决问题的技能，具有探险精神、创造意识以及克服困难的勇气；',u'独立自主，能以个人工作，并且全神贯注；',u'能够综合考虑和运用大量的信息；',u'搜集所需用信息时理智的好奇心、独特的洞悉力；',u'即使在压力很大的情况下也能逻辑地分析事物；',u'喜欢能够学到新知识、掌握新技能的环境，学习新知识的信心和动力都很大；',u'客观性；能够客观地分析和处理问题，而不时感情用事；',u'对自己的想法和观点充满信心；',u'能够有远见的分析问题，能够把握事情的全局，弄清行为和思想的长远影响；',u'能灵活地适应新情况，有熟练的随机应变的能力。'],'disadvantage':[u'办事情可能条理不够清晰，容易发生紊乱；',u'有时过于自信，可能会不恰当地运用自己的能力和社会经历；',u'对思维狭窄和思想固执的缺乏耐心；',u'不喜欢按传统的、公式化的方式来办事；',u'做事容易丧失兴趣，主要问题一旦解决，兴趣便不复存在，不能实施并贯彻到底；',u'不擅长于把复杂的思想和问题用简明的形式表现出来，并用简单的形式将其解决；',u'可能过于理论化，而忽视或无视现实性，某些观点的实施不现实；',u'不能严格要求自己考虑且解决重要的细节性问题；',u'不喜欢重复地做同一件事，对琐碎的日常工作缺乏耐心；',u'对程式化的事情和固执的人缺乏耐心；',u'思想、观点对别人来说过于复杂、难以理解；',u'对别人的情感、批评和要求反映迟钝，人际不够敏感；',u'斗志不足，容易松懈，通常不愿付出过多的努力；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'工作可以去挑战复杂的问题，可以尝试一些别出心裁的方法，并为找到更好的结果去冒险；',u'工作可以不断提高自己的能力和权力，与那些有才华的人们一起工作；',u'让您把精力投入到有创造性的、富于理论逻辑的过程，而不是最后的结果；',u'不需要花时间组织或管理其他人，较少需要处理人际关系；',u'工作环境灵活宽松，没有过多的限制、规则和烦琐的会议；',u'独立工作，有大量的不受打扰的时间，有较多需要深入思考的事情。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。您喜欢这样的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网；',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求不高','detail':[u'您更喜欢结构松散、不是要求很高精确度和不强调细节的组织；',u'您喜欢自己设定目标和工作的完成期限，并且有权力决定自己的工作方式（例如自我设定工作时间表）；',u'工作中您更相信您的直觉，而不是精细的计划和安排；',u'以人为本，互动性强和高度自主的文化对您都很合适。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求高','detail':[u'您适合开放、创新的企业文化。您喜欢挑战、变化，愿意接受新观点，创新会让您觉得兴奋。',u'您喜欢不断尝试新的方法，崇尚与众不同；',u'您喜欢从事有较大风险性的事情；',u'鼓励或奖励创新和新思想的企业文化更适合您。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力；',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系；',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'更加有条理，尝试坚持计划；',u'对他人要有耐心；',u'体会他人感受和反应，增进自己的人际交往。'],'Proposal':[u'增强自己的执行力，将观念落实，关注现实和细节；',u'简单清楚的表达自己的想法，不要将简单的事情想复杂；',u'学会赞赏和鼓励他人；',u'更多的去体会自己和他人的情绪感受，学会理解别人；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'软件设计师、网络管理员、电脑工程师、系统分析人员、研究开发专业人员战略策划、金融规划师、电脑漫画设计者、分析人员等。',u'物理学家、美容师、药剂师、兽医、生物学家等。 ',u'律师、经济学者、心理学者、建筑师、金融分析者、商业分析、情报专家、口笔译人员等。',u'摄影师、作家、艺术家、发明家、天文工作者、制片人、音乐组织者、美编等。 '],'Reason': [u'大多数象您这样特点的人喜欢在技术领域工作，运用自己独特的能力来分析复杂的系统，形成富有创意的解决方案。',u'医学和科技领域能够充分发挥您出色的推断能力，站在行业的前沿与复杂高深的概念打交道，并带有一定的风险性也是您在工作中要求的。',u'您具有清晰的、逻辑性较强的思维和创造才能，在那些用这些方式来解决问题的专业和商业性领域工作对您也很有吸引力。',u'那些给您提供可创造出完全新奇的东西的领域，那些可以经历许多不同事情的领域也在您考虑范围。']}},
                'ISFJ':{'content':u'照顾者型','description':[u'您具有友善、负责、认真、忠于职守的特点，只要您认为应该做的事，不管有多少麻烦都要去做，但却厌烦去做您认为毫无意义的事情。',u'您务实、实事求是，追求具体和明确的事情，喜欢做实际的考虑。善于单独思考、收集和考察丰富的外在信息。不喜欢逻辑的思考和理论的应用，拥有对细节很强的记忆力，诸如声音的音色或面部表情。',u'您与人交往时较为敏感，谦逊而少言、善良、有同情心，喜欢关心他人并提供实际的帮助，您们对朋友忠实友好，有奉献精神。虽然在很多情况下您有很强烈的反应，但通常不愿意将个人情感表现出来。',u'您做事有很强的原则性，尊重约定，维护传统。工作时严谨而有条理，愿意承担责任，您依据明晰的评估和收集的信息来做决定，充分发挥自己客观的判断和敏锐的洞察力。'],'blindness':[u'您有高度的责任心，会陷入日常事务的细节中去，以至于没完没了的工作。每件事情您都会从头做到尾，这总是让您过度劳累，压力很大时，您会过度紧张，甚至产生消极情绪。',u'由于您的现实、细致，有时容易忽略事情的全局和发展变化趋势，难以预见存在的可能性。建议您周到考虑解决问题的不同方法和可能性，需要增强对远景的关注。',u'您总是替别人着想，以至于让人感觉“关心过度”，您需要学会给别人空间。在工作中，您过多的承受和忍耐，不太习惯表达，却将情绪在家庭和生活中发泄出来。',u'您不停地制订计划并保证完成，以致于经常花费更多的时间和投入更多的精力来完成工作，建议您给自己安排必要的娱乐和放松的活动，不要总是“低头拉车”，需要考虑“抬头看路”。'],'advantage':[u'能够很好地集中精力、关注焦点；',u'强烈的工作热情，认真负责，工作努力；',u'良好的协作技巧，能和别人建立起和谐友好的关系；',u'讲求实效的工作态度，办事方法现实可行；',u'十分关注细节，能够准确地把握事实；',u'乐于助人，乐意给同事和下属职员的工作提供实际的支持和帮助；',u'了解公司（或组织）的经历，能够很好地维护公司（或组织）的传统；',u'具有出色的组织才能；',u'愿意在传统的机构中工作，而且兢兢业业、不遗余力；',u'能够连续地工作，对相同的工作任务不会感到厌倦；',u'有较强的责任意识，别人可以信任兑现自己的诺言；',u'喜欢运用固定的办事程序；',u'尊重别人的地位和能力；',u'能情达理，看问题现实。'],'disadvantage':[u'可能会低估自己的能力，难于坚决地维护自己的需要和利益；',u'不愿意尝试、接受新的或未经验证的观点和想法；',u'对反对意见过于敏感；',u'在紧张的工作环境里容易感到压抑感；',u'可能只关注细节和眼前之事，而对整体和将来重视不够，或看不见将来后果的征兆；',u'难以适应新境况，或者在不同的工作任务之间来回切换时会有困难；',u'易于被需要同时解决的太多工作项目或任务弄得晕头转向、无所适从；',u'如果自己得不到充分的重视和赞赏，可能会感到灰心丧气；',u'不太愿意为坚持自己的想法和立场而冒风险打破与他人的协调关系；',u'一经做出决定，就不愿意从头考虑同一个问题；',u'对突然的变化较难适应；',u'在压力和挫折面前不够坚持。'],'PositionMatch':[u'在规范、传统、稳定的环境下工作，可以给他人提供服务或帮助；',u'适合在责任清晰，有一定私人空间、人际关系和谐的氛围中工作；',u'要求细致、精确，能够发挥您出色的观察力和对细节的关注能力；',u'工作能够让您集中精力，关注一件事情或一个人，而不是平行开展多项工作；',u'通过工作，您能够得到同事和上级的认可、欣赏和鼓励；',u'按照标准化的工作流程和规范开展工作，不要在事先没有准备的情况下把您的工作展示给别人。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。您喜欢这样的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网；',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化；',u'在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同；',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您不会从事风险极大的事情，您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您很喜欢能培养友好、合作和“温暖”工作氛围的企业文化；',u'办公室对您来说既是一个商业场合也是一个交朋友的地方；',u'您有较强的利他主义情感，并且期望大多数同事有着此种情感或价值观；',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化；',u'崇尚内部竞争和敢闯敢干的企业不是您成功的地方。']},'SuccessKey':[u'直接地表达自己，说出您现在的感受；',u'不要只顾低头拉车，需要抬头看路；',u'调整节奏、放松自己、适当松弛一下绷紧的弦。'],'Proposal':[u'做长远思考，加强对全局和可能性的关注，避免陷入具体事物而忽略了方向；',u'尽量直接了当地表达，避免绕弯；',u'尽量客观面对压力，更加积极；',u'需要以更加开放的的态度对待他人不同的做事方式；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'营养学者、外科医生、宠物医生、牙医、生物/植物学者、护士、矫形师等。',u'幼儿/小学教师、社会工作者、健康保健人员、指导顾问、历史学者、运动培训师、园艺人员等。 ',u'秘书、行政/人事管理人员、电脑维护者、信贷顾问、顾客服务等。',u'艺术人员、室内设计师、商品规划师、营销、房地产代理或经纪人、酒店管理人员等。 '],'Reason': [u'您喜欢通过具体的方法亲自、单独的与他人打交道，运用技术给他们带来直接的影响。',u'教育和研究类的工作特别受到和您特点相同的人的青睐，您们可以自主的工作，可以帮助别人，并能看到成果，可以为社会做出贡献。',u'直接和他人单独打交道的工作要求您具有较广的知识面、技能和交际，满足您给别人提供支持的偏好。',u'那些对工作细节非常关注，满足客户要求，与他们友好相处的实实在在的工作也是您需要考虑的。']}},
                'ISFP':{'content':u'艺术家型','description':[u'您和蔼、友善、敏感，谦虚地看待自己的能力。您能平静愉悦地享受目前的生活，喜欢体验。珍视自由自在地安排自己的活动，有自己的空间，支配自己的时间。',u'您善于观察、务实、讲求实际，了解现实和周围的人，并且能够灵活地对他们的情况和需要做出反应，但很少寻求其动机和含义。',u'您是优秀的短期规划者，能够全身心地投到此时此刻的工作中，喜欢享受现今的经验而不是迅速冲往下一个挑战。',u'您有耐心，易通融，很好相处。您没有领导别人的愿望，往往是忠实的跟随者和很好的合作伙伴。',u'您很客观，而且能以一种实事求是的态度接受他人的行为，但您需要基本的信任和理解，需要和睦的人际关系，而且对矛盾和异议很敏感。',u'您很有艺术天份，对自然的美丽情有独钟，对直接从经验中和感觉中得到的信息非常感兴趣，喜欢为自己创造一种幽雅而个性化的环境，您希望为社会的福利和人类的幸福做些贡献。',u'您内心深沉，其实很热情，不太喜欢表现。'],'blindness':[u'您完全着眼于现在，从不喜欢寻找和发现那些您认为不存在的可能性,这使您无法发现更广阔的前景,也不能为将来做打算,不能很好地安排时间和精力。',u'您天生对他人具有高度的敏感,总是难以拒绝别人，有时为了满足他人的需求而拼命地工作，以至于在此过程中忽视了自己。',u'您过分忽视事物之间的内在联系和逻辑思考,难以理解复杂的事情。',u'您对他人的批评会感到生气或气馁，有时容易过分自责。您容易相信别人，很少对别人的动机有所怀疑，也不会发现别人行为背后的隐含意义。',u'您需要更注重自己的需求，而且要对别人的行为加以分析。在分析中加入一些客观和怀疑的态度会让您们更准确地判断人的性格。'],'advantage':[u'热情、慷慨，对您很关心的人和组织忠诚；',u'注意重要的细节，尤其那些有关他人的细节；',u'主动愿意支持组织的目标；',u'准确评估目前形势的能力和看出什么是最需要保持稳定的能力；',u'会仔细评估冒风险和试用新方法时的灵活性和主动性。'],'disadvantage':[u'有因过于关注事物的表现而忽略事物内在联系的倾向；',u'较难能够观察到目前不存在的机会和可选择的机会；',u'不愿提早准备，在利用自己的时间上存在一定问题；',u'存在一定决断的困难；',u'不喜欢过多的规则，不喜欢结构过于复杂的机构；',u'在与自己的感受相矛盾时很难做出符合逻辑的决定；',u'不愿意为坚持自己的想法和立场而冒风险打破与他人的协调关系；',u'会被大量的极其复杂的任务压的喘不过气来的趋势；',u'反对制定长期的目标，较难按时完成任务；',u'不会很自觉的做直接的报告或批评他人；',u'斗志不足，容易松懈,通常不愿付出过多的努力。'],'PositionMatch':[u'在活跃的、合作的环境下工作，最小限度的人际冲突；',u'作为对集体忠诚和乐于合作的一员，在彼此积极支持的气氛下工作；',u'工作要求关注细节，切实且能够快速处理问题，提供实际帮助；',u'有独立工作的自由，周围的人最好和谐有礼貌，工作中没有太多的规则和僵化的程序；',u'符合您的内在价值观和审美情趣的工作；',u'工作不要求例行公事的公开讲话，或总是拒绝别人。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。您喜欢这样的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网；',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化。',u'在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同。',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您不会从事风险极大的事情，您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求高','detail':[u'您很喜欢能培养友好、合作和“温暖”工作氛围的企业文化；',u'办公室对您来说既是一个商业场合也是一个交朋友的地方；',u'您有较强的利他主义情感，并且期望大多数同事有着此种情感或价值观；',u'您倾向于没有冲突和争论，并鼓励相互尊重、支持的企业文化；',u'崇尚内部竞争和敢闯敢干的企业不是您成功的地方。']},'SuccessKey':[u'学会更好的沟通，表达自己的内心的真实感受和观点；',u'在一定高度下考虑问题，发展您的前瞻性；',u'客观公正，不要太个人化的看待事物。'],'Proposal':[u'需要学会怀疑和挑战他人的观点，深入分析外界信息，而不是一味接受；',u'学会规划和计划，更多考虑长远发展的前景；',u'需要更果敢和更直接地对待他人，学会说“不”；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'尽量思考成熟后再采取行动，碰到困难时，您需要坚持。'],'SuitableJob':{'JobType': [u'室内／风景设计师、宝石设计师、画家、演员、服装设计师、乐器制造、漫画/卡通制作、厨师等。 ',u'牙医、药剂师、外科医生、营养学者、康复专家等。',u'植物/动物/生物学者、地质/考古学者、摄像师、计算机操作员、系统分析师、检查员等。',u'文科教师、警察、美容专家、策划、翻译人员、社会工作人员、客户销售代表、工程师、娱乐工作者、消防员、野外探险领导者、保险鉴定人等。'],'Reason': [u'您喜欢那些可以通过双手创造出美丽、吸引人同时又有用的东西的职业，并且这些职业可以给您提供灵活自由的空间。',u'医疗保健事业可以给许多像您这样特点的人带来成就感，在那里您可以直接接触到病人，做细致的观察，迅速及时的解决问题，给他们提供身体和精神上的帮助。',u'您做事灵巧、细致，那些户外的、可以接触实事、变化丰富的工作也是在您考虑的范围内。',u'在服务性行业中，通过具体的、切实的方式帮助他人、关心他人，是您体现价值观的方式。']}},
                'ISTJ':{'content':u'u检查员型','description':[u'您是一个认真而严谨的人，勤奋而负有责任感，认准的事情很少会改变或气馁，做事深思熟虑，信守承诺并值得信赖。',u'您依靠理智的思考来做决定，总是采取客观、合乎逻辑的步骤，不会感情用事，甚至在遇到危机时都能够表现得平静。',u'您谨慎而传统，重视稳定性、合理性；您天生独立，需要把大量的精力倾注到工作中，并希望其它人也是如此，善于聆听并喜欢将事情清晰而条理的安排好。',u'您喜欢先充分收集各种信息，然后根据信息去综合考虑实际的解决方法，而不是运用理论去解决。',u'您对细节非常敏感，有很实际的判断力，决定时能够运用精确的证据和过去的经验来支持自己的观点，并且非常系统有条不紊，对那些不这样做的人没有耐心。'],'blindness':[u'您非常固执，一旦决定的事情，会对其他的观点置之不理，并经常沉浸于具体的细节和日常的操作中。',u'您看问题有很强的批判性，通常持怀疑态度，您需要时常的换位思考，更广泛的收集信息，并理智的评估自己的行为带来的可能后果。',u'您非常独立，我行我素，不能理解不合逻辑的事情，忽视他人的情感，并对与您风格不同的人不能理解，非常挑剔；您要学会欣赏他人的优点并及时表达出来。',u'您非常有主见，时常会将自己的观点和标准强加给别人，而且无视那些不自信的人的建议。在处理问题时，强求别人按照自己的想法来做，对于未经检验或非常规的方法不加考虑。若能在以后多尝试和接受新颖的、有创造性的方法，您就能做出更有效的决策。'],'advantage':[u'办事精确，希望第一次就能把工作做好；',u'乐意遵循确定的日常安排和传统的方针政策，是组织忠诚的维护者、支持；',u'每次都能十分专注地把注意力集中在一个项目或任务上；',u'能够专心细致的工作，可以不需要别人的合作独立工作；',u'具有较灵敏的组织能力；',u'一丝不苟、认真专注地对待具体问题；',u'视角现实，关注事实和细节；',u'相信传统模式的可取之处，并且能够遵循传统模式；',u'拥有较强的责任意识，别人可以信任您兑现自己的诺言；',u'对工作有高要求，认为高效率和多成果是重要的；',u'可以依靠，能够将工作自始至终贯彻到底，对实现目标有毅力和决心。'],'disadvantage':[u'不愿意尝试、接受新的或未经验证的观点和想法；',u'排斥革新，容易对变化感到不安，可能会有些僵硬、死板；',u'对需要很长时间才能完成的任务缺乏耐心；',u'有时会因过于关注近期目标而忽略长远需要的考虑；',u'适应力较弱，有时难以或不愿适应新环境；',u'较难以看到问题的整体以及行为的长远影响；',u'对于方针或决定将会对别人造成什么样的影响缺乏敏感；',u'有时不太愿意改变努力的方向或调整投入的多少；',u'不愿意促成必要的改变，不愿意支持有风险的行为；',u'见到实际应用后的结果才肯接受新观点；',u'对自己及自己对组织的贡献估计过低。'],'PositionMatch':[u'工作环境稳定，不需要太多的冒险和变动，最好依照经验和规律解决问题；',u'有较多的独立工作时间，可以专心的完成整个项目或任务；',u'较多使用事实、细节和运用实际经验的技术性工作，能够充分发挥自己精细、准确、逻辑性强的才能；',u'工作对象是具体的产品或服务，工作成果要有形并且可以衡量；',u'要有明确的工作目标和清晰的组织结构层次；',u'逐渐增加工作中的责任，承担更多的任务，尽可能少的安排社会活动；',u'工作有足够的准备和实施时间，在交付成果之前能够进行自我成就评估。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。您喜欢这样的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网；',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化。',u'在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同。',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您不会从事风险极大的事情，您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力；',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系；',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'要保持开放的心态，敢于尝试探索新的可能性；',u'考虑问题要更全面周到，更多考虑人的因素；',u'增强做事的灵活性，学会变通的看待和接受新事物。'],'Proposal':[u'避免墨守陈规，需要尝试新的东西；',u'需要考虑人的因素，提升人际敏感度；',u'除了眼前的现实资源，需要关注事情的整体和发展；',u'对那些与您想法不同的观点保持足够的耐心和虚心；',u'适合的时候，主动承担一些工作对您的发展更有利。'],'SuitableJob':{'JobType': [u'审计师、会计、质检员、文字信息处理专家、后勤/供应人员、信息顾问、精算师、统计员、作家、代理商、建筑检查/监理、保险调查员等。',u'警官/侦探、军官、公司人力行政人员、政府职员、飞机驾驶员等。',u'证券/股票分析人员、预算分析家、成本/房地产评估者、图书管理员等。',u'法律研究者、地质/气象学家、技术人员、技工/电工、网络编辑、系统分析员、外科医生、牙医、兽医、护理人员等。 '],'Reason': [u'大多数和您一样特点的人更偏好在传统的商业领域工作，您们讲求效率，在管理一个体系和保持事务正常运转方面表现的非常突出。',u'文职类工作较为吸引您，这样的环境细致、有条理，您可以维护服务、保护人们的工作制度或机构。',u'对于数据和细节较为细心、有耐心，能够快速、有效、独立的工作，处理大量数据和信息。',u'您特别善于发现事务细节方面出现的问题，所以您对那些技术、设计、生产精确度要求非常高的工作感兴趣。']}},
                'ISTP':{'content':u'冒险家型','description':[u'您密切关注周围发生的事情，常常充当解决困难的人。一旦需要，会快速反应，抓住问题的核心以最有实效的方式予以解决。您好奇心强，对事实敏感，能很好的利用手头的资源。',u'您善于思考和分析，关注事情是什么，及可以解决什么具体问题，不关注理论。您喜欢客观独立地作决定，并把一切都清楚直接地安排妥当。您对技术工作很有天赋，是使用工具和双手工作的专家。',u'您非常独立，不愿受规则约束，以独有的好奇心和富有创意的幽默观察和分析生活。具备很好的迎接挑战和处理问题的能力，天性喜欢兴奋和行动，通常很喜欢户外活动和运动。',u'您通常是安静或沉默的，喜欢行动而非言语，看上去比较“酷”，时常被认为不太愿意接近人。'],'blindness':[u'您非常实际，总能找到简捷的解决办法，这使您有时会偷工减料，不能完成所有的步骤和细节。您过分的关注眼下的结果，以至忽略了自己的决策和行动的长远影响。建议您学会做计划并坚持完成，以克服自己主动性弱的特点。',u'您总是独立分析，独自判断，不喜欢与别人分享自己的反应、情感和担忧，也不愿意把具体的情况甚至是最重要的部分与他人进行交流，使得周围的人行动或配合起来比较被动。',u'您非常喜欢多样化和新奇刺激，对所有的选择都持开放态度，所以您不善于做决定。您需要认真给自己一些约束，避免总是变动和无规律所带来的危害。',u'您通常无视自己的情感和需要，忽视他的人感受，对于自己的决定对他人产生的影响不够重视。'],'advantage':[u'有敏锐的观察力和较强的对事实信息的记忆力；',u'有将混乱的数据和可辨认的事实有序排列的能力；',u'喜欢独立工作或与您敬佩的人并肩工作；',u'在压力之下面对危机能保持头脑冷静；',u'知道完成工作需要做什么和必须做什么；',u'对突然变化和迅速发生的转变适应良好；',u'对新鲜事物有较强的开放度，愿意冒险以及尝试新事物。'],'disadvantage':[u'较难以看到行动的深远影响；',u'不喜欢事先准备，您在组织时间上存在有一定困难；',u'对抽象、复杂的理论缺乏耐心；',u'在人际交往上反应较为迟钝；',u'有容易变得厌烦和焦躁的倾向；',u'难以看到目前不存在的机会和选择；',u'对行政上的细节和程序缺乏耐心；',u'较难以做出果断的决定；',u'具有较强的独立性，不喜欢过多的条条框框、官僚作风；',u'不喜欢制定长期的目标；',u'斗志不足，容易松懈，通常不愿付出过多的努力；',u'缺乏挑战精神，对失败和挫折的承受力较差。'],'PositionMatch':[u'必须在一个没有过多规则和操作标准要求的环境下工作，可以享受冒险的乐趣，也可以应付危机；',u'允许您独立工作，而且可以经常做户外活动；',u'工作具有挑战性，有效的分配活动和能量，不必履行多余的程序；',u'尽可能少的监督您的工作，也不需要您过多的去监视他人；',u'不需要过多与人互动、影响他人的工作，相对于人，更喜欢与事物打交道，例如机器、设备的工作。'],'SocialRequire':{'summary':u'您对组织的社会性要求不高','detail':[u'您较为保守，喜欢在工作中拥有个人的空间。您喜欢这样的企业，他们尊重和强调个人的素质，并且奖励个人取得的成就，而不是只去建立社会关系网；',u'您不愿把自己看作一个有野心的人，所以也不会喜欢那些鼓励员工有野心的企业。']},'DetailRequire':{'summary':u'您对组织的结构和工作的细节关注度要求较高','detail':[u'您喜欢有序、组织性、纪律性强的企业文化。',u'在这种高标准、严要求的文化中您会更快乐或者说更容易成功。这种企业往往不断的采用最好的做法，以便产品、服务的质量与众不同。',u'您会为成为一个行业领先企业中的一员而骄傲。']},'OpenessRequire':{'summary':u'您对组织的开放性和想象力要求不高','detail':[u'您更倾向于那些忙碌的、注重实际操作的企业文化，用现有经过检验的方法处理事务；',u'您崇尚经过时间检验的能力的有效性和可预测性；',u'您不会从事风险极大的事情；',u'您更欣赏按照传统方法按规定做事，不计时间代价的企业；',u'您喜欢企业有明确目标、清晰的商业战略，并且能够尽可能有效和始终如一执行这些策略的企业文化。']},'CooperateRequire':{'summary':u'您对组织的合作性和和谐性要求不高','detail':[u'您把竞争和人员间的不同意见看成是创新和商业成功的驱动力；',u'您喜欢鼓励讨论、争论、坦诚交流的企业文化，与其他人相比您也许会与您的同事保持相对较远的关系；',u'您在生机盎然和进取的企业文化里工作状态最好。']},'SuccessKey':[u'学会与人交流和分享；',u'重视自己的情感，并考虑别人的感受；',u'坚持计划，信守承诺。'],'Proposal':[u'需要加强与他人的深入交流沟通；',u'需要发展自己的持恒性，不要过多的变动；',u'需要形成设立目标、制定计划的习惯；',u'适合的时候，主动承担一些工作对您的发展更有利；',u'正确看待失败，碰到困难不要随意放弃。'],'SuitableJob':{'JobType': [u'摄影师、销售商、体育教练、消防员、刑侦人员、警察、赛车手、飞行员等。',u'电子/机械/土木工程师、软件开发、计算机工程师、系统分析师、地理学家、网络工程师、检测员、外科医师等。 ',u'证券分析师、采购员、办公室管理员、经济学者、管理顾问、土木/机械工程师、保险理算员等。',u'飞机机师、教练、园艺设计、摄像师/特效专家、军官、保险鉴定人、刑事侦察员、画家、模型设计/制造者等。 '],'Reason': [u'您喜欢自然的环境，独自工作，能够综合自己的能力迅速找到策略，采取恰当的行动。',u'大多数您这种特点的人在机械技术领域表现的十分优秀，有较强的观察力和对细节、事实的记忆力，喜欢自己动手。',u'您能够使混乱的数据和模糊的事实排列有序，能够较容易地看到经济环境中的实际情况，做这种独立自主的工作能让您非常快乐。',u'贸易的独立和实践的实际性常吸引着您，您推崇真实具体而且具有机会动手的任务，对匹配您兴趣的工作更为勤奋。']}},
            }

            character_result = character.get(characteristics, None)
            character[characteristics]["characteristics"] = characteristics
            default_data["msg"]["style"] = character_result
            default_data["msg"]["score"] = ret_score
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    def getMC2019_90(self, personal_result_id):

        list_quotas = [u"变革推动",u"创新优化",u"客户导向",u"跨界协同",u"团队领导",u"勇于承担",u"正直诚信",u"资源整合",u"系统思维",u"积极进取"]
        dict_score_level = {4.0:'H',2.5:'M',0.0:'L'}
        dict_score_quota_self = {u"变革推动":0.00,u"创新优化":0.00,u"客户导向":0.00,u"跨界协同":0.00
                                ,u"团队领导":0.00,u"勇于承担":0.00,u"正直诚信":0.00,u"资源整合":0.00
                                ,u"系统思维":0.00,u"积极进取":0.00}
        dict_score_behaviour_self = {u"处事公平公正":0.00,
                                u"打造创新机制及氛围":0.00,
                                u"多形式学习交流":0.00,
                                u"敢于尝试持续创新":0.00,
                                u"敢于当面直谏":0.00,
                                u"高效合理授权":0.00,
                                u"管理阻抗":0.00,
                                u"过程管控与跟踪":0.00,
                                u"捍卫变革":0.00,
                                u"换位思考，促进协作":0.00,
                                u"换位思考，构建解决方案":0.00,
                                u"会付出额外的努力":0.00,
                                u"积极寻求解决办法,坚持不懈":0.00,
                                u"建立合作机制，实现效能最大化":0.00,
                                u"借鉴经验，快速有效优化":0.00,
                                u"理解变革":0.00,
                                u"理解高效团队的重要性":0.00,
                                u"理解其他部门需求及利益":0.00,
                                u"明确职责，主动承担责任":0.00,
                                u"前瞻性分析":0.00,
                                u"倾听并及时反馈":0.00,
                                u"塑造团队文化":0.00,
                                u"调解冲突，达致双赢":0.00,
                                u"挺身而出，成为依靠":0.00,
                                u"为自己设置挑战性目标":0.00,
                                u"问题发现及分析":0.00,
                                u"协调资源超越期望":0.00,
                                u"形成固有并可持续的模式 ":0.00,
                                u"言行一致遵守承诺":0.00,
                                u"以目标为导向，完成工作":0.00,
                                u"有责无疆，积极推进":0.00,
                                u"原因识别及构建解决方案":0.00,
                                u"愿景塑造":0.00,
                                u"主动共享信息 ":0.00,
                                u"主动关注提升满意度":0.00,
                                u"主动关注新事物":0.00,
                                u"主动争取和协调资源 ":0.00,
                                u"转变思维，扩展资源渠道 ":0.00,
                                u"自我激发,从内心寻求动力":0.00,
                                u"做事规范坦率真诚":0.00}

        analyis_self = {}
        advices = {}
        dict_analysis = {u"个人相对优势能力":[],u"个人相对劣势能力":[]}
        dict_behaviour_question = {"B29":u"处事公平公正",
                                "B05":u"打造创新机制及氛围",
                                "B17":u"多形式学习交流",
                                "B06":u"敢于尝试持续创新",
                                "B30":u"敢于当面直谏",
                                "B18":u"高效合理授权",
                                "B01":u"管理阻抗",
                                "B21":u"过程管控与跟踪",
                                "B02":u"捍卫变革",
                                "B13":u"换位思考，促进协作",
                                "B09":u"换位思考，构建解决方案",
                                "B39":u"会付出额外的努力",
                                "B40":u"积极寻求解决办法,坚持不懈",
                                "B14":u"建立合作机制，实现效能最大化",
                                "B07":u"借鉴经验，快速有效优化",
                                "B03":u"理解变革",
                                "B19":u"理解高效团队的重要性",
                                "B15":u"理解其他部门需求及利益",
                                "B25":u"明确职责，主动承担责任",
                                "B22":u"前瞻性分析",
                                "B10":u"倾听并及时反馈",
                                "B20":u"塑造团队文化",
                                "B16":u"调解冲突，达致双赢",
                                "B26":u"挺身而出，成为依靠",
                                "B37":u"为自己设置挑战性目标",
                                "B23":u"问题发现及分析",
                                "B11":u"协调资源超越期望",
                                "B33":u"形成固有并可持续的模式 ",
                                "B31":u"言行一致遵守承诺",
                                "B27":u"以目标为导向，完成工作",
                                "B28":u"有责无疆，积极推进",
                                "B24":u"原因识别及构建解决方案",
                                "B04":u"愿景塑造",
                                "B34":u"主动共享信息 ",
                                "B12":u"主动关注提升满意度",
                                "B08":u"主动关注新事物",
                                "B35":u"主动争取和协调资源 ",
                                "B36":u"转变思维，扩展资源渠道 ",
                                "B38":u"自我激发,从内心寻求动力",
                                "B32":u"做事规范坦率真诚"}

        dict_quota_advice = \
                    {u"正直诚信":[u"规章制度是促进公司正常有序运行的基础，需要加强遵守规范制度的自觉性，以及互动中坦率真诚的意识",
                                u"诚信是做人之根本，是人际关系建立的基础，加强言出必行的意识，做到言行一致才能赢得他人的尊重和信任",
                                u"公平公正是员工最期望领导者具备的素质之一。加强自身在制定决策、处理问题上的公正性，努力规避个人情感因素的影响，即可赢得下属的尊重，也是表现自己领导风范的一次机会",
                                u"加强维护利益、坚持组织原则的意识，发现内外勾结等情况时，勇于向上反映"],
                    u"勇于承担":[u"加深对工作职责的理解，培养工作主动性及承担困难任务的意识",
                                u"加强对本职岗位工作职责的认识，不清晰的地方可以找相关人员询问清楚",
                                u"增强以实现战略目标为工作导向的意识，主动承担责任，出色完成工作",
                                u"开展工作之前，不妨先想一下需要达成或实现的目标，从目标往回拆分工作任务",
                                u"遇到困难挫折，不要轻言放弃，坚持一下说不定会有不一样的结果",
                                u"淡化职责边界意识，积极协调、推进相关部门共同协作，确保任务完成",
                                u"公司是个人的载体，公司的利益应高于个人利益，作为团队的领航者，您需要在危机时刻主动站出，成为大家找出方向的依靠"],
                    u"创新优化":[u"加强对行业内/市场上新事物、新技术、新方法的敏锐度和关注度",
                                u"主动从竞争对手、内外部客户反馈中发现借鉴价值，并对其进行一定的优化/微创新，提升工作效率",
                                u"借鉴他人在工作上的经验，结合当前行业内的新技术，进行深入的分析，总结尝试过程中的经验教训",
                                u"在团队中鼓励员工进行各方面（如，工作方法）的优化创新，并定期组织经验分享会，树立强烈的创新氛围"],
                    u"客户导向":[u"了解客户真实需求和感受是提供优质客户服务的基础，耐心倾听、了解客户感受，主动将顾客体验反馈给相关人员",
                                u"主动站在客户的角度，充分考虑其需求和期望利益，以最快的速度给予问题反馈和解决",
                                u"加强协调并善用内外部资源，挖掘客户更深层的需求，以满足/超越客户原有的期望，树立的良好形象",
                                u"主动关心客户，了解其当前的困难和发展需求，给予适当的帮助和服务，以确保客户满意度的不断提高"],
                    u"跨界协同":[u"仔细梳理的组织架构，主动向上级/各部门管理者了解不同职能部门的需求和利益",
                                u"理解其他部门的工作流程和工作量，以其他部门角度来看待问题，促进双方共同协作",
                                u"主动了解部门内外冲突的原因，平衡各方的利益，通过双赢的方式解决冲突",
                                u"主动进行各部门间的沟通，共同探讨如何平衡部门间决策的相互影响，以确保达成合作机制"],
                    u"团队领导":[u"总结过往工作中，不同运作效率的团队对部门目标达成的作用，加强对团队的运作效率的了解和支持",
                                u"结合员工的能力现状和工作任务内容才能做到人岗匹配，达到效能的最大化，授权之后也不代表我们领导者工作的结束，还需要进行及时的跟进辅导，才能确保各项工作任务的有序开展",
                                u"为了提升团队的整体效能，作为团队的领导者，很有必要为团队创造多种形式的交流、分享、学习的平台，促进整个团队能力提升",
                                u"确定团队文化的方向，并积极的宣导团队愿景，巩固团队的凝聚力，激发团队自主效率"],
                    u"变革推动":[u"如有可能，可以争取与高层沟通的计划，讨论推动变革的深层原因，加深对变革必要性和收益的理解",
                                u"站在尽可能高的战略角度，为变革做出全局的规划，然后再层层细化，确定变革愿景达成过程中需要每个人付出的努力",
                                u"准备专门的幻灯片或其他材料，为团队成员系统梳理变革的必要性，以及每一位成员在变革中的价值所在，并解答大家可能提出的疑惑",
                                u"为变革设计和运行一个正规的流程，有利于督促自己担当变革推动者的角色，也有利于推动变革的努力取得效果"],
                    u"系统思维":[u"积极去发现工作中出现的问题，不回避问题，并运用多种思维方式来分析问题的成因和解决办法",
                                u"不局限于问题的表面，努力去分析问题的本质原因，以解决问题根源为导向来构建问题解决方案",
                                u"在问题解决过程中，紧密跟踪问题的状态与事态的发展，及时的调整问题解决方案，以快速有效的解决问题为目标",
                                u"主动去了解本行业发展趋势和动态，基于经验和知识对业务发展做出预判，并积极针对预判构建备选方案，以确保业务或流程的顺畅推进"],
                    u"资源整合":[u"信息的传播与共享能够促进组织效率的提升。您可以尝试在公司内部设立资源共享平台，提高自身及他人信息传播的意识，推动各职能部门协调效率的提升",
                                u"客户需求的满足离不开组织内部的共同协作，这就意味着您不仅仅要善用现有资源，同时要争取并协调其他部门资源。因此您可能需要加强对各部门利益的了解，确保客户需求满足",
                                u"市场发展的变化瞬息万变，您在工作中可通过行业报告等途径了解行业最新动态，转变思维模式",
                                u"对于企业来说，不断拓展资源渠道是至关重要的。主动在工作中寻求多方合作对象，认真筛选，推动组织资源的整合效应",
                                u"资源整合是组织发展的必然趋势，首先您需要清晰并坚持组织在目标医院的战略规划，其次您需要从长远的角度考量不同资源相互协调配合所产生的效益，以打造提升组织效能的资源体系；"],
                    u"积极进取":[u"需要主动走出自身的舒适区，尝试对自身提出更高的要求和挑战。",
                                u"需要更多从任务本身发现乐趣，并以此来激励自己全情投入，而不要过于看重来自外部的激励。",
                                u"面对完成任务中的困难和挑战，需要你更多的坚持和投入，有时成功来自于对最后一米的坚持。"]}

        dict_quota_behaviour = {u"正直诚信":[u"做事规范坦率真诚",u"言行一致遵守承诺",u"处事公平公正",u"敢于当面直谏"],
                        u"勇于承担":[u"明确职责，主动承担责任",u"以目标为导向，完成工作",u"有责无疆，积极推进",u"挺身而出，成为依靠"],
                        u"创新优化":[u"主动关注新事物",u"借鉴经验，快速有效优化",u"敢于尝试持续创新",u"打造创新机制及氛围"],
                        u"客户导向":[u"倾听并及时反馈",u"换位思考，构建解决方案",u"协调资源超越期望",u"主动关注提升满意度"],
                        u"跨界协同":[u"理解其他部门需求及利益",u"换位思考，促进协作",u"调解冲突，达致双赢",u"建立合作机制，实现效能最大化"],
                        u"团队领导":[u"理解高效团队的重要性",u"高效合理授权",u"多形式学习交流",u"塑造团队文化"],
                        u"变革推动":[u"理解变革",u"愿景塑造",u"管理阻抗",u"捍卫变革"],
                        u"系统思维":[u"问题发现及分析",u"原因识别及构建解决方案",u"过程管控与跟踪",u"前瞻性分析"],
                        u"资源整合":[u"主动共享信息 ",u"主动争取和协调资源 ",u"转变思维，扩展资源渠道 ",u"形成固有并可持续的模式 "],
                        u"积极进取":[u"为自己设置挑战性目标",u"自我激发,从内心寻求动力",u"会付出额外的努力",u"积极寻求解决办法,坚持不懈"]}

        dict_quota_desc = {u"变革推动":u"能够积极识别和寻求变革的机会和阻力，并为取得建设性的、有益的结果激发变革共识、制定系统计划并主导推进和有效地控制变化。",
                        u"创新优化":u"敢于打破常规，接纳并进行主动创新，善于从不同的角度提出新颖的问题解决方法,推进问题得到改善。",
                        u"积极进取":u"能够从自我价值实现的角度设置高标准、具有挑战性的目标，不断自我激励，寻求各种方法努力获得成功。",
                        u"客户导向":u"能够积极关注并有效识别客户的真实需求，采取有效行动并建立良好的客户互动关系。",
                        u"跨界协同":u"立足公司整体并从流程协同的角度主动打破边界、换位沟通并通力合作，出现分歧时能寻求整合解决，建立组织协同优势",
                        u"团队领导":u"通过有效的机制和方法进行团队价值引导、目标整合、信任建立、潜能激发，塑造优秀团队文化，推动团队高绩效实现。",
                        u"系统思维":u"立足公司战略定位，洞察行业发展的趋势，系统分析业务发展的各种因素，把握本质并结合实际，形成整体判断和系统性的策略安排",
                        u"勇于承担":u"始终立足公司发展的大局，积极地看待转型发展中的问题并敢于负责、主动承担、积极奉献，能包容，善团结。",
                        u"正直诚信":u"坚持从客观事实出发，公正公平，坚持原则，不畏权威，言行一致，推动坦诚信任的组织文化建设。",
                        u"资源整合":u"立足价值链的协同，从增加和创造商业价值的角度，通过合理的方式和机制获取资源，并进行有效配置以实现资源价值最大化"}

        dict_behaviour_desc = {u"做事规范坦率真诚":{"H":u"能够遵守的制度规范，主动真诚地与他人分享信息","M":u"基本能够遵守制度规范，能够在互动中有一定的坦诚交流","L":u"可能在工作、互动中忽视了规章制度，及坦诚的重要性"},
                        u"言行一致遵守承诺":{"H":u"能够言行一致，遵守对他人的承诺，承诺过的事情一定做到","M":u"一般情况下都能够做到言行一致","L":u"言行可能会不一致，很少会将自身的承诺转化为实际行动"},
                        u"处事公平公正":{"H":u"坚持公平公正的原则处理问题、制定决策，对事不对人","M":u"基本能够秉持客观公正的处事原则","L":u"可能在处理问题上掺杂了个人情感"},
                        u"敢于当面直谏":{"H":u"面对权威敢于当面直谏，主动保护组织利益","M":u"大多情况下能够坚持组织原则，向上进行反馈","L":u"可能对权威有一定的畏惧，忽视了组织的利益"},
                        u"明确职责，主动承担责任":{"H":u"清晰自身岗位职责，能够主动承担并处理职责范围内的困难任务","M":u"基本能够清楚工作职责要求，承担起份内的工作","L":u"可能对工作职责和角色不是太清晰，缺乏对本职工作责任的担当"},
                        u"以目标为导向，完成工作":{"H":u"目标导向，为了实现目标，能够承担压力，不择不扣地完成工作内容或任务","M":u"基本能够完成本职或者上级交付的工作","L":u"可能目标导向性较为薄弱，在完成工作任务时会有所折扣"},
                        u"有责无疆，积极推进":{"H":u"能够积极处理职责内外事务，主动推动相关部门协作，推进任务完成","M":u"大多情况下不设定职责边界，并能够推动各部门共同合作完成任务","L":u"可能为自身划分出明确的职责范围，不善于推进各部门的共同协作"},
                        u"挺身而出，成为依靠":{"H":u"始终心系利益，主动在关键时刻挺身而出成为大家的依靠","M":u"面对逆境，基本能够不计较个人得失，为大家找出方向","L":u"面对危难时，或许很难带领大家找出问题解决的方向"},
                        u"主动关注新事物":{"H":u"主动关注并借鉴行业/市场出现上的新事物","M":u"对行业/市场上的新技术、新方法有一定的关注和思考","L":u"可能对行业/市场上的新生事物、新技术、新方法等缺乏一定的了解"},
                        u"借鉴经验，快速有效优化":{"H":u"善于借鉴各方经验及反馈信息快速有效地进行微创新","M":u"优势能够在借鉴他人经验的基础上，对本职工作进行一些优化或微创新","L":u"可能不太善于借鉴他人的经验来完善或优化自己的工作"},
                        u"敢于尝试持续创新":{"H":u"敢于试错并不断地总结分析经验促进工作方法上的创新","M":u"基本能够对工作中的经验和错误进行持续的优化","L":u"可能不太会为了改进工作方法/机制，而去尝试或犯错"},
                        u"打造创新机制及氛围":{"H":u"善于在团队中营造创新的氛围，鼓励并接纳员工的创新","M":u"大多情况下鼓励员工进行业务、工作方法等方面的创新","L":u"可能很少在团队中打造创新机制"},
                        u"倾听并及时反馈":{"H":u"善于倾听内外部客户感受，并及时与相关人员进行反馈","M":u"对内外部客户感受有一定的了解，并与相关人员进行沟通","L":u"可能对内外部客户的感受有所忽视，不能给予相关反馈"},
                        u"换位思考，构建解决方案":{"H":u"善于从内外部客户的角度看待问题，构建解决方案增强客户满意度","M":u"基本能够以内外部客户利益来提供问题解决方案","L":u"很少从内外部客户角度处理问题，提供服务"},
                        u"协调资源超越期望":{"H":u"善于协调各方资源，深化内外部客户需求，超越客户对工作的期望","M":u"基本能够结合内外资源满足/超越客户需求","L":u"可能需要加强资源协作上的技巧，以确保实现/超越内外部客户期望"},
                        u"主动关注提升满意度":{"H":u"能够主动关心内外部客户的发展和困难，并给予支持和帮助，不断提高客户满意度","M":u"对客户有一定的关注，在提供内外部客户支持和帮助方面基本与大多数人一致","L":u"很少了解客户的需求，可能很难使客户满意"},
                        u"理解其他部门需求及利益":{"H":u"充分明晰各部门的需求及利益，了解项目/时间对其他部门的影响","M":u"对各职能部门的需求和利益有一定的了解","L":u"可能很少关注其他部门的利益需求"},
                        u"换位思考，促进协作":{"H":u"主动从其他部门的角度考虑问题，实现各部门之间的相互支持","M":u"基本能够做到各部门之间的相互理解和协作","L":u"可能在工作中从本部门的角度为出发点，缺少了共同合作的精神"},
                        u"调解冲突，达致双赢":{"H":u"善于在利益冲突过程中进行综合考量，制定解决方案，达成各部门间的双赢","M":u"基本能够调节部门内外冲突，实现各部门间利益双赢","L":u"或许很少以双赢的方式解决部门内外冲突"},
                        u"建立合作机制，实现效能最大化":{"H":u"善于建立长期的部门合作机制，实现效益最大化","M":u"对决策的影响有一定的预估，基本能够建立协同合作机制","L":u"可能忽略了各个部门间合作机制的构建"},
                        u"理解高效团队的重要性":{"H":u"清楚理解高效团队对部门目标达成的重要性，会主动去了解团队的运作效率和挑战","M":u"基本能够意识到团队高效运作的重要意义，对团队的运作效率有一定的了解","L":u"可能不太理解高效团队对目标达成的重要性，很少回去了解团队的现状"},
                        u"高效合理授权":{"H":u"善于根据员工的能力进行合理有效的授权，并长期跟踪与反馈","M":u"给予部门员工在工作任务上一定的权限和辅导","L":u"可能在如何授予员工对应的权限和责任有待提升，不太能合理授权"},
                        u"多形式学习交流":{"H":u"积极主动地在团队内部组织多种形式的学习交流活动（如，成功经验分享）","M":u"基本能够根据需求采用不同的方式展开经验分享","L":u"可能不太善于为团队创造不同形式的学习交流活动"},
                        u"塑造团队文化":{"H":u"善于打造团队文化，激发团队自主效能，打造高效团队","M":u"在团队内能够进行愿景宣导，激励团队向心力方面与大多数人一样","L":u"可能缺少团队凝聚力、团队文化的建设"},
                        u"理解变革":{"H":u"清楚理解驱动变革的深层原因，以及变革所能带来的全局收益","M":u"基本能够理解驱动变革的原因，但是对于变革带来的收益认识模糊","L":u"对于公司/行业正在发生的变革缺乏理解，不明白变革的需求以及变革带来的收益"},
                        u"愿景塑造":{"H":u"善于为变革创造一个全局的愿景，并基于愿景的达成恰当地授权他人","M":u"能够基于变革创造愿景，但是缺乏为达成愿景进行授权的技巧","L":u"无法基于变革描述愿景，或是不知道怎样基于愿景进行授权"},
                        u"管理阻抗":{"H":u"在变革中总是能够向团队解释清楚变革带来的积极影响，并且清晰阐明成员的角色和价值，赢得成员对于变革的认可和配合","M":u"在变革中通常能够就变革向团队进行解释，但是对于成员角色和价值的描述有时并不清晰，因此会遇到阻抗和消极对待","L":u"在变革中，几乎不向团队解释变革，无法阐明团队成员的角色和价值，因此往往遇到阻抗和消极的现象"},
                        u"捍卫变革":{"H":u"主动担任变革的捍卫者，自身支持变革的同时还能够鼓励同事参与变革","M":u"认可自己作为变革参与者的一份子，通常能够积极拥护变革，支持变革的发生","L":u"在变革中常常置身事外，没有承担起捍卫变革、推动变革的角色"},
                        u"问题发现及分析":{"H":u"主动关注并发现工作中出现的问题，并能够基于内外部客观事实来分析问题","M":u"基本能够发现工作中出现的一些问题，也能够基于事实来分析问题","L":u"或许不太能够发现工作中的问题，也难以对问题进行深入分析"},
                        u"原因识别及构建解决方案":{"H":u"能够透过问题看本质，识别问题的根本原因，并善于以解决问题根源为目的制定解决方案","M":u"基本能够识别问题较深层次的原因，并能够构建问题的解决方案","L":u"不太能够识别问题的本质原因，难以构建以解决问题根源为目的的解决方案"},
                        u"过程管控与跟踪":{"H":u"善于在解决问题的过程中紧密跟踪，及时调整问题解决方案","M":u"基本能够在问题解决过程中跟踪问题的状况与事态的发展，调整问题的解决方案","L":u"或许不太能够紧密跟踪问题的解决过程，难以及时调整问题解决方案"},
                        u"前瞻性分析":{"H":u"能以前瞻性的视野看待问题，善于发现潜在的机会或风险","M":u"能够提前预计各种情况，不会走一步看一步","L":u"不太能用发展的眼光看待问题，往往只关注眼前的问题"},
                        u"主动共享信息 ":{"H":u"主动在内部建立协作关系，促进资源信息共享","M":u"能够在内部建立协作关系，推动信息传播和共享","L":u"可能较少在组织内部传播、分享信息资源"},
                        u"主动争取和协调资源 ":{"H":u"以公司需求和市场发展为目标，发掘各部门/事业部协作机会，争取并协调组织资源，以满足客户需求","M":u"基于对各部门及事业部利益点的了解，基本能以客户需求为出发点，协调各方资源，推动需求满足","L":u"可能忽视了组织内各事业部及部门的不同利益点，不太擅长协调各部门资源，满足客户需求"},
                        u"转变思维，扩展资源渠道 ":{"H":u"敢于突破思维，引进新资源，促成多方合作，扩展资源渠道","M":u"对新资源持有开放的态度，基本能扩展已有的渠道，推动产品组合的整合效应","L":u"可能偏向于固有的合作思维，较少引进新资源，资源渠道较为单一"},
                        u"形成固有并可持续的模式 ":{"H":u"善于从宏观层面综合考量资源的协调与配合，优化资源配置，敢于打造并固化新的资源整合体系","M":u"基本能从长远发展的角度出发，整体考量资源整合体系，促进组织效能的提升","L":u"可能更多的使用固有的资源体系进行资源配置，不太善于提升组织效能"},
                        u"为自己设置挑战性目标":{"H":u"具有强烈的渴望成功的愿望，勇于挑战现状，设立奋斗的目标","M":u"有一定的追求成功的愿望，一般不会满足于现状，能够给自己设定具有一定挑战性的目标","L":u"面对任务时，可能会安于现状，对自己没有太高的要求"},
                        u"自我激发,从内心寻求动力":{"H":u"在困难和挑战面前，能以自我价值实现为动力，积极调动自身能量，激情投入","M":u"为了目标的达成能够付出和努力行动，有时需要外部的一些肯定或激励才会持续地投入","L":u"在缺乏外部激励时可能会缺乏激情，容易放弃"},
                        u"会付出额外的努力":{"H":u"投入额外的时间和精力，达成行业或组织内最佳的工作成果","M":u"能够投入额外的努力，有追求更好成果的愿望","L":u"可能缺乏额外投入的意愿，更多只愿完成份内的工作。"},
                        u"积极寻求解决办法,坚持不懈":{"H":u"面对困难和挑战仍能够持续投入，利用各种方法保证最终达到目标","M":u"面对困难，能主动面对，并愿意做出一定的投入","L":u"面对困难缺乏自信，容易产生放弃、逃避和退缩的念头"}}        

        default_data = {
            "report_type": "MC2019_90",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "scores":{"self":dict_score_quota_self},
                "analysis":dict_analysis,
                "details_self":analyis_self,
                "advices":advices
            }}

        frontname = settings.DATABASES['front']['NAME']

        sql_query_self = "select b.tag_value ,a.score from\
            (select answer_id,answer_score score\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.answer_id=b.object_id and b.tag_id=54\
            and b.is_active=True"
     

        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['mc2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())
                                                                
            with connection.cursor() as cursor:
                # get self mc
                cursor.execute(sql_query_self, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                dictscore = {}
                # get question answers
                for row in cursor.fetchall():
                    if dictscore.has_key(row[0]):
                        dictscore[row[0]]=dictscore[row[0]]+row[1]
                    else:
                        dictscore[row[0]]=row[1]
                # get behaviour score
                for key,value in dictscore.items():
                    if dict_behaviour_question.has_key(key): 
                        dict_score_behaviour_self[dict_behaviour_question[key]]=(value+3)/1.2
                # get quota score
                for key,value in dict_quota_behaviour.items():
                    for bv in value:
                        dict_score_quota_self[key] += dict_score_behaviour_self[bv]
                    dict_score_quota_self[key] = (dict_score_quota_self[key] * 1.00)/len(value)
            
            #get top.last 2 of self-mc
            keys,values = zip(*sorted(dict_score_quota_self.items(), key=lambda d:d[1],reverse = True))
            dict_analysis[u"个人相对优势能力"].extend(keys[:3])
            dict_analysis[u"个人相对劣势能力"].extend(keys[-1:-4:-1])        
            #quota details
            for quota in list_quotas:
                analyis_self[quota]={}
                analyis_self[quota]["pt"]=dict_score_quota_self[quota]
                analyis_self[quota]["desc"]=dict_quota_desc[quota]
                analyis_self[quota]["memo"]=[]
                mark = "L"
                for bv in dict_quota_behaviour[quota]:
                    for margin in dict_score_level.keys():
                        if dict_score_behaviour_self[bv]>=margin:
                            mark = dict_score_level[margin]
                            analyis_self[quota]["memo"].append(\
                                (mark,dict_behaviour_desc[bv][mark]))
                            break


            dict_analysis[u"个人相对优势能力"]=dict_analysis[u"个人相对优势能力"][:2]
            dict_analysis[u"个人相对劣势能力"]=dict_analysis[u"个人相对劣势能力"][:2]

            for quota in dict_analysis[u"个人相对劣势能力"]:
                advices[quota]=dict_quota_advice[quota]

        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS      


    def getPC2019(self, personal_result_id):

        ordict_quota = {'quota':[],'score':[]}
        dict_ranking = {}
        dict_ranking[1]=[]
        dict_ranking[2]=[]
        dict_ranking[3]=[]
        dict_detail={}
        dict_detail[u"动机取向"]={"scores":[],"quotas":[],"suggest":[]}
        dict_detail[u"认知取向"]={"scores":[],"quotas":[],"suggest":[]}
        dict_detail[u"意志取向"]={"scores":[],"quotas":[],"suggest":[]}
        dict_detail[u"情绪取向"]={"scores":[],"quotas":[],"suggest":[]}
        dict_detail[u"任务取向"]={"scores":[],"quotas":[],"suggest":[]}
        dict_detail[u"人际取向"]={"scores":[],"quotas":[],"suggest":[]}
        dict_dimension_qutoa = {
            u"进取性":u"动机取向",
            u"支配性":u"动机取向",
            u"亲和性":u"动机取向",
            u"开放性":u"认知取向",
            u"乐观性":u"认知取向",
            u"变通性":u"认知取向",
            u"内省性":u"认知取向",
            u"独立性":u"意志取向",
            u"坚韧性":u"意志取向",
            u"自律性":u"意志取向",
            u"悦纳性":u"情绪取向",
            u"稳定性":u"情绪取向",
            u"自信心":u"情绪取向",
            u"尽责性":u"任务取向",
            u"容人性":u"人际取向",
            u"利他性":u"人际取向",
        }
        score_social_desirability = 0

        default_data = {
            "report_type": "PC2019",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "CompletionTime":"",
                "Validity":"",                
                "scores":ordict_quota,
                "ranks":dict_ranking,
                "detail":dict_detail,
            }}

        liststd = [75,30,0]
        dict_std = {u"进取性":{"avg":9.9218 ,"std":2.8134 },
                    u"支配性":{"avg":7.8741 ,"std":2.2837 },
                    u"亲和性":{"avg":10.7492 ,"std":2.2238 },
                    u"开放性":{"avg":11.4568 ,"std":2.2386 },
                    u"乐观性":{"avg":10.7943 ,"std":2.3241 },
                    u"变通性":{"avg":9.3143 ,"std":2.3755 },
                    u"内省性":{"avg":9.8525 ,"std":2.3303 },
                    u"独立性":{"avg":10.5365 ,"std":2.4590 },
                    u"坚韧性":{"avg":8.3136 ,"std":2.7231 },
                    u"自律性":{"avg":7.3937 ,"std":2.1992 },
                    u"悦纳性":{"avg":11.2215 ,"std":2.4083 },
                    u"稳定性":{"avg":8.3257 ,"std":3.2422 },
                    u"自信心":{"avg":10.9360 ,"std":2.7136 },
                    u"尽责性":{"avg":11.3242 ,"std":2.0988 },
                    u"容人性":{"avg":8.2866 ,"std":2.1232 },
                    u"利他性":{"avg":11.0449 ,"std":2.2027}}

        dict_table_suggestion = {
            u"进取性":{1:u"具有强烈的渴望成功的愿望，勇于挑战现状，始终从自我价值的实现的角度设定自己的理想抱负和奋斗目标，并以此来激励自己，作为目标达成的动力，积极付出、努力行动，不断完善和超越。（极端高分：可能过于看重自己个人的成就，难以容忍些许的不足，给人以工作狂的印象。）",
                        2:u"有一定的追求成功的愿望，一般不会满足于现状，能够给自己设定具有一定挑战性的目标，为了目标的达成能够付出和努力行动。有时需要外部的一些肯定或激励才会持续地投入追求更高的目标和不断的完善和超越。",
                        3:u"获得成功的愿望稍差，不太喜欢挑战，容易安于现状，不会主动设置较高的目标，不能调动自身的能量来投入，在困难和挑战面前，不愿付出努力，容易放弃，需要依赖外部的刺激来驱动自己，前进动力不足。"},
            u"支配性":{1:u"工作中乐于支配和获得主导地位，喜欢以自己的思想和意图影响和改变他人和环境，喜欢组织、安排他人按自己的意愿行事，不愿受到约束。",
                        2:u"工作中能够表现出一定的主导意愿，愿意通过自己的思想、意图影响他人和环境，能够进行组织、安排，面对外部环境的约束时，也会表现出相应的妥协。",
                        3:u"工作中以自己的思想、意图影响控制他人和环境的愿望表现不充分，不愿意进行主导和影响、控制和安排，愿意服从和跟随，愿意接受安排和约束。"},
            u"亲和性":{1:u"人际交往中，设身处地为他人着想，善解人意，言行举止透露出对他人的信任和尊重，待人热情，受人欢迎，乐于助人、合作，注重与人建立良好的人际关系。（极端高分：可能过于关注给别人留下好印象而过分取悦他人，甚至有时会放弃原则或过度迁就他人。）",
                        2:u"人际交往中，能够从他人的角度考虑问题，理解、尊重并信任他人，待人比较热情，能够关注自己给人留下的印象，在别人需要时能够提供帮助和支持，愿意与他人打交道，进行合作和建立关系。",
                        3:u"人际合作取向低，易于自我中心。与他人交往、参加社交活动以及建立良好关系的愿望很弱，不能从他人的角度思考问题，较难理解他人的需求和感受，不在乎是否受到欢迎，不会主动提供帮助，较难相处，亲和力较差。"},
            u"开放性":{1:u"不局限于既有的观念、思维模式的束缚，主动尝试新事物，主动接纳变化和多样性，对不确定性的模糊情境有较强的容忍力，善于根据情境的变化适宜改变和修正自己的观点，实现自己持续性的成长。",
                        2:u"通常情况下能够摆脱原有思维模式或习惯的束缚，愿意尝试新事物，不排斥变化和多样性，对不确定性的模糊情境有一定的适应性，愿意根据情境的变化适宜改变和修正自己的观点，实现自己的成长河进步。",
                        3:u"通常情况下局限于原有思维模式或习惯，比较保守，不愿接纳和尝试新事物，排斥多样性，不能容忍不确定性的模糊情境，对改革或变化持批驳和抵触，难以根据情境的变化适宜改变和修正自己的观点。"},
            u"乐观性":{1:u"始终从正面积极的角度捕捉信息，看待各类事物、现象、问题，正面解释和对待对工作与生活中的得失，相信一切都会变得更好，对未来充满希望，踌躇满志并积极准备和投入。（极端高分：可能过于关注事物好的一面而过滤不好的一面，甚至伴随盲目的乐观。）",
                        2:u"通常会从正面的角度看待事物、现象和问题，对待工作和生活中的得失能够从正面的角度进行解释，能够从积极的方面憧憬未来，以比较愉悦的心情投入到工作和生活中，有时会受到负面信息的影响。",
                        3:u"通常以消极的视角看待周围事物，对坏消息比较敏感，计较工作与生活中的得失，难以从正面的角度进行解释，对未来缺乏信心，较为悲观，有时会表现得很无助。"},
            u"变通性":{1:u"问题解决过程中，非常注重从不同的角度进行思考，灵活地转换思路，探索多样的问题解决策略，形成适宜解决方案并进行调整，灵活应对各种突发事件。",
                        2:u"问题解决过程中，具有从不同的角度考虑问题的习惯，在问题不能有效解决时能够进行思路的转换，注意提供问题解决的备选方案，也能在过程中进行调整并应对突发的事件。",
                        3:u"问题解决过程中，不具有从多角度思考问题的习惯，易于受既有框架和套路的局限和影响，问题解决的策略比较单一，对计划的执行较为僵化，突发事件应对的灵活性不足。"},
            u"内省性":{1:u"工作生活中，经常积极吸纳内外部的信息，主动审视自己行动所隐含的信念、观点，检查自己的思维过程和问题解决策略，反思自己经验的适应性，勇于剖析自己的不足，并进行总结、积累、校正、改进、完善。",
                        2:u"工作生活中，能够通过内外部信息的吸纳来审视自己行动所隐含的信念、观点，对自己的思维过程、问题解决策略以及经验的适用性进行一定的反思，基本能够正确对待自己的不足，并进行相应的总结、积累、校正、改进。",
                        3:u"工作生活中，不能接受外部提供的反馈信息，难以审视自己行动所隐含的信念、观点，不能对自己的思维过程、问题解决策略以及经验的适用性进行反思，回避自己的问题，极少进行总结、积累、校正和改进。"},
            u"独立性":{1:u"具有自觉明显的目的性，充分认识到行动的意义，能够独立思考，有自己独立的立场、观点和主见，重要的问题能够自主决定并支配自己的行动，能够对自己的行动负责，愿意接受有益的建议和批评。",
                        2:u"能够明确自己行动的目的，能够独立思考，拥有自己的立场、观点，一定程度上能够自主决定，支配自己的言行并负责，有时会考虑并受到外界影响，能够接收别人的建议和批评。",
                        3:u"行动时缺乏自己明确的目标性，倾向于依靠外在参照来作为行动的依据，回避一个人面对重要问题，较难独立判断和自主决定，没有主见，希望别人给自己拿主意，自己的立场和观点易于改变，屈从于别人的影响。"},
            u"坚韧性":{1:u"面对任务情境，勇于面对困难、挫折和失败，坚定地专注于既定的目标，积极寻求解决任务的办法，自觉地抵制一切不合目的的主客观诱因的干扰，具有锲而不舍、不达目的决不罢休的决心，坚信自己的能力，极少受到失望、沮丧等负面情绪的影响，有很强的心理承受能力。",
                        2:u"面对任务情境，能够面对困难、挫折和失败，少有回避困难、挫折和失败的倾向，能够关注既定目标的完成，寻求解决办法，不会过分强调任务的困难和不可完成性，极少受到失望、沮丧等负面情绪的影响，有较强的心理承受能力。",
                        3:u"面对任务情境，具有明显的回避困难、挫折和失败的倾向，担心失败，不能坚守既定的目标，缺乏自信，消极退缩，常常将潜在困难看得比实际上更严重，往往感到沮丧和失望，缺乏心理承受能力。"},
            u"自律性":{1:u"无需外在监督就能自觉控制自己不合理的需求和欲望，抗拒来自外部和内部的诱因的干扰，克制自己不应有的情绪和冲动行为，主动严格约束自己的言行举止，自觉遵守纪律。",
                        2:u"基本能够控制自己不合理的需求、欲望，偶尔需要在提醒情况下，抗拒来自外部和内部的诱因的干扰，克制自己不应有的情绪和冲动行为，有时在外部监督条件下能够束自己的言行举止，遵守纪律。",
                        3:u"自制力较弱，一般不能控制自己不合理的需求、欲望以及不良情绪冲动，即使有外在强制性监督，也难于约束自己的言行举止，行为难以预测，缺乏组织性、纪律性，不遵守行为规范。"},
            u"悦纳性":{1:u"坦然地接受自己的过去，客观地认识和评估自己的能力，对自己进行正面积极的肯定，欣赏自己并能积极面对自身的缺点和不足，并努力改正。",
                        2:u"对自己的过去经历能够接受，基本上对自己有客观的认识，能够了解自己的能力和不足，多数情况下对自己能够进行正面的肯定，欣赏自己且不会回避自己的不足，适当调整修正可以改变的行为。",
                        3:u"对自己的过去经历不能坦然接受，对自己的认识不够客观，要么夸大自己的能力，否认自己的不足，要么忽略自己的优势，夸大自己的缺陷，产生消极的自我评价，不能正面自己的不足并进行调整和修正。"},
            u"稳定性":{1:u"情绪稳定，很少为外界因素影响而波动，能够合理地控制和调节自己的情绪状态，情绪积极，很少为负面情绪所困扰。",
                        2:u"情绪较为稳定，一般情况下很少为外界因素影响而波动，具有一定控制和调节自己的情绪状态的能力，通常能够保持情绪的积极状态，没有较大的负面事件的情况下，很少为负面情绪所困扰。",
                        3:u"情绪不太稳定，易受很小的外界因素影响，不能很好地认识、把握、调节自己的情绪，经常为负面情绪所困扰。"},
            u"自信心":{1:u"对自己始终保持持续肯定性评价，认为自己有能力解决问题的信念，愿意参与竞争或挑战，不盲从权威，有克服困难、达成目标勇气和决心，具有较强的坚持力。",
                        2:u"基本上能够对自己肯定性评价，对自己的能力比较有信心。不会回避竞争，不大会盲从权威，一般情况下，相信自己有能力解决问题，克服困难，达成目标。",
                        3:u"对自己的能力缺乏信心，回避竞争和挑战，自卑，认为自己不如别人，缺乏克服困难的决心和勇气，依赖他人，易于放弃。"},
            u"尽责性":{1:u"面对不明确的任务或职责时，总是能主动承担并努力完成，尽心尽责，一丝不苟，有始有终，工作中从不给自己找借口，从不降低标准，勤勉踏实，值得信赖。",
                        2:u"工作中不会推托自己应承担的任务和责任，也能完成工作职责的要求，在外部要求明确或在一定的激励和监督的情况下，会按期按标准完成任务，有时未能完成任务时会从客观上找原因，有时也会感到暂时的不安。",
                        3:u"在严格的监督和制约下才能履行本职工作，但经常推托回避任务和责任的承担，工作中经常降低标准，敷衍了事，易于松懈和放弃，工作结果总是不尽人意，经常为自己寻找借口，难以让人信赖。"},
            u"容人性":{1:u"人际交往中，为人宽厚大度，善于包容他人的缺点和不足，以博大的胸怀包容别人的冒犯或过错，善于接纳不同的意见、观点，善于与不同风格的人交往，不拘泥于过去的成见和是非，着眼于未来的关系发展。",
                        2:u"人际交往中，比较宽厚，多数情况下能够包容他人的缺点和不足，甚至不太计较别人无心的冒犯或不敬，一般不会求全责备、苛求他人，能够与持不同观点的人以及风格不同的人进行交往和发展关系。",
                        3:u"人际交往中，较为在意别人的不足和缺点，容易求全责备和计较，难以容忍别人的冒犯或不敬，难以接受不同观点的人以及与风格不同的人进行交往，容易把对别人的偏见带入交往中，甚至在小事上和别人纠缠不清，不能从未来发展的角度与人建立和发展关系。"},
            u"利他性":{1:u"具有强烈的亲社会取向，主动为他人着想，真诚、无私地帮助他人，自觉自愿地为社会服务，维护集体利益，具有强烈的社会责任感。",
                        2:u"通常情况下，能够关注别人，愿意提供帮助，行为符合社会的期望，一般能够将集体利益放在个人利益之前，有一定的社会责任感，也会注重互惠互利的利益交换。",
                        3:u"多数情况下较为注重利益的交换，较少表现无私助人的行为，较多地关注个人的利益而不是集体的利益，有时甚至会做出不符合社会期望的举动。"}}

        frontname = settings.DATABASES['front']['NAME']
        sql_query = "select left(b.tag_value,2), sum(a.score) as score from\
            (select question_id,answer_score score\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.question_id=b.object_id and b.tag_id=54\
            and b.is_active=True group by left(b.tag_value,2)"

        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['pc2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())
            used_time = people_result.used_time
            default_data["msg"]["CompletionTime"] = u"%s分%s秒" % (used_time / 60, used_time % 60)
            dictscore = {}
            dict_quota = {}
            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                for row in cursor.fetchall():
                    dictscore[row[0]]=row[1]
            
            dict_quota[u"变通性"]=dictscore["BT"]
            dict_quota[u"独立性"]=dictscore["DL"]
            dict_quota[u"坚韧性"]=dictscore["JR"]
            dict_quota[u"尽责性"]=dictscore["JZ"]
            dict_quota[u"进取性"]=dictscore["JQ"]
            dict_quota[u"开放性"]=dictscore["KF"]
            dict_quota[u"乐观性"]=dictscore["LG"]
            dict_quota[u"利他性"]=dictscore["LT"]
            dict_quota[u"内省性"]=dictscore["NX"]
            dict_quota[u"亲和性"]=dictscore["QH"]
            dict_quota[u"容人性"]=dictscore["RR"]
            dict_quota[u"稳定性"]=dictscore["WD"]
            dict_quota[u"悦纳性"]=dictscore["YN"]
            dict_quota[u"支配性"]=dictscore["ZP"]
            dict_quota[u"自律性"]=dictscore["ZL"]
            dict_quota[u"自信心"]=dictscore["ZX"]
            score_social_desirability=dictscore["CX"]
            if score_social_desirability>=4:
                default_data["msg"]["Validity"]=u"不能按照自己的实际情况如实做答测验问题，测验结果不能很好地反映其自身的特点。"
            else:
                default_data["msg"]["Validity"]=u"回答真实可信，能够按照自己的实际情况如实做答，测验结果能够反映其自身的特点。"
            for key,value in dict_std.items():                
                zscore=(dict_quota[key]-value['avg'])*1.00/value['std']
                dict_quota[key]=round(normsdist(zscore)*100.00,0)
            sortedlist = sorted(dict_quota.items(), key=lambda d:d[1], reverse = True)
            for tp in sortedlist:                
                ordict_quota['quota'].append(tp[0])
                ordict_quota['score'].append(tp[1])
                idx = 1
                for member in liststd:
                    if tp[1] >= member:
                        dict_ranking[idx].append(tp[0])
                        dimension = dict_dimension_qutoa[tp[0]]
                        dict_detail[dimension]["scores"].append(tp[1])
                        dict_detail[dimension]["quotas"].append(tp[0])
                        dict_detail[dimension]["suggest"].append(dict_table_suggestion[tp[0]][idx])
                        break
                    idx += 1
            del dict_ranking[2]
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS  

    def getWV2019(self, personal_result_id):

        ordict_quota = {'quota':[],'score':[]}
        dict_ranking = {}
        dict_ranking[1]=[]
        dict_ranking[2]=[]
        dict_ranking[3]=[]
        dict_ranking[4]=[]
        dict_ranking[5]=[]
        dict_detail={}
        dict_detail[1]={}
        dict_detail[2]={}
        dict_detail[3]={}
        dict_detail[4]={}
        dict_detail[5]={}

        default_data = {
            "report_type": "WV2019",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "scores":ordict_quota,
                "ranks":dict_ranking,
                "detail":dict_detail,
            }}

        liststd = [4, 2,-1.9,-3,-5]

        dict_dimension_qutoa = {u'舒适/家庭':u'保障',
                                u'安全/稳定':u'保障',
                                u'经济/报酬':u'保障',
                                u'归属/团队':u'人际',
                                u'社交/人际':u'人际',
                                u'利他/慈善':u'人际',
                                u'权力/影响':u'尊重',
                                u'地位/职位':u'尊重',
                                u'认可/表现':u'尊重',
                                u'艺术/文化':u'认知与审美',
                                u'变化/探索':u'认知与审美',
                                u'专业/技术':u'自我实现',
                                u'自主/独立':u'自我实现',
                                u'挑战/成就':u'自我实现'}
        
        dict_table_description = {u'舒适/家庭':u'追求舒适、轻松、优越的工作条件和环境，关注工作与生活的平衡',
                                u'安全/稳定':u'关注工作生活的安全与稳定，偏好有序的、计划性的、可预测的工作环境，不倾向于承担风险',
                                u'经济/报酬':u'关注工作所获得的经济报酬和物质回报，自身的额外努力必须得到可见的奖励',
                                u'归属/团队':u'关注和谐的工作氛围，倾向于在团队中和他人合作开展工作',
                                u'社交/人际':u'乐于结交朋友，重视建立广泛的社会联系和关系',
                                u'利他/慈善':u'渴望帮助他人，关心社会福祉，看重在工作中的自我价值实现，主动帮助他人取得成功',
                                u'权力/影响':u'追求领导职位，比起自己处理工作人物更倾向于指导他人工作',
                                u'地位/职位':u'关注工作或职位在的社会地位，希望得到他人的重视与尊敬',
                                u'认可/表现':u'自己的工作需要得到应有的认可和肯定，希望成为人群中的关注焦点',
                                u'艺术/文化':u'重视艺术、文学等方面的工作内容，关注审美和创造，倾向于在鼓励创新的环境中工作',
                                u'变化/探索':u'希望每天都能处理全新的事务，适应变化的环境，经常尝试新的方法',
                                u'专业/技术':u'追求在技术或专业领域的成长和提高，倾向于专业或技术性的工作岗位和内容',
                                u'自主/独立':u'希望按自己的方式、步调或想法去安排工作时间、地点和方式，不倾向于受到太多来自他人的监督和控制',
                                u'挑战/成就':u'乐于在工作生活中面对挑战，克服困难，适应竞争激烈的工作环境'}
        dict_table_dimension = {u'舒适/家庭':
                                    [u'认为工作不应该影响生活，轻松、舒适工作条件以及工作与家庭的平衡能够提升满意度',
                                    u'认为工作不应该影响生活，轻松、舒适工作条件以及工作与家庭的平衡能够提升满意度',
                                    None,
                                    u'不关注工作与生活的平衡，接受在常规工作时间外执行任务，不介意加班',
                                    u'不关注工作与生活的平衡，接受在常规工作时间外执行任务，不介意加班'],
                                u'安全/稳定':
                                    [u'工作和职位具有安全感会提升工作热情',
                                    u'工作和职位具有安全感会提升工作热情',
                                    None,
                                    u'不介意工作中的风险因素，接受不稳定的职位、工作环境和氛围',
                                    u'不介意工作中的风险因素，接受不稳定的职位、工作环境和氛围'],
                                u'经济/报酬':
                                    [u'看重物质上的实际利益，很难接受自己的工作得不到足够的物质回报',
                                    u'看重物质上的实际利益，很难接受自己的工作得不到足够的物质回报',
                                    None,
                                    u'较少关注工作带来的金钱利益和其它物质回报',
                                    u'较少关注工作带来的金钱利益和其它物质回报'],
                                u'归属/团队':
                                    [u'希望在和谐互助的氛围中工作，愿意成为团队的一份子，不倾向于独自工作',
                                    u'希望在和谐互助的氛围中工作，愿意成为团队的一份子，不倾向于独自工作',
                                    None,
                                    u'希望独自承担任务，不倾向于和他人合作，不关注团队',
                                    u'希望独自承担任务，不倾向于和他人合作，不关注团队'],
                                u'社交/人际':
                                    [u'愿意主动与他人沟通，和各种人交往，建立比较广泛的社会联系和关系',
                                    u'愿意主动与他人沟通，和各种人交往，建立比较广泛的社会联系和关系',
                                    None,
                                    u'与他人的沟通互动需求比较低，不倾向于参与交际或应酬',
                                    u'与他人的沟通互动需求比较低，不倾向于参与交际或应酬'],
                                u'利他/慈善':
                                    [u'渴望帮助他人，关心社会福祉，重视在工作中的自我价值实现，乐意帮助他人取得成功',
                                    u'渴望帮助他人，关心社会福祉，重视在工作中的自我价值实现，乐意帮助他人取得成功',
                                    None,
                                    u'不倾向于帮助他人，认为人可以自助，不太能从帮助他人中获得满足',
                                    u'不倾向于帮助他人，认为人可以自助，不太能从帮助他人中获得满足'],
                                u'权力/影响':
                                    [u'倾向于担任有影响力的职位并管理他人，能够承担责任',
                                    u'倾向于担任有影响力的职位并管理他人，能够承担责任',
                                    None,
                                    u'不追求工作中的权力、影响力及权威',
                                    u'不追求工作中的权力、影响力及权威'],
                                u'地位/职位':
                                    [u'关注自己所在的职位和在组织中的地位，当无法获得他人的尊重时会感觉低落',
                                    u'关注自己所在的职位和在组织中的地位，当无法获得他人的尊重时会感觉低落',
                                    None,
                                    u'不关注外在的职务、地位和身份认可 ',
                                    u'不关注外在的职务、地位和身份认可 '],
                                u'认可/表现':
                                    [u'希望在工作中得到肯定，失去同事的认可和关注可能会是一个打击',
                                    u'希望在工作中得到肯定，失去同事的认可和关注可能会是一个打击',
                                    None,
                                    u'更高的职位并不是那么重要，也不太关心职业发展前景是否良好',
                                    u'更高的职位并不是那么重要，也不太关心职业发展前景是否良好'],
                                u'艺术/文化':
                                    [u'认为和艺术或文化有关的工作非常理想，重视创作和自我表达的机会',
                                    u'认为和艺术或文化有关的工作非常理想，重视创作和自我表达的机会',
                                    None,
                                    u'关注实践和执行方面的工作，更看重实质内容而非外在表象，对文化艺术不太重视',
                                    u'关注实践和执行方面的工作，更看重实质内容而非外在表象，对文化艺术不太重视'],
                                u'变化/探索':
                                    [u'希望每一天的工作都是在解决全新的问题，对枯燥重复的工作内容感到厌倦',
                                    u'希望每一天的工作都是在解决全新的问题，对枯燥重复的工作内容感到厌倦',
                                    None,
                                    u'在多元多变的工作环境中会感到不安',
                                    u'在多元多变的工作环境中会感到不安'],
                                u'专业/技术':
                                    [u'对专业或技术导向的工作感兴趣，关注工作中提供的学习新知识或技能的机会',
                                    u'对专业或技术导向的工作感兴趣，关注工作中提供的学习新知识或技能的机会',
                                    None,
                                    u'工作是否符合自己的经历或专业并不重要，不关心学习新知识或专业技能的机会',
                                    u'工作是否符合自己的经历或专业并不重要，不关心学习新知识或专业技能的机会'],
                                u'自主/独立':
                                    [u'希望以自己的方式工作，过度的监督会影响工作表现',
                                    u'希望以自己的方式工作，过度的监督会影响工作表现',
                                    None,
                                    u'乐于听从指令及接受督导，缺乏明确指示会让其产生不安。',
                                    u'乐于听从指令及接受督导，缺乏明确指示会让其产生不安。'],
                                u'挑战/成就':
                                    [u'乐于克服各种困难及挑战，总是试图做得比别人更好，与他人之间的竞争关系会激发更好的工作表现',
                                    u'乐于克服各种困难及挑战，总是试图做得比别人更好，与他人之间的竞争关系会激发更好的工作表现',
                                    None,
                                    u'寻求适度而非巨大的挑战，不倾向于在充满竞争的环境中工作',
                                    u'寻求适度而非巨大的挑战，不倾向于在充满竞争的环境中工作']}
        dict_table_suggestion = {u"舒适/家庭":[
                                            [u"工作时间外，只在工作任务非常紧急的时候才联系他/她",u"在可调整的范围内，尽量为他/她提供舒适的工作环境",u"避免为他/她安排过多的工作任务，尽量不要占用他/她的私人时间",u"向他/她说明组织需要的是完成工作任务以及绩效，而不是工作的时间长度",u"鼓励并帮助他/她做好工作生活两方面的时间安排"],
                                            [u"工作时间外，只在工作任务非常紧急的时候才联系他/她",u"在可调整的范围内，尽量为他/她提供舒适的工作环境",u"避免为他/她安排过多的工作任务，尽量不要占用他/她的私人时间",u"向他/她说明组织需要的是完成工作任务以及绩效，而不是工作的时间长度",u"鼓励并帮助他/她做好工作生活两方面的时间安排"],
                                            None,
                                            [u"向他/她提供能够保持专注工作的环境和条件",u"为他/她安排足够的工作任务，确保有一定的工作量",u"向他/她提供有一定难度和挑战性的工作",u"和向他/她提供更多的休假相比，向其提供新领域的工作和学习机会，以及更好的职业发展渠道等激励手段可能会更有效"],
                                            [u"向他/她提供能够保持专注工作的环境和条件",u"为他/她安排足够的工作任务，确保有一定的工作量",u"向他/她提供有一定难度和挑战性的工作",u"和向他/她提供更多的休假相比，向其提供新领域的工作和学习机会，以及更好的职业发展渠道等激励手段可能会更有效"]],
                                u"安全/稳定":[
                                            [u"在组织发生变动时，及时与他/她沟通，确保他/她了解具体情况，说明组织变动对组织发展的重要性",u"建立完善的保险和福利制度，保障他/她收入的稳定",u"明确他/她的工作内容以及相应的职责范围",u"在给他/她安排工作任务时，及时与他/她进行沟通并尽可能提供明确具体的任务及计划安排"],
                                            [u"在组织发生变动时，及时与他/她沟通，确保他/她了解具体情况，说明组织变动对组织发展的重要性",u"建立完善的保险和福利制度，保障他/她收入的稳定",u"明确他/她的工作内容以及相应的职责范围",u"在给他/她安排工作任务时，及时与他/她进行沟通并尽可能提供明确具体的任务及计划安排"],
                                            None,
                                            [u"向他/她说明组织的发展状态，确保工作环境的变动在他/她可承受的范围内",u"鼓励他/她在完成自己职责范围内的工作后，自主拓展，承担更多的工作，提升个人能力",u"为他/她安排工作时，与他/她商讨确定工作目标，让他/她自主确定工作计划与安排",u"向他/她提供必要保险和福利"],
                                            [u"向他/她说明组织的发展状态，确保工作环境的变动在他/她可承受的范围内",u"鼓励他/她在完成自己职责范围内的工作后，自主拓展，承担更多的工作，提升个人能力",u"为他/她安排工作时，与他/她商讨确定工作目标，让他/她自主确定工作计划与安排",u"向他/她提供必要保险和福利"]],
                                u"经济/报酬":[
                                            [u"为他/她提供行业内具有竞争力的薪资",u"在激励他/她时，多考虑采用物质奖励的方式",u"当他/她工作表现优异时，确保他/她能够得到丰厚的奖金",u"注意在他/她加班或担负了额外的工作任务后向其提供相应的额外报酬"],
                                            [u"为他/她提供行业内具有竞争力的薪资",u"在激励他/她时，多考虑采用物质奖励的方式",u"当他/她工作表现优异时，确保他/她能够得到丰厚的奖金",u"注意在他/她加班或担负了额外的工作任务后向其提供相应的额外报酬"],
                                            None,
                                            [u"与他/她沟通，了解他/她所期望的激励方式",u"确保组织内经济报酬分配的公平合理性",u"尝试采用多种手段相结合的方式来评价他/她的工作表现",u"避免只通过薪资福利增长的方式来激励他/她"],
                                            [u"与他/她沟通，了解他/她所期望的激励方式",u"确保组织内经济报酬分配的公平合理性",u"尝试采用多种手段相结合的方式来评价他/她的工作表现",u"避免只通过薪资福利增长的方式来激励他/她"]],
                                u"归属/团队":[
                                            [u"在团队中，营造融洽和谐的工作氛围，培养他/她对团队的归属感",u"建议团队成员为他/她在工作领域的相关问题提供心理上的关爱和帮助",u"多为他/她安排需要与他人合作完成的工作任务",u"鼓励他/她参与团体建设活动，与同事、领导建立良好的关系"],
                                            [u"在团队中，营造融洽和谐的工作氛围，培养他/她对团队的归属感",u"建议团队成员为他/她在工作领域的相关问题提供心理上的关爱和帮助",u"多为他/她安排需要与他人合作完成的工作任务",u"鼓励他/她参与团体建设活动，与同事、领导建立良好的关系"],
                                            None,
                                            [u"避免过多关心他/她的私人生活",u"多为他/她安排个人可独立完成的工作任务",u"在他/她参与团队合作工作时，与他/她充分沟通，明确他/她个人承担的工作任务",u"在他/她参于集体活动时，强调集体活动对团队建设和发展的意义"],
                                            [u"避免过多关心他/她的私人生活",u"多为他/她安排个人可独立完成的工作任务",u"在他/她参与团队合作工作时，与他/她充分沟通，明确他/她个人承担的工作任务",u"在他/她参于集体活动时，强调集体活动对团队建设和发展的意义"]],
                                u"社交/人际":[
                                            [u"多给予他/她一些需要跨部门沟通的工作任务，并鼓励他/她在过程中不断提高自己沟通交流的能力",u"向他/她提供参加行业展会、外出交流的机会",u"为他/她提供机会，与行业内有影响的人交流沟通",u"鼓励他/她参加工作应酬，建立良好的工作人脉"],
                                            [u"多给予他/她一些需要跨部门沟通的工作任务，并鼓励他/她在过程中不断提高自己沟通交流的能力",u"向他/她提供参加行业展会、外出交流的机会",u"为他/她提供机会，与行业内有影响的人交流沟通",u"鼓励他/她参加工作应酬，建立良好的工作人脉"],
                                            None,
                                            [u"避免给予他/她过多交际应酬的工作任务",u"在他/她参与各类行业内交流活动时，引导他/她专注于专业知识的获取和学习",u"不强迫他/她参加工作应酬",u"鼓励他/她从达成工作目标角度出发，与他人相处，建立工作关系"],
                                            [u"避免给予他/她过多交际应酬的工作任务",u"在他/她参与各类行业内交流活动时，引导他/她专注于专业知识的获取和学习",u"不强迫他/她参加工作应酬",u"鼓励他/她从达成工作目标角度出发，与他人相处，建立工作关系"]],
                                u"利他/慈善":[
                                            [u"强调整个组织的工作最终能使整个世界变得更好",u"对于他/她帮助他人的行为，及时的给予认可和奖励",u"帮助他/她意识到自己的工作任务对他人和社会的积极影响",u"鼓励他/她多参与社会公益活动，并为他/她提供公益活动的相关资源和信息"],
                                            [u"强调整个组织的工作最终能使整个世界变得更好",u"对于他/她帮助他人的行为，及时的给予认可和奖励",u"帮助他/她意识到自己的工作任务对他人和社会的积极影响",u"鼓励他/她多参与社会公益活动，并为他/她提供公益活动的相关资源和信息"],
                                            None,
                                            [u"倡导个人的独立自主",u"避免通过他/她对他人的帮助来评价他/她的工作表现",u"不要求他/她关注公益慈善事业",u"鼓励他/她专注于自己本职工作又好又快的完成"],
                                            [u"倡导个人的独立自主",u"避免通过他/她对他人的帮助来评价他/她的工作表现",u"不要求他/她关注公益慈善事业",u"鼓励他/她专注于自己本职工作又好又快的完成"]],
                                u"权力/影响":[
                                            [u"适当放权，给予他/她担任项目负责人的工作机会，并在过程中不断的给予指导与支持",u"鼓励他/她勇敢表达自己的观点，采用一定的方法和策略说服和影响他人",u"重视他/她的合理建议，鼓励他/她参与决策并承担相应职责",u"确保他/她每隔一段时间都会有机会承担新的职责",u"明确他/她所期望的管理权限和职责范围"],
                                            [u"适当放权，给予他/她担任项目负责人的工作机会，并在过程中不断的给予指导与支持",u"鼓励他/她勇敢表达自己的观点，采用一定的方法和策略说服和影响他人",u"重视他/她的合理建议，鼓励他/她参与决策并承担相应职责",u"确保他/她每隔一段时间都会有机会承担新的职责",u"明确他/她所期望的管理权限和职责范围"],
                                            None,
                                            [u"多让他/她担任项目工作中的参与者，而不是组织者或管理者",u"避免为他/她安排分配和指导他人的工作任务",u"鼓励他/她通过团队的讨论形成决策",u"明确他/她的职业成长意愿，为他/她提供合适的上升道路"],
                                            [u"多让他/她担任项目工作中的参与者，而不是组织者或管理者",u"避免为他/她安排分配和指导他人的工作任务",u"鼓励他/她通过团队的讨论形成决策",u"明确他/她的职业成长意愿，为他/她提供合适的上升道路"]],
                                u"地位/职位":[
                                            [u"有意识的在各种场合，正面或侧面强调他/她在组织中的重要价值和地位",u"在他/她的工作环境中更多的强调职务和级别",u"关注组织在所属行业中的地位",u"强调他/她能为组织做出其他人无法做出的贡献"],
                                            [u"有意识的在各种场合，正面或侧面强调他/她在组织中的重要价值和地位",u"在他/她的工作环境中更多的强调职务和级别",u"关注组织在所属行业中的地位",u"强调他/她能为组织做出其他人无法做出的贡献"],
                                            None,
                                            [u"更多突出他/她在业务或技术方面取得的名声而不是职务级别",u"确保他/她的头衔更多的是关于技术或业务能力而不是管理级别",u"关注和赞扬他/她工作所得到的具体成果",u"避免仅用职位上的提升来激励他/她"],
                                            [u"更多突出他/她在业务或技术方面取得的名声而不是职务级别",u"确保他/她的头衔更多的是关于技术或业务能力而不是管理级别",u"关注和赞扬他/她工作所得到的具体成果",u"避免仅用职位上的提升来激励他/她"]],
                                u"认可/表现":[
                                            [u"鼓励他/她在自己擅长的领域培训和支持其他同事",u"确保他/她的优异工作表现得到同事和领导的认可和赞扬",u"每当他/她的工作最终被证明有效，不管用了什么方式和手段，都要强调其所具有的实用价值",u"鼓励他/她表达自己的观点，对于他/她提出的有建设性的观点，及时的给予支持和认可",u"不要过多赞扬他/她，会降低赞扬的效果"],
                                            [u"鼓励他/她在自己擅长的领域培训和支持其他同事",u"确保他/她的优异工作表现得到同事和领导的认可和赞扬",u"每当他/她的工作最终被证明有效，不管用了什么方式和手段，都要强调其所具有的实用价值",u"鼓励他/她表达自己的观点，对于他/她提出的有建设性的观点，及时的给予支持和认可",u"不要过多赞扬他/她，会降低赞扬的效果"],
                                            None,
                                            [u"是否得到充分的支持不会对他/她的工作动力产生太大的影响",u"尽量避免直接比较他/她和其它人的工作表现",u"建议他/她周围的人避免经常寻求他/她的协助或支持",u"避免仅通过对其工作表现的认可和表扬来激励他/她"],
                                            [u"是否得到充分的支持不会对他/她的工作动力产生太大的影响",u"尽量避免直接比较他/她和其它人的工作表现",u"建议他/她周围的人避免经常寻求他/她的协助或支持",u"避免仅通过对其工作表现的认可和表扬来激励他/她"]],
                                u"艺术/文化":[
                                            [u"有意识多为他/她安排与艺术相关联的工作任务",u"在确保工作结果的基础上，鼓励他/她发挥自己的创新能力，对工作流程进行优化",u"鼓励他/她不断提高自己的审美水平，在工作成果中体现他/她的审美能力，如PPT的制作等",u"在团队中，营造鼓励创新的氛围"],
                                            [u"有意识多为他/她安排与艺术相关联的工作任务",u"在确保工作结果的基础上，鼓励他/她发挥自己的创新能力，对工作流程进行优化",u"鼓励他/她不断提高自己的审美水平，在工作成果中体现他/她的审美能力，如PPT的制作等",u"在团队中，营造鼓励创新的氛围"],
                                            None,
                                            [u"少为他/她安排需要发挥创意和想象力的工作",u"鼓励他/她多参与具体执行操作的工作任务",u"为他/她安排工作任务时，明确具体的工作成果要求，不要求他/她在工作成果中体现他/她审美水平",u"避免通过他/她在工作中体现的创新能力来衡量他/她的工作表现"],
                                            [u"少为他/她安排需要发挥创意和想象力的工作",u"鼓励他/她多参与具体执行操作的工作任务",u"为他/她安排工作任务时，明确具体的工作成果要求，不要求他/她在工作成果中体现他/她审美水平",u"避免通过他/她在工作中体现的创新能力来衡量他/她的工作表现"]],
                                u"变化/探索":[
                                            [u"为他/她安排需要多部门合作的工作任务",u"避免让他/她承担过多重复性、枯燥的工作",u"在必须执行的重复性工作时鼓励他/她探索总结新的工作方式方法，提高工作效率",u"鼓励他/她在工作中，多方面拓展，了解行业内最前沿的信息和发展趋势"],
                                            [u"为他/她安排需要多部门合作的工作任务",u"避免让他/她承担过多重复性、枯燥的工作",u"在必须执行的重复性工作时鼓励他/她探索总结新的工作方式方法，提高工作效率",u"鼓励他/她在工作中，多方面拓展，了解行业内最前沿的信息和发展趋势"],
                                            None,
                                            [u"避免在没有任何外部支持的情况下要求他/她负责不熟悉的业务",u"多让他/她承担目标明确，步骤清晰的工作任务",u"鼓励他/她在完成重复性工作时，总结经验，优化工作方法",u"在他/她承担灵活变化的工作任务时，与他/她充分沟通，明确工作目标与任务结构，设定具体的执行路线"],
                                            [u"避免在没有任何外部支持的情况下要求他/她负责不熟悉的业务",u"多让他/她承担目标明确，步骤清晰的工作任务",u"鼓励他/她在完成重复性工作时，总结经验，优化工作方法",u"在他/她承担灵活变化的工作任务时，与他/她充分沟通，明确工作目标与任务结构，设定具体的执行路线"]],
                                u"专业/技术":[
                                            [u"关注他/她工作内容的专业性，多为他/她安排专业性上有挑战的工作任务",u"为他/她专业性的提高提供平台和资源支持",u"通过他/她完成任务是否符合专业标准来评价他/她的工作表现",u"重视专业人才，鼓励他/她在专业领域上精益求精，不断进步"],
                                            [u"关注他/她工作内容的专业性，多为他/她安排专业性上有挑战的工作任务",u"为他/她专业性的提高提供平台和资源支持",u"通过他/她完成任务是否符合专业标准来评价他/她的工作表现",u"重视专业人才，鼓励他/她在专业领域上精益求精，不断进步"],
                                            None,
                                            [u"与他/她沟通，了解他/她对工作内容专业性的期待",u"避免仅通过他/她在专业性上的进步和发展激励他/她",u"避免为他/她安排在专业性要求过高的工作任务",u"鼓励他/她多尝试多探索，找到自己希望发展的职业技能"],
                                            [u"与他/她沟通，了解他/她对工作内容专业性的期待",u"避免仅通过他/她在专业性上的进步和发展激励他/她",u"避免为他/她安排在专业性要求过高的工作任务",u"鼓励他/她多尝试多探索，找到自己希望发展的职业技能"]],
                                u"自主/独立":[
                                            [u"在确保工作任务能够保质保量完成的基础上，允许他/她自行安排工作方式，如：在家办公等",u"在确保工作结果的基础上，鼓励他/她在工作中尝试新的方式方法优化工作流程",u"为他/她安排工作任务时，共同商讨确定工作目标和时间节点，允许他/她自主安排工作进度",u"在能力范围内，为他/她提供自由、宽松的工作氛围"],
                                            [u"在确保工作任务能够保质保量完成的基础上，允许他/她自行安排工作方式，如：在家办公等",u"在确保工作结果的基础上，鼓励他/她在工作中尝试新的方式方法优化工作流程",u"为他/她安排工作任务时，共同商讨确定工作目标和时间节点，允许他/她自主安排工作进度",u"在能力范围内，为他/她提供自由、宽松的工作氛围"],
                                            None,
                                            [u"在公司内部，制定健全的工作规章制度",u"给予他/她明确的工作指示，并监督他/她的工作进程，即时给予反馈",u"避免为他/她安排需要自主管理的工作任务",u"对于他/她遵守公司规章制度，严格履行公司纪律的行为，给予奖励和认可"],
                                            [u"在公司内部，制定健全的工作规章制度",u"给予他/她明确的工作指示，并监督他/她的工作进程，即时给予反馈",u"避免为他/她安排需要自主管理的工作任务",u"对于他/她遵守公司规章制度，严格履行公司纪律的行为，给予奖励和认可"]],
                                u"挑战/成就":[
                                            [u"评估他/她的工作能力，多给予一些对他/她来说具有挑战性的工作任务",u"在他/她承担有一定难度的工作任务时，与他/她共同明确目标，确定工作计划与安排，并在过程中给予鼓励和资源支持",u"每当实现困难的目标时，都要向他/她祝贺成功，尤其是那些他/她亲自参与设定的目标",u"确保他/她不会因为自己设定超出规定范围、不切实际的目标而牺牲工作的基本质量"],
                                            [u"评估他/她的工作能力，多给予一些对他/她来说具有挑战性的工作任务",u"在他/她承担有一定难度的工作任务时，与他/她共同明确目标，确定工作计划与安排，并在过程中给予鼓励和资源支持",u"每当实现困难的目标时，都要向他/她祝贺成功，尤其是那些他/她亲自参与设定的目标",u"确保他/她不会因为自己设定超出规定范围、不切实际的目标而牺牲工作的基本质量"],
                                            None,
                                            [u"了解他/她所期望工作内容的困难程度",u"根据他/她以往的工作表现，为他/她安排工作能力范围内能承担的工作任务",u"避免通过对比他/她与他人的工作结果来评价他/她的工作表现",u"为他/她安排竞争性较小的工作任务"],
                                            [u"了解他/她所期望工作内容的困难程度",u"根据他/她以往的工作表现，为他/她安排工作能力范围内能承担的工作任务",u"避免通过对比他/她与他人的工作结果来评价他/她的工作表现",u"为他/她安排竞争性较小的工作任务"]]}

        frontname = settings.DATABASES['front']['NAME']
        sql_query = "select left(b.tag_value,2), sum(a.score) as score from\
            (select answer_id,answer_score score\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.answer_id=b.object_id and b.tag_id=54\
            and b.is_active=True group by left(b.tag_value,2)"

        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['wv2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())

            dictscore = {}
            dict_quota = {}
            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                for row in cursor.fetchall():
                    dictscore[row[0]]=row[1]
            
            dict_quota[u'舒适/家庭']=dictscore.get('SS',0.00)
            dict_quota[u'安全/稳定']=dictscore.get('AQ',0.00)
            dict_quota[u'经济/报酬']=dictscore.get('JJ',0.00)
            dict_quota[u'归属/团队']=dictscore.get('GS',0.00)
            dict_quota[u'社交/人际']=dictscore.get('SJ',0.00)
            dict_quota[u'利他/慈善']=dictscore.get('LT',0.00)
            dict_quota[u'权力/影响']=dictscore.get('QL',0.00)
            dict_quota[u'地位/职位']=dictscore.get('DW',0.00)
            dict_quota[u'认可/表现']=dictscore.get('RK',0.00)
            dict_quota[u'艺术/文化']=dictscore.get('YS',0.00)
            dict_quota[u'变化/探索']=dictscore.get('BH',0.00)
            dict_quota[u'专业/技术']=dictscore.get('ZY',0.00)
            dict_quota[u'自主/独立']=dictscore.get('ZZ',0.00)
            dict_quota[u'挑战/成就']=dictscore.get('TZ',0.00)
            sortedlist = sorted(dict_quota.items(), key=lambda d:d[1], reverse = True)  
            for tp in sortedlist:                
                ordict_quota['quota'].append(tp[0])
                ordict_quota['score'].append(tp[1]+5)
                idx = 1
                for member in liststd:
                    if tp[1] >= member:
                        dict_ranking[idx].append(tp[0])
                        dimension = dict_dimension_qutoa[tp[0]]
                        if not dimension in dict_detail[idx].keys():
                            dict_detail[idx][dimension]=[]
                        dict_detail[idx][dimension].append({'quota':tp[0],
                                                    'desc':dict_table_description[tp[0]],
                                                    'factor':dict_table_dimension[tp[0]][idx-1],
                                                    'suggestion':dict_table_suggestion[tp[0]][idx-1]})
                        break
                    idx += 1

        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS  

    def getLS2019(self, personal_result_id):

        dict_quota={}
        dict_ranking = {}
        dict_ranking[1]=[]
        dict_ranking[2]=[]
        dict_ranking[3]=[]

        default_data = {
            "report_type": "LS2019",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "scores":dict_quota,
                "ranks":dict_ranking,
                "behaviour":[]
            }}

        dict_quota[u'高压风格']={}
        dict_quota[u'权威风格']={}
        dict_quota[u'亲和风格']={}
        dict_quota[u'民主风格']={}
        dict_quota[u'模范风格']={}
        dict_quota[u'教练风格']={}

        dict_std = {u'高压风格':{12:100,11:100,10:97,9:95,8:90,7:88,6:74,5:57,4:47,3:28,2:8,1:0},
                    u'权威风格':{12:100,11:100,10:95,9:88,8:67,7:48,6:28,5:9,4:6,3:3,2:0,1:0},
                    u'亲和风格':{12:100,11:100,10:100,9:98,8:97,7:95,6:87,5:68,4:48,3:28,2:8,1:3},
                    u'民主风格':{12:98,11:96,10:88,9:74,8:58,7:30,6:17,5:9,4:6,3:4,2:0,1:0},
                    u'模范风格':{12:100,11:100,10:98,9:95,8:93,7:88,6:68,5:48,4:36,3:8,2:5,1:0},
                    u'教练风格':{12:98,11:95,10:88,9:68,8:37,7:18,6:8,5:4,4:2,3:0,2:0,1:0}}

        dict_table_dimension = {u'高压风格':[u'不断的给出命令，期望下属立刻服从。',
                                        u'密切的监督和控制下属的工作进程。',
                                        u'关注发现的问题，经常给出负面的、纠正性的反馈。',
                                        u'强调不服从所导致的负面后果来激发团队成员服从。'],
                                u'权威风格':[u'为团队制定和传达清晰的使命和方向',
                                        u'用清晰的目标激励员工，让他们清楚地认识到本岗位与组织总体愿景之间的联系。',
                                        u'会把宏大的愿景分解为个体的目标任务，并围绕组织愿景制定工作标准。',
                                        u'允许员工自由创新、尝试各种方法，并愿意承担可衡量的风险。'],
                                u'亲和风格':[u'提倡团队成员之间保持友好的关系。',
                                        u'关注团队成员的情感需求，而不是工作任务的指引、目标和标准。',
                                        u'追求员工的满意以及团队的和谐，通过与员工建立牢固的感情联系，获得员工强烈的忠诚。',
                                        u'避免与绩效相关的冲突，创造能带来积极反馈的机会。'],
                                u'民主风格':[u'愿意花时间听取集体意见，争取民意。',
                                        u'允许员工对自己的任务目标以及工作方式保留发言权。',
                                        u'通过组织许多会议来作出决策，希望通过深入讨论最终达成共识。'],
                                u'模范风格':[u'相信团队成员有能力为自己和团队确定合适的指引。',
                                        u'设定特别高的业绩标准，并且以身作则，亲自示范。',
                                        u'强迫自己更高质量、更快速地完成工作，而且要求别人跟他一样。',
                                        u'倾向于亲力亲为，独立完成工作任务，只有紧急任务时，才与他人协调。',
                                        u'在团队成员遇到问题时，提供详细的工作指引。'],
                                u'教练风格':[u'鼓励员工确定长期的职业发展目标，帮助制订明确的实施计划。',
                                        u'应用倾听技巧和开放性问题来鼓励团队成员解决自己的问题',
                                        u'擅长授权，会布置给员工挑战性的任务。',
                                        u'将错误视为学习机会，为了员工的成长愿意接受暂时的失败。']}

        frontname = settings.DATABASES['front']['NAME']
        sql_query = "select b.tag_value, sum(GREATEST(a.score,0)) as score from\
            (select answer_id,answer_score score\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.answer_id=b.object_id and b.tag_id=54\
            and b.is_active=True group by b.tag_value"

        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['ls2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())

            dictscore = {}
            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                for row in cursor.fetchall():
                    dictscore[row[0]]=row[1]
            
            dict_quota[u'高压风格']['pt']= dictscore['GY1']+dictscore['GY2']+dictscore['GY3']+dictscore['GY4']+dictscore['GY5']+dictscore['GY6']+dictscore['GY7']
            dict_quota[u'权威风格']['pt']= dictscore['QW1']+dictscore['QW2']+dictscore['QW3']+dictscore['QW4']+dictscore['QW5']+dictscore['QW6']+dictscore['QW7']
            dict_quota[u'亲和风格']['pt']= dictscore['QH1']+dictscore['QH2']+dictscore['QH3']+dictscore['QH4']+dictscore['QH5']+dictscore['QH6']
            dict_quota[u'民主风格']['pt']= dictscore['MZ1']+dictscore['MZ2']+dictscore['MZ3']+dictscore['MZ4']+dictscore['MZ5']+dictscore['MZ6']
            dict_quota[u'模范风格']['pt']= dictscore['MF1']+dictscore['MF2']+dictscore['MF3']+dictscore['MF4']+dictscore['MF5']+dictscore['MF6']
            dict_quota[u'教练风格']['pt']= dictscore['JL1']+dictscore['JL2']+dictscore['JL3']+dictscore['JL4']+dictscore['JL5']+dictscore['JL6']

            for key,value in dict_std.items():
                zscore = dict_std[key][dict_quota[key]['pt']]
                dict_quota[key]['zscore'] = zscore
                if zscore >= 60:
                    default_data["msg"]["behaviour"].extend(dict_table_dimension[key])
                    dict_ranking[1].append(key)
                elif zscore >= 40:
                    dict_ranking[2].append(key)
                else:
                    dict_ranking[3].append(key)
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS  

    def getPPSY2019(self, personal_result_id):
        dict_quota={}
        dict_quota[u'躯体反应']={}
        dict_quota[u'幻想行为']={}
        dict_quota[u'回避行为']={}
        dict_quota[u'自责行为']={}
        dict_quota[u'强迫行为']={}
        dict_quota[u'偏执心理']={}
        dict_quota[u'嫉妒心理']={}
        dict_quota[u'人际适应']={}
        dict_quota[u'孤独感受']={}
        dict_quota[u'依赖心理']={}
        dict_quota[u'猜疑心理']={}
        dict_quota[u'冲动控制']={}
        dict_quota[u'焦虑情绪']={}
        dict_quota[u'抑郁倾向']={}
        dict_quota[u'环境适应']={}
        dict_quota[u'恐惧心理']={}
        dict_quota[u'身心同一']={}
        dict_quota[u'社会称许性']={}        

        list_quota = [u'躯体反应',
                    u'幻想行为',
                    u'回避行为',
                    u'自责行为',
                    u'强迫行为',
                    u'偏执心理',
                    u'嫉妒心理',
                    u'人际适应',
                    u'孤独感受',
                    u'依赖心理',
                    u'猜疑心理',
                    u'冲动控制',
                    u'焦虑情绪',
                    u'抑郁倾向',
                    u'环境适应',
                    u'恐惧心理',
                    u'身心同一']


        dict_ranking = {}
        dict_ranking[1]=[]
        dict_ranking[2]=[]
        dict_ranking[3]=[]

        rank_table = [25.20,15]

        default_data = {
            "report_type": "PPSY2019",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "CompletionTime":"",
                "Validity":"",
                "scores":dict_quota,
                "ranks":dict_ranking,
            }}

        dict_table_dimension = {u'躯体反应':{10:u'<ul>一般来说，您具有良好的身体状态，可能的表现为：<li>精力充沛，具有较强的工作兴趣和较高的工作效率；</li><li>极少产生持久而强烈的身体疼痛感；</li><li>即使产生身体疲劳感，也能够通过休息很快恢复。</li></ul>',
                                            15:u'<ul>一般来说，您基本具有较好的身体状态，可能的表现为：<li>较少表现出明显的胃肠道症状，比如腹痛、腹胀、恶心、呕吐等；</li><li>较少表现出持久、严重且强烈的身体疼痛感；</li><li>较少表现出明显的身体疲劳感。</li></ul>',
                                            25:u'<ul>一般来说，您已经呈现出轻微的躯体症状，可能的表现为：<li>有时感到身体疲劳，浑身乏力；</li><li>有时感到腹痛、腹胀或感到恶心、呕吐；</li><li>有时郁郁寡欢，感到胸闷、气短；</li><li>身体的某些部位有时会有疼痛感，有时持久且强烈。</li></ul>',
                                            30:u'<ul>一般来说，您已经呈现比较明显的躯体症状，可能的表现为：<li>常表现出胃肠道症状，比如腹痛、恶心、腹胀、呕吐、打嗝、稀便等；</li><li>常表现出呼吸系统症状，比如气短、胸痛等；</li><li>常表现出自主神经兴奋症状，比如心悸、出汗、脸红、震颤等；</li><li>极易过度疲劳，常感到手脚沉重或无力感；</li><li>感觉到身体的疼痛感，有时持续、严重、强烈且突出。</li></ul>'},
                                u'回避行为':{10:u'<ul>一般来说，您是一个能积极面对困难和挑战的人。可能的表现为：<li>能坚定地专注于既定的目标，积极寻求解决任务的办法</li><li>能够用成熟的态度面对困难、挫折和失败</li><li>努力去改变现状，使情况向好的一面转化</li><li>极少受到失望、沮丧等负面情绪的影响</li><li>具有锲而不舍、不达目的决不罢休的决心</li></ul>',
                                            15:u'<ul>一般来说，您能够积极面对困难。可能的表现为：<li>能够关注既定目标的完成，寻求解决办法</li><li>能够面对困难、挫折和失败，少有回避倾向</li><li>较少受到失望、沮丧等负面情绪的影响</li><li>不会过分强调任务的困难和不可完成性</li></ul>',
                                            25:u'<ul>一般来说，您不太愿意直面困难和挑战。可能的表现为：<li>有时不能坦然面对现实环境，而是选择抱怨或逃避。</li><li>在困难和挑战面前，不愿付出努力，容易放弃</li><li>容易受到失望、沮丧的情绪影响</li><li>面对问题采取等待观望的态度</li></ul>',
                                            30:u'<ul>一般来说，您具有明显的回避困难、挫折和失败的倾向。可能的表现为：<li>不能坦然面对现实环境，经常报怨或逃避。</li><li>不能坚守既定的目标，缺乏自信，消极退缩</li><li>常常将潜在困难看得比实际上更严重，往往感到沮丧和失望</li><li>自甘落后，回避困难，得过且过</li></ul>'},
                                u'幻想行为':{10:u'<ul>一般说来，您是一位理性的、现实的人，能够正确的面对和应付困难。可能的表现为：<li>通常是现实主义者，不喜欢幻想，对现实持有清醒的认识；</li><li>能够正面的看待问题，并专注于问题解决</li><li>能理智地应付困难</li></ul>',
                                            15:u'<ul>一般说来，您比较理性，能够正确看待问题。可能的表现为：<li>很少幻想，对现实持有比较清醒的认识。</li><li>解决问题比较专注，不易受外部打扰</li></ul>',
                                            25:u'<ul>一般说来，您不太能够正确的面对问题和困难. 可能的表现为：<li>面对问题会产生一些不切实际的幻想</li><li>在处理问题时注意力不能集中，容易受外部干扰</li></ul>',
                                            30:u'<ul>一般说来，您在应对问题的方式不太成熟。可能的表现为：<li>不愿意正视问题的存在，经常沉迷于幻想而逃避现实的压力</li><li>在处理问题时经常性的分散注意力</li></ul>'},
                                u'自责行为':{10:u'<ul>一般来说，您在遇到挫折和困难时有较强的信心。可能的表现为：<li>能正确地认识自己，正面对待自己的经历</li><li>能够客观的评估自己的能力与不足</li><li>信任自己解决问题的能力，不轻易动摇</li></ul>',
                                            15:u'<ul>一般来说，您在遇到挫折和困难时比较有信心，可能的表现为：<li>比较能正确地认识自己，正面对待自己的经历</li><li>基本上能够客观的评估自己的能力，比较自信</li><li>信任自己解决问题的能力，不轻易动摇</li></ul>',
                                            25:u'<ul>一般来说，您在遇到挫折和困难时有责怪自己的倾向。可能的表现为：<li>对自己的困难和失败不能坦然接受，对自己的认识不够客观。</li><li>忽略自己的优势，夸大自己的缺陷，产生消极的自我评价。</li><li>难以正确对待自己的不足、并进行调整和修正。</li></ul>',
                                            30:u'<ul>一般来说，您在遇到挫折和失败时有明显的自责倾向。可能的表现为：<li>对自己的困难和失败不能坦然接受，完全否定自己。</li><li>认为自己能力不足而放弃解决问题的努力。</li><li>不能正确面对自己的不足，放弃进行调整和修正。</li></ul>'},
                                u'强迫行为':{10:u'<ul>一般说来，您非常理性，从不为毫无根据的想法而烦恼，也不会反复去做毫无意义的事情。可能的表现为：<li>不是充满疑虑的人，不会时刻担心细菌、病毒的侵入，也不会反复检查煤气管道、电源开关等物件；</li><li>可以有效地控制自己的思维活动，随时可以把那些奇怪的、荒谬的念头抛开；</li><li>行为举止很正常，没有任何需要反复进行否则就会感到焦虑的行为习惯或癖好；</li><li>对生活和工作的掌控能力比较强，不会夸大犯错的后果，也不会因此惴惴不安。</li></ul>',
                                            15:u'<ul>一般说来，您比较理性，很少为毫无根据的想法而烦恼，也很少反复去做毫无意义的事情。可能的表现为：<li>如果明知某些念头是荒谬的、不合理的，或者觉得某些行为是过分的、无关紧要的，会有意压抑这些念头、克制这些行为；</li><li>相信自己，对刚刚做完的事情比较放心，很少反复去检查；</li><li>可以有效地控制自己的思维活动，适时摆脱不必要的联想或回忆；</li><li>没有比较奇怪的生活习惯，也没有顽固而难以变通的行为风格；</li><li>对生活和工作的掌控能力比较强，很少会夸大犯错后果，也很少会因此惴惴不安。</li></ul>',
                                            25:u'<ul>一般说来，您相对理性，但有时可能为毫无根据的想法而烦恼，或者反复去做毫无意义的事情。可能的表现为：<li>明知某些念头是荒谬的、不合理的，或者觉得某些行为是过分的、无关紧要的，有时却无法压抑这些念头、克制这些行为；</li><li>可以比较有效地控制自己的思维活动，但有时摆脱不了某些不良的念头，也难以制止某些不必要的联想或回忆；</li><li>对自己信心不足，对那些刚刚做完的事情不够放心，经常去反复检查；</li><li>做事的方式比较固定，很少变通，可能存在比较奇怪的生活习惯。</li></ul>',
                                            30:u'<ul>一般说来，您已出现比较明显的强迫症症状，被某些不必要的念头、毫无意义的行为习惯所困扰，甚至痛苦万分。可能的表现为：<li>明知某些念头是荒谬的、不合理的，或者觉得某些行为是过分的、无关紧要的，却无法压抑这些念头或者克制这些行为；</li><li>缺乏自信，对自己做过的事情总是持怀疑态度，而需要反复检查才能安心；</li><li>难以有效地控制自己的思维活动，往往摆脱不了某些不良的念头，也难以制止某些不必要的联想或回忆，因此不仅很苦恼，而且严重影响了日常的工作与生活；</li><li>为人处世有固定的行为方式，会严格遵循某些套路，不知变通。</li></ul>'},
                                u'偏执心理':{10:u'<ul>一般来说，您是一位通情达理、灵活变通的人，有可能的表现为：<li>乐于信任别人，极少怀疑别人的动机和愿望；</li><li>心胸宽广，很少记恨别人，能够坦然宽容接受别人的过错；</li><li>对自己有清晰的认识，能客观评估自己的能力</li></ul>',
                                            15:u'<ul>一般来说，您通情达理，通常情况下也愿意信任别人。可能的表现为：<li>通常能够信任别人，较少对别人的动机产生疑虑；</li><li>心胸较为宽广，一般不会记恨别人；</li><li>多数情况下，能够积极正面的认识别人的行为和态度，乐于与别人建立良好关系；</li><li>对自己的认识比较清晰，很少高估自己的能力</li></ul>',
                                            25:u'<ul>一般来说，您已经表现出轻微的偏执倾向，有时敏感多疑、固执任性，可能的表现为：<li>有时敏感多疑，较多的信任自己，不轻易信任别人；</li><li>有时不能开放坦然的正确理解和认识别人友好的行为；</li><li>有时不能正确、客观地分析形势，有问题易从个人感情出发，主观片面性大；</li><li>对自己的能力有较高估计，自视甚高。</li></ul>',
                                            30:u'<ul>一般来说，您已经呈现比较明显的偏执倾向，敏感多疑、固执己见，甚至极易记恨，可能的表现为：<li>极度感觉过敏，对侮辱和伤害耿耿于怀，思想行为固执死板，敏感多疑、心胸狭隘；</li><li>过度的自信，且只信任自己，不信任别人；</li><li>过分警惕和抱有敌意，常将别人无意的、非恶意的甚至友好的行为误解为敌意或歧视，或无足够根据的怀疑会被人利用或伤害；</li><li>对自己的能力估计过高，在工作上往往言过其实。</li></ul>'},
                                u'嫉妒心理':{10:u'<ul>一般来说，您是一位心胸豁达，心态平和的人。可能的表现为：<li>对自己有清晰的认识，客观理性的评估自己的能力；</li><li>能够正确看待别人的长处和优点，并能由衷赞美别人的成绩和能力；</li><li>往往表现出热情、喜悦、生活充满动力，具有较高的工作效率；</li><li>极好的适应能力，能够坦然面对现实环境，以客观的态度面对现实，冷静地判断事实，理性地处理问题，并形成积极应变的心态。</li></ul>',
                                            15:u'<ul>一般来说，您的心胸较为豁达，心态较为平和。可能的表现为：<li>对自己的认识较为客观，很少高估自己的能力和价值；</li><li>一般能够认可别人的成绩和荣誉，不会贬低别人的能力和价值；</li><li>通常情况下，工作充满热情和动力，效率较高；</li></ul>',
                                            25:u'<ul>一般来说，您表现出轻微的嫉妒倾向，有时心胸不够豁达，心态不够平和。可能的表现为：<li>自我感觉良好，对自己能力和价值的评价较高；</li><li>有时不太认可别人的成绩和荣誉，不能客观的认识别人的能力和价值；</li><li>有时缺乏乐观向上的进取心，以致影响工作效率；</li></ul>',
                                            30:u'<ul>一般来说，您已经表现出明显的嫉妒倾向，心胸较为狭隘，心态不平衡。可能的表现为：<li>自我感觉非常好，过度高估自我价值和能力；</li><li>习惯否定别人的成绩和荣誉，同时贬低别人的能力和价值；</li><li>遇到他人优于自己的情境时，产生难以克制的痛苦感，即使是一点小事；</li><li>有时缺乏信心，丧失动力，工作积极性和效率明显降低。</li></ul>'},
                                u'人际适应':{10:u'<ul>一般说来，您是一个外向、热情、善解人意的人，不会在细节上纠缠不清，也不会自我封闭。可能的表现为：<li>心胸宽广，能够分辨别人说话的意图，对无心之言、玩笑话不会放在心上，更不会生气、愤恨；</li><li>非常自信，喜欢表达和展现自己，能够坦然面对别人的拒绝、冷落和负面评价；您待人宽厚，信任他人，不会仅仅从个人立场出发考虑问题；</li><li>心理能量很强大，乐观大方，能够从容、坦荡地与他人交往；</li><li>经常参加各种社交活动，乐意和别人打交道，并能以淡定的心态处理人际冲突或矛盾。</li></ul>',
                                            15:u'<ul>一般说来，您是一个比较外向、热情、善解人意的人，很少在细节上纠缠不清，也很少在社交活动上退缩。可能的表现为：<li>为人宽厚，通常能够分辨别人说话的意图，对无心之言、玩笑话不会放在心上，更不会生气、愤恨；</li><li>比较自信，往往喜欢表达和展现自己，能够坦然面对别人的拒绝、冷落和负面评价；</li><li>比较乐观大方，能顾及他人的感受，通常能够从容、坦荡地与他人交往；</li><li>乐于参加各种社交活动，愿意和别人打交道，通常情况下能以淡定的心态处理人际冲突或矛盾。</li></ul>',
                                            20:u'<ul>一般说来，您是一个相对大度、宽容、善解人意的人，但有时会在细节上纠缠不清，或者回避与他人的交往。可能的表现为：<li>心胸较为宽广，基本能够分辨别人说话的意图，对无心之言、玩笑话很少放在心上，也很少会生气、愤恨；</li><li>相对理性，但有时会把自己的想法投射到现实中，或者仅仅从个人立场出发考虑问题；</li><li>心理能量不够强大，自信心不足，一般情况下能够从容、坦荡地与他人交往；</li><li>在需要的时候您会出席各种社交场合，愿意和别人打交道，一般能以平常心处理人际冲突或矛盾。</li></ul>',
                                            25:u'<ul>一般说来，您不够大度、宽容和善解人意，有时会在细节上纠缠不清，或者刻意回避与他人的交往。可能的表现为：<li>心胸不够宽广，有时分辨不清别人说话的意图，因而把无心之言、玩笑话放在心上，甚至生气、愤恨；</li><li>比较感性，有时会把自己的想法投射到现实中，或者仅仅从个人立场出发考虑问题，情绪波动较大；</li><li>心理能量相对弱小，缺乏自信心，有时难以从容、坦荡地与他人交往；</li><li>对参加社交活动缺乏积极性，也很少主动和别人搭话，有时无法用平常的心态处理人际冲突或矛盾。</li></ul>',
                                            30:u'<ul>一般说来，您在人际关系方面比较敏感，拒绝与别人建立亲密的关系，因而带来种种困惑和苦恼。可能的表现为：<li>常常在细节上纠缠不清，或者刻意回避与他人的交往；</li><li>常常分辨不清别人说话的意图， 把无心之言、玩笑话放在心上，甚至生气、愤恨；</li><li>十分感性，经常会把自己的想法投射到现实中，或者把细微的东西过度放大，情绪容易波动；</li><li>心理能量比较弱小，骨子里比较自卑，常常难以从容、坦荡地与他人交往；</li><li>不愿意参加社交活动，极少主动和别人搭话，常常无法用平常的心态处理人际冲突或矛盾。</li></ul>'},
                                u'孤独感受':{10:u'<ul>一般说来，您具有强大的、持久的精神支持，如亲情、友谊、爱情、信仰、兴趣等，关心与爱护您的人很多。可能的表现为：<li>能够以愉悦的方式消磨自己的空闲时间，而不会有寂寞、无所事事的感受；</li><li>在遇到困难或者心情不好的时候，总是会有人帮助和安慰，有温暖、安心的感受；</li><li>通常具备良好的人际关系，可以得到较多社会资源和支持；</li><li>一个成熟、乐观的人，能积极应对竞争和压力、忍受拥挤和忙碌，以平和、恬淡的心态面对生活和工作。</li></ul>',
                                            15:u'<ul>一般说来，您具有稳固的、持久的精神支持，如亲情、友谊、爱情、信仰、兴趣等，关心与爱护您的人比较多。可能的表现为：<li>通常能够以愉悦的方式消磨自己的空闲时间，而很少有寂寞、无所事事的感受；</li><li>在遇到困难或者心情不好的时候，经常会有人帮助和安慰您，有温暖、安心感；</li><li>通常具备和谐的人际关系，可以得到一定的社会资源和支持；</li><li>往往是一个成熟、乐观的人，能以积极的态度应对竞争和压力、忍受拥挤和忙碌，并能较好地控制自己的情绪。</li></ul>',
                                            25:u'<ul>一般说来，您具有比较稳固的、持久的精神支持，如亲情、友谊、爱情、信仰、兴趣等，有一些关心与爱护您的人。可能的表现为：<li>往往能够以愉悦的方式消磨自己的空闲时间，但有时可能会产生寂寞、无聊、烦闷的感觉；</li><li>在遇到困难或者心情不好的时候，您往往可以找到合适的人帮助和安慰自己；</li><li>通常具备比较和谐的人际关系，可以得到一定的社会资源和支持；</li><li>比较成熟与乐观，基本上能以积极的态度应对竞争和压力、忍受拥挤和忙碌，并能合理地控制自己的情绪。</li></ul>',
                                            30:u'<ul>一般说来，您欠缺比较稳固的、持久的精神支持，如亲情、友谊、爱情、信仰、兴趣等，几乎没有关心与爱护您的人。可能的表现为：<li>往往以一个人独处的方式来消磨空闲时间，常常有寂寞、无聊、烦闷的感觉；</li><li>在遇到困难或者心情不好的时候，往往找不到合适的人来帮助和安慰自己，总觉得自己被周围人忽视或遗忘；</li><li>往往缺乏安全感，人际关系不是很好，难以得到充分的社会资源和支持；</li><li>容易悲观、情绪低落，经常以消极的态度应对竞争和压力、忍受拥挤和忙碌，有时无法适当地控制自己的情绪。</li></ul>'},
                                u'依赖心理':{10:u'<ul>一般来说，您具有较好的独立性、自主性和创造性，可能的表现为：<li>具有较强的理性思维，情绪控制能力较强，积极参与决策的讨论和制定；</li><li>客观理性的评价自己，积极肯定认可自我价值和优势；</li><li>以自己的价值取向和思维方式进行决策，不依附别人，也不受别人摆布；</li><li>尊重别人的思想和意志，不以自己的利益去驾驭别人的事，不以自己的意志束缚任何人；</li><li>在与别人交往中保持自身的独立性，并以个体的独立价值积极参与社会活动。</li></ul>',
                                            15:u'<ul>一般来说，您基本认可自我价值，具有一定的自主进取精神和独立意识。可能的表现为：<li>偏理性，能够控制自我情绪，并参与决策讨论和制定；</li><li>积极认可自我能力和自我价值；</li><li>不会对别人提出过多不合理的要求和期望；</li><li>不依附别人，对事物能够独立的进行判断和作出决策。</li></ul>',
                                            25:u'<ul>一般来说，您呈现出轻微的依赖倾向，有时缺乏独立意识，甚至自感无能。可能的表现为：<li>有时敏感多思，依恋别人，不太注意自己参与决策的能力；</li><li>有时缺乏自主性和创造性，需要作出决策时，需要征求大量的建议和保证；</li><li>有时自我贬低，认为别人比自己优秀，比自己有吸引力，比自己能干；</li><li>主动精神较弱，有时被动服从别人的愿望和要求，即使不够合理；</li><li>有时产生被人遗弃的想法和念头。</li></ul>',
                                            30:u'<ul>一般来说，您已呈现比较明显的依赖症状，缺乏活力，缺乏独立意识，甚至自感无能，可能的表现为：<li>在没有从别人处得到大量的建议和保证之前，对日常事物不能作出决策；</li><li>无助感，让别人为自己作大多数的重要决定，如在何处生活，该选择什么职业等；</li><li>深怕被人遗弃，一些基本目标常常只能在别人予以协助之下才能达到；</li><li>无独立性，很难单独展开计划或做事；</li><li>过度容忍，为讨好别人甘愿做低下的或自己不愿做的事；</li><li>缺乏自尊自重，把自己看作是毫无能力的、必须依附别人的人，经常通过自我贬低以求获得别人的帮助；</li><li>往往对别人有过多的不易被人理解的要求，在各方面总是寄希望于得到帮助和依靠。</li></ul>'},
                                u'猜疑心理':{10:u'<ul>一般说来，您是一位友善、合作的人，愿意相信别人。可能的表现为：<li>对他人的看法比较正面、积极，相信人性的善良，愿与他人协作；</li><li>信任别人，愿意和别人建立关系，没有充分的证据，极少怀疑别人的动机。</li><li>即使遇到不快，也能控制自己的情绪，而极少在语言和行为上攻击他人；</li><li>比较坦率和豁达，很少记仇，不会将负面情绪带入以后的工作中；</li></ul>',
                                            15:u'<ul>一般说来，您待人友好，具备较强合作性，通常情况下也愿意相信别人。可能的表现为：<li>对他人的看法相对积极和正面，相信别人有“善”的一面；</li><li>不大喜欢与别人争论，有了误解或矛盾，愿意心平气和地进行沟通；</li><li>多数时候能控制自己的情绪，以避免给工作和生活带来不良影响；</li><li>一般不会选择对抗，大体上信赖他人，很少捕风捉影，鲜有过度敏感之时；</li><li>通常愿意与别人建立友好的关系，很少对别人的动机心存疑虑。</li></ul>',
                                            25:u'<ul>一般说来，您待人相对友好，具备一定的合作性，但不大相信别人，有较强的戒备心。可能的表现为：<li>对他人的看法有时是消极和负面的，甚至认为多数时候人是冷漠自私的；</li><li>担心别人损害您的利益，可能出现过激情绪反应，并采取对抗排斥的应对方式；</li><li>有时过度敏感，并可能对某些人持有敌意和怀疑，并将这种态度保持一段时间。</li></ul>',
                                            30:u'<ul>一般说来，您是一位比较难相处的人，待人不够友善，不大愿意和别人亲近，合作性也比较差。可能的表现为：<li>对别人的看法往往是负面的和消极的，觉得人都是自私冷漠的</li><li>时刻保持警惕，对别人的言行举止的想法往往是过激的、甚至扭曲的；</li><li>常常难以控制自己的情绪，有过摔东西、撕文件等行为，并对别人恶言相向；</li><li>过于敏感，认为别人对自己存在敌意，甚至要故意伤害自己；</li><li>采取敌对的方式处理问题，给工作和人际交往制造了巨大的障碍。</li></ul>'},
                                u'焦虑情绪':{10:u'<ul>一般说来，您是一位从容镇定、乐观豁达、心情愉悦的人。可能的表现为：<li>能坦然面对各种压力，并能巧妙地、高效地解决各种问题；</li><li>对周围环境的掌控能力很强，对可能发生的事情有着准确的预期；</li><li>性格比较随和，擅长交际，并可能喜欢在公众场合表现自己；</li><li>身体健康，没有受到疾病、疼痛、不适、衰弱的困扰；</li><li>心态很好，淡泊名利，极少有偏激的想法或看法，对人对事都比较宽容；</li><li>往往按照惯常的方式做事，遵循既有的规则，时间管理能力也比较好，很少拖沓。</li></ul>',
                                            15:u'<ul>一般说来，您的焦虑水平较低，很少因为工作和生活方面的事情而烦躁不安，常常给人从容淡定的感觉。可能的表现为：<li>能冷静地面对各种问题，即使自己无法解决，也很少慌乱或害怕；</li><li>身体比较健康，即使稍有不适或病痛，也不会因此而苦恼；</li><li>自信心比较强，对自己内在价值的认同比较高，很少在上司或权威面前惊慌失措；</li><li>为人宽厚，善待别人，很少卷入名利之争，也很少有偏激的、扭曲的想法；</li><li>时间管理能力比较强，较少拖沓，即使没有及时完成工作任务，也会因开朗、豁达的性格而保持表面的镇静。</li></ul>',
                                            20:u'<ul>一般说来，您的焦虑水平中等，有时为工作和生活中的麻烦事而烦躁。可能的表现为：<li>尚能适当地应付各种压力，但有时可能惊慌失措，产生不良情绪，带来困扰；</li><li>身体相对健康，有时可能会担心身体的疾患与病痛；</li><li>自信水平一般，对不确定的事情心存疑虑，对上司或权威心存敬畏；</li><li>比较看重名利，有时会因为攀比、竞争而苦恼和担忧；</li><li>有时瞻前顾后，做事顾虑太多、犹豫不决，并可能陷入痛失良机的懊悔之中；</li><li>有时会延期完成任务，导致突击赶进度，并体验到一定程度的焦虑。</li></ul>',
                                            25:u'<ul>一般说来，您的焦虑水平较高，经常为工作和生活中的事情而烦恼，甚至担心受怕。可能的表现为：<li>能勉强应付各种问题，但有时力不从心，在压力面前你可能心情烦躁，采用拖拉、回避等消极方式来应对问题；</li><li>可能出现负面情绪，还可能出现头晕、胸闷、尿频、出汗等躯体症状，会因为身体的疾病、疼痛而苦恼不已；</li><li>往往不知道如何以确切的方式向合适的人寻求帮助，如果您是那种情绪外露的人，则可能向周围人散播焦虑的气氛；</li><li>可能觉得周围充满了不确定的因素，为了增强安全感，可能竭力争夺；</li><li>自我要求比较严格，有时对自身的能力、工作的进度把握不好，造成拖延，并因此体验到强烈的不安。</li></ul>',
                                            30:u'<ul>一般说来，您是一个非常容易焦虑的人，缺乏安全感和掌控感，甚至陷入长期的焦躁和不安之中。可能的表现为：<li>面对日常工作与生活的一些问题，您往往觉得力不从心、身心疲惫，不知道如何妥善应付；</li><li>有时您会无缘无故地觉得紧张，或者稍遇挫折就会情绪崩溃，给工作和生活带来严重的负面影响；</li><li>经常觉得身体不舒服，长期受到疾病、疼痛的困扰，严重的时候甚至产生绝望的念头；</li><li>即使您的工作能力很强，内心的力量也比较弱小，在很多场合您缺乏自信，也没有安全感；</li><li>可能时间管理能力比较差，没有固定的做事习惯和工作流程，总是匆匆忙忙地赶任务，并且难以保证任务完成的质量；</li><li>较难适当地表达和控制自己的情绪，对别人不够宽容，人际关系可能比较紧张；</li><li>对自己的评价可能不够准确，对自身的要求比较苛刻，在理想和现实之间难以找到平衡或妥协之处。</li></ul>'},
                                u'冲动控制':{10:u'<ul>一般来说，您是一位成熟理智而沉着冷静的人，待人比较友善。可能的表现为：<li>情绪状态非常稳定，极少出现突然的暴怒，情绪控制能力也较强；</li><li>行为比较慎重，倾向于规避风险，做事情顾及后果，很少冲动；</li><li>语言和思维能力正常，遇事能够冷静对待，并能很好的控制和调节语言举止；</li><li>头脑冷静，能够平心静气、毫无偏见地分析道理而不感情用事。</li></ul>',
                                            15:u'<ul>一般来说，您比较成熟理智，为人处世相对沉着冷静。可能的表现为：<li>情绪状态比较稳定，很少暴躁、发火；</li><li>通常情况下，行为较为谨慎，较少冲动，采取行动之前会考虑行为的后果；</li><li>一般遇事较为冷静，较好控制协调语言举止。</li></ul>',
                                            25:u'<ul>一般来说，您已经表现出轻微的冲动症状，情绪波动较大。可能的表现为：<li>有时情绪不够稳定，因一件小事而大发雷霆、大动干戈；</li><li>有时比较冲动，做事也常常忽略后果；</li><li>有时遇事不够冷静，意识狭隘，贸然行事，不能较好控制自己的语言举止。</li></ul>',
                                            30:u'<ul>一般来说，您已经表现出明显的冲动症状，常因微小刺激爆发强烈而难以控制的愤怒情绪，可能的表现为：<li>情绪控制不够稳定，往往突然暴怒，通常缺乏理智且带有盲目性；</li><li>稍不如意就怒火直冒、行为冲动，且不计后果和难以遏制；</li><li>事后对发作时的所作所为感到后悔，甚至自责，但不能防止失控冲动的再次发生，具有明显的阵发性特点；</li><li>在强烈的感情冲动期间，意识明显狭隘，认知片面、判断力下降、注意范围缩小，难以控制和调节语言举止。</li></ul>'},
                                u'抑郁倾向':{10:u'<ul>一般说来，您是一位开朗、愉悦、乐观的人，精神比较饱满，能以积极、平和的心态面对日常的工作与生活。可能的表现为：<li>极少情绪低落、悲观失望，而往往意气风发、笑容满面；</li><li>觉得生活很充实，有很多有趣的、值得做的事情，如交友、培养兴趣爱好等；</li><li>思维和语言功能正常，反应灵敏；</li><li>自信，并在一定程度上悦纳自己，觉得自己是一个有用的、有价值的人；</li><li>身体健康，饮食睡眠状况良好，精力也比较充沛；</li><li>喜欢与别人交往，人际关系良好，态度宽容、随和，经常给人阳光、活泼的感觉；</li><li>能坦然接受社会现实，即使遭遇挫折和打击，也能勇敢地面对。</li></ul>',
                                            15:u'<ul>一般说来，您是一位比较积极乐观、活泼开朗的人，能以适当的方式应对工作与生活中的各种问题。可能的表现为：<li>往往情绪状态良好，待人接物乐观积极，给别人愉悦、舒适的感觉；</li><li>愿意与别人交往，并得到别人的理解和帮助；</li><li>对身边的事物持有一定的兴趣，并有精力和体力参与各项活动；</li><li>很少悲观，对前途保有一些期望，对自己也比较有信心；</li><li>身体状况比较良好，没有遭受严重疾病、疼痛的侵袭，饮食睡眠也相对正常；</li><li>思维和意志功能比较正常，能够对环境和事件做出合理的判断；</li><li>受挫能力比较强，能坦然面对一般的压力，并妥善处理身边的问题。</li></ul>',
                                            25:u'<ul>一般说来，您的情绪有一定的波动，在处境顺利、心满意足时愉快、乐观，但在遭受挫折、面对困难时则可能悲观失望。可能的表现为：<li>易受环境的影响，有时会因为环境的变化而心情大变；</li><li>心情不好的时候不愿交往，甚至闭门不出，对既往的爱好也不屑一顾；</li><li>思维和意志功能比较正常，但沮丧的时候容易犯糊涂和走神；</li><li>不是非常自信，有时对前途感到迷惘，对近况感到失落；</li><li>有时会受到疾病、疼痛的困扰，如胸闷、肠胃不适、便秘等，</li><li>有时食欲不振，睡眠不佳，精神疲惫；</li><li>抗压能力一般，有时会在困难面前惊慌失措。</li></ul>',
                                            30:u'<ul>一般说来，您已呈现比较明显的抑郁症状，经常情绪低落、悲观失望，甚至产生厌世轻生的念头。可能的表现为：<li>常郁郁寡欢，对周围事物毫无兴趣，觉得生活是一种负担，有度日如年的感觉；</li><li>常身心疲惫，对工作缺乏热情，注意力难以集中，严重影响了工作效率；</li><li>觉得没有前途和希望，很不自信，怀疑自己的价值；</li><li>在人际交往方面消极被动，缺乏与人沟通的意愿；</li><li>思维能力有所下降，记忆力减退，行动也比较迟缓；</li><li>经常生病，饮食和睡眠状况比较差，有时性功能也遭到衰竭；</li><li>经常早醒，然后无法入睡，陷入悲哀的情绪之中，体重也有明显下降的趋势；</li><li>常感到焦虑，以批判、否定的态度看待自己，甚至有自罪观念。</li></ul>'},
                                u'环境适应':{10:u'<ul>一般说来，您的社会适应能力很强，能根据环境的变化、自身的发展来调整个人的需求，以积极的态度面对工作和生活中的困难。可能的表现为：<li>具备良好沟通技巧，能迅速和周围的人建立关系，甚至左右逢源、讨人喜欢；</li><li>非常理性，制定的计划切合实际，操作性强，容易被别人接受；</li><li>与环境保持适宜的接触，但不是只注重眼前利益的人；</li><li>能够忍受一时的挫折和痛苦，能延迟满足；</li><li>价值观与社会主流价值观趋同或者兼容，能对个人需求做适当的追求。</li></ul>',
                                            15:u'<ul>一般说来，您的社会适应能力较强，通常能根据环境的变化、自身的发展来调整个人的需求，以比较积极的态度面对工作和生活中的困难。可能的表现为：<li>具备较好的沟通技巧，能与周围人建立和谐的关系；</li><li>比较理性，制定的计划通常切合实际，操作性较强，容易被别人接受；</li><li>能够从失败中吸取教训，逐渐积累经验，做事比较坚持，能忍受一时挫折和痛苦；</li><li>价值观与社会主流价值观基本趋同或者兼容，能对个人需求做适当的追求。</li></ul>',
                                            25:u'<ul>一般说来，您的社会适应能力欠佳，有时难以根据环境的变化、自身的发展来调整个人的需求，态度也不够积极。可能的表现为：<li>欠缺较好的沟通技巧，不善与人交往，可能需要花很长时间才能融入新的环境；</li><li>有时冲动任性，想法过于单纯，提出的建议不切实际；</li><li>通常能够从失败中吸取教训，逐渐积累经验，但做事缺乏毅力，缺乏长远的眼光，比较容易感到困惑和苦闷；</li><li>价值观与社会主流价值观可能存在一些冲突，有时显得有些自私；</li><li>抗挫折能力不是很强，有时难以克制自己的负面情绪。</li></ul>',
                                            30:u'<ul>一般说来，您的社会适应能力严重不足，难以根据环境的变化、自身的发展来调整个人的需求，为人处世的态度也比较消极。可能的表现为：<li>欠缺基本的沟通技巧，不善与人交往，需要花很长时间才能融入新的环境；</li><li>往往冲动任性，想法过于单纯，提出的建议不切实际；</li><li>难以从失败中吸取教训，缺乏毅力，缺乏长远眼光，容易感到困惑和苦闷；</li><li>价值观与社会主流价值观存在较大的冲突，有时过于自私；</li><li>抗挫折能力比较差，经常难以克制自己的负面情绪。</li></ul>'},
                                u'恐惧心理':{10:u'<ul>一般说来，您是一位胆大的、泰然自若的人，遇事不慌不乱。可能的表现为：<li>在社交场合表现自如，即使有人盯着你看，也不会觉得不自在；</li><li>敢于在公众场合表达，甚至喜欢在大庭广众之下演讲或者表演；</li><li>没有什么场所或空间让您觉得害怕，可以镇定地出入各种场合；</li><li>没有任何“怕得要命”的东西，即使受了惊吓，也会很快恢复过来；</li><li>身体健康，极少出现胸闷、呼吸困难、晕厥，对生活和工作的把控能力很强。</li></ul>',
                                            15:u'<ul>一般说来，您的胆子比较大，遇事很少慌乱，比较镇定自若。可能的表现为：<li>没有因什么生活事件或事物受到严重惊吓而留下心理阴影；</li><li>可以在社交场合表现自如，比较轻松、愉快地和别人交流，但不大希望自己成为别人关注的焦点，否则您可能觉得浑身不自在；</li><li>对空旷的场地没有任何恐惧，对拥挤的、密闭的房间或交通工具也毫不害怕；</li><li>偶尔有一两样事物让您感到害怕，但程度并不深，恐惧的情绪消散得也比较快；</li><li>对生活和工作的把控能力比较强，相对自信一些。</li></ul>',
                                            25:u'<ul>一般说来，您的胆子比较小，有时过于敏感，工作与生活中那些不确定的因素往往让您忧心和焦虑。可能的表现为：<li>曾经受到比较严重的惊吓或羞辱，以致对某些事物或场合心有余悸，但尚能克服这种恐惧感；</li><li>在社交场合有时会觉得别扭、不舒服，与别人的交流也显得比较勉强；</li><li>可能害怕一个人去空旷的地方，或者对拥挤的、密闭的房间或交通工具心怀畏惧；</li><li>遇到困难的、自己无法掌控的事情时，有时会惊慌失措，甚至惊恐。</li></ul>',
                                            30:u'<ul>一般说来，您已经出现比较明显的恐惧症症状，对特定的事物或场景有着强烈的、不必要的恐惧，并伴随回避、退缩行为。可能的表现为：<li>可能对社交场合避而远之，觉得浑身不自在，难以和别人自然地交流；</li><li>往往不够自信，没有悦纳自己，或者对自己的要求过高，一旦觉得自己无法胜任工作或者应付某些问题，就会失望、痛苦和害怕；</li><li>可能害怕一个人去空旷的地方，或者对拥挤的、密闭的房间或交通工具心怀畏惧；</li><li>当恐惧袭来的时候，往往无法摆脱，感到绝望、崩溃，出现胸闷、脸色苍白、心悸等症状，甚至当场昏厥。</li></ul>'},
                                u'身心同一':{10:u'<ul>一般说来，您是一位现实主义者，有责任心，可信赖。可能的表现为：<li>认知、意志、运动等方面都很正常，没有出现病变或互不协调的情况；</li><li>情绪比较稳定，有同情心，往往比较热情，注重有距离的交往；</li><li>认同权威，尊敬真正有学问和能力的人，比较顺从；</li><li>人际关系比较好，待人随和，比较合群；</li><li>关心个人的成功和地位，对现实情况有清醒的认识，但在做决策时往往偏于保守；</li><li>有兴趣参加一些社会活动，并在工作中保持一定的主动性；</li><li>偶尔显得刻板，兴趣单调，缺乏想象力。</li></ul>',
                                            15:u'<ul>一般说来，您比较注重现实，有较强的责任心，值得周围人的信赖。可能的表现为：<li>认知、情绪、意志、运动、感觉等方面的功能都比较正常。</li><li>没有出现明显的病变或统合失调；</li><li>兴趣爱好相对广泛，愿意和别人建立亲密的关系，待人比较友善和礼貌；</li><li>喜欢具体的东西，也喜欢抽象思考，有时会和别人讨论，但往往固执己见；</li><li>对权威比较尊重，对上司相对顺从，有时显得保守一些，缺乏竞争意识；</li><li>情绪比较稳定，有时不善表达情感，甚至胆怯、怕羞。</li></ul>',
                                            25:u'<ul>一般说来，您比较理想主义，富有想象力，看法、理念常常与别人不同。可能的表现为：<li>心智功能都基本正常，有时可能出现暂时的思维错乱、情感反常和意志消沉；</li><li>兴趣爱好比较广泛，但注意力容易分散，往往缺乏毅力；</li><li>情绪有时波动较大，出现社会退缩，如突然变得对人冷淡、不愿和别人说话等；</li><li>比较喜欢抽象的东西，如哲理，但思考的内容别人往往难以理解；</li><li>往往不是责任心很强的人，对上司和权威的尊重、顺从相对有限；</li><li>在境遇不佳的时候，可能通过幻想或白日梦来回避现实。</li></ul>',
                                            30:u'<ul>一般说来，您已出现比较明显的精神分裂症症状，思想已经脱离现实环境，在认知、情绪、意志、运动、感觉等方面存在种种功能障碍。可能的表现为：<li>有时思维混乱、缺乏逻辑与目的性，或者觉得思维被别人控制了；</li><li>还可能出现一些妄想，如觉得有人想伤害您、身体某部分发生了奇异的变形、自己有高贵的血统等；</li><li>可能出现一些幻觉，如看到不存在的图像，或听到空气中有人对你说话；</li><li>性格比较孤僻，不愿和别人打交道，懒散，工作与生活的能力严重下降；</li><li>情感非常冷淡，经常面无表情，没有同情心，也难以理解别人的感受；</li><li>在别人看来，您经常做些奇怪的事情，甚至荒谬可笑。</li></ul>'}}

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
                people_result.report_url= settings.Reports['ppsy2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            duration = people_result.finish_time - people_result.begin_answer_time
            duration_in_s = duration.total_seconds()
            days    = divmod(duration_in_s, 86400)
            hours   = divmod(days[1], 3600)
            minutes = divmod(hours[1], 60)
            seconds = divmod(minutes[1], 1) 
            default_data["msg"]["CompletionTime"] = u"%d分%d秒" % (minutes[0], seconds[0])
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())

            dictscore = {}
            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                for row in cursor.fetchall():
                    dictscore[row[0]]=row[1]

            dict_quota[u'躯体反应']['pt']=dictscore['QT1']+dictscore['QT2']+dictscore['QT3']+dictscore['QT4']+dictscore['QT5']+dictscore['QT6']
            dict_quota[u'幻想行为']['pt']=dictscore['HX1']+dictscore['HX2']+dictscore['HX3']+dictscore['HX4']+dictscore['HX5']+dictscore['HX6']
            dict_quota[u'回避行为']['pt']=dictscore['HB1']+dictscore['HB2']+dictscore['HB3']+dictscore['HB4']+dictscore['HB5']+dictscore['HB6']
            dict_quota[u'自责行为']['pt']=dictscore['ZZ1']+dictscore['ZZ2']+dictscore['ZZ3']+dictscore['ZZ4']+dictscore['ZZ5']+dictscore['ZZ6']
            dict_quota[u'强迫行为']['pt']=dictscore['QP1']+dictscore['QP2']+dictscore['QP3']+dictscore['QP4']+dictscore['QP5']+dictscore['QP6']
            dict_quota[u'偏执心理']['pt']=dictscore['PZ1']+dictscore['PZ2']+dictscore['PZ3']+dictscore['PZ4']+dictscore['PZ5']+dictscore['PZ6']
            dict_quota[u'嫉妒心理']['pt']=dictscore['JD1']+dictscore['JD2']+dictscore['JD3']+dictscore['JD4']+dictscore['JD5']+dictscore['JD6']
            dict_quota[u'人际适应']['pt']=dictscore['RJ1']+dictscore['RJ2']+dictscore['RJ3']+dictscore['RJ4']+dictscore['RJ5']+dictscore['RJ6']
            dict_quota[u'孤独感受']['pt']=dictscore['GD1']+dictscore['GD2']+dictscore['GD3']+dictscore['GD4']+dictscore['GD5']+dictscore['GD6']
            dict_quota[u'依赖心理']['pt']=dictscore['YL1']+dictscore['YL2']+dictscore['YL3']+dictscore['YL4']+dictscore['YL5']+dictscore['YL6']
            dict_quota[u'猜疑心理']['pt']=dictscore['CY1']+dictscore['CY2']+dictscore['CY3']+dictscore['CY4']+dictscore['CY5']+dictscore['CY6']
            dict_quota[u'冲动控制']['pt']=dictscore['CD1']+dictscore['CD2']+dictscore['CD3']+dictscore['CD4']+dictscore['CD5']+dictscore['CD6']
            dict_quota[u'焦虑情绪']['pt']=dictscore['JL1']+dictscore['JL2']+dictscore['JL3']+dictscore['JL4']+dictscore['JL5']+dictscore['JL6']
            dict_quota[u'抑郁倾向']['pt']=dictscore['YY1']+dictscore['YY2']+dictscore['YY3']+dictscore['YY4']+dictscore['YY5']+dictscore['YY6']
            dict_quota[u'环境适应']['pt']=dictscore['HJ1']+dictscore['HJ2']+dictscore['HJ3']+dictscore['HJ4']+dictscore['HJ5']+dictscore['HJ6']
            dict_quota[u'恐惧心理']['pt']=dictscore['KJ1']+dictscore['KJ2']+dictscore['KJ3']+dictscore['KJ4']+dictscore['KJ5']+dictscore['KJ6']
            dict_quota[u'身心同一']['pt']=dictscore['SS1']+dictscore['SS2']+dictscore['SS3']+dictscore['SS4']+dictscore['SS5']+dictscore['SS6']
            dict_quota[u'社会称许性']['pt']=dictscore['SD1']+dictscore['SD2']+dictscore['SD3']+dictscore['SD4']+dictscore['SD5']+dictscore['SD6']

            if dict_quota[u'社会称许性']['pt']<=24:
                default_data["msg"]["Validity"] = u"回答较为真实，没有掩饰，结果可以相信。"
            else:
                default_data["msg"]["Validity"] = u"没有按照自身的实际情况作答，存在较多的饰好、伪装倾向，因此无法向您提供真实的、详尽的报告，请您抽时间重新参加测验。"

            for key in list_quota:                
                i = 1
                for pt in rank_table:
                    if dict_quota[key]['pt']>pt:
                        dict_ranking[i].append(key)
                        break
                    else:
                        i += 1
                sortedlist = sorted(dict_table_dimension[key].items(),key=lambda d:d[0])
                for level in sortedlist:
                    if dict_quota[key]['pt']<=level[0]:
                        dict_quota[key]['desc']=level[1]
                        break

        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS  

    def getPEOI2019(self, personal_result_id):

        dict_quota={}
        dict_quota[u'自主定向']={}
        dict_quota[u'意义寻求']={}
        dict_quota[u'自我悦纳']={}
        dict_quota[u'自我拓展']={}
        dict_quota[u'情绪调节']={}
        dict_quota[u'专注投入']={}
        dict_quota[u'亲和利他']={}
        dict_quota[u'包容差异']={}
        dict_quota[u'乐观积极']={}
        dict_quota[u'自信坚韧']={}
        dict_quota[u'合理归因']={}
        dict_quota[u'灵活变通']={}

        dict_ranking = {}
        dict_ranking[1]=[]
        dict_ranking[2]=[]
        dict_ranking[3]=[]
        dict_ranking[4]=[]

        default_data = {
            "report_type": "PEOI2019",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "scores":dict_quota,
                "ranks":dict_ranking,
            }}

        dict_std = {
            u"自主定向": {"avg": 62.64,"std": 18.09},
            u"意义寻求": {"avg": 74.13,"std": 18.87},
            u"自我悦纳": {"avg": 73.43,"std": 18.67},
            u"自我拓展": {"avg": 69.75,"std": 17.14},
            u"情绪调节": {"avg": 72.10,"std": 19.24},
            u"专注投入": {"avg": 66.86,"std": 18.92},
            u"亲和利他": {"avg": 60.94,"std": 16.80},
            u"包容差异": {"avg": 73.23,"std": 20.86},
            u"乐观积极": {"avg": 73.53,"std": 19.60},
            u"自信坚韧": {"avg": 71.59,"std": 21.68},
            u"合理归因": {"avg": 71.96,"std": 18.47},
            u"灵活变通": {"avg": 68.62,"std": 18.60}}

        rank_table = [2.28,6.69,15.86,30.85,50.5,69.15,84.13,93.31,97.7,100]

        dict_table_dimension = {u'乐观积极':{1:u'您对工作中的问题或生活中的得失的看法相当消极，在挫折和困境中往往会怀疑自己，对未来存在观望或悲观情绪，经常感到无助。',
                                            3:u'您对工作中的问题或生活中的得失的看法可能比较消极，在挫折和困境中倾向于怀疑自己，有时会对未来存在观望或悲观情绪，甚至感到无助。',
                                            7:u'您在多数情况下能从积极的角度看待存在的问题以及自己的得失，在挫折和困境中往往也能看到积极的一面，但有些时候也会受到负面信息的影响。',
                                            10:u'您倾向于从乐观正面的角度看待工作和生活中的问题和得失，即使在挫折和困境中也能看到积极的一面，对自己和未来充满希望，能够做好准备并付诸行动。'},
                                u'自信坚韧':{1:u'您经常低估自己的能力或高估工作任务的难度，不善于应对挑战和工作压力，或处理较高强度的工作。您需要相当长的时间才能从挫折和批评中恢复过来，重新投入到工作中。',
                                            3:u'您对自己的能力不太有信心，往往高估工作任务的难度。和大多数人相比，您不善于应对挑战和工作压力，或处理在短期内较高强度的工作。需要较长的时间才能从挫折和批评中恢复过来，重新投入到工作中。',
                                            7:u'您和大多数人一样相信自己的能力，能够应对大部分挑战和工作压力，并在短期内处理较高强度的工作。虽然会需要一些时间，您通常可以从挫折和批评中恢复过来，重新投入到工作中。',
                                            10:u'您比大多数人更相信自己的能力，可以更好的应对挑战和工作压力，长期处理较高强度的工作，或者接受短期内极大强度工作的挑战。您通常可以在较短时间内从挫折和批评中恢复过来，重新投入到工作中。'},
                                u'合理归因':{1:u'您很少能够从全面、发展、客观的角度分析和看待问题，思维方式经常过于具体或过度关注细节，往往只从某一个单一的角度看待问题。',
                                            3:u'您比较缺乏从全面、发展、客观的角度分析和看待问题的意识，往往会陷入过于具体或只针对问题某一个单独方面的思维方式中。',
                                            7:u'您有从全面、发展、客观的角度分析和看待问题的意识，但有时还是会陷入过于具体或只针对问题某一个单独方面的思维方式中。',
                                            10:u'您能够从全面、发展、客观的角度分析和看待问题，很少陷入过于具体或只针对问题某一个单独方面的思维方式中。'},
                                u'情绪调节':{1:u'您非常感性，经常会认为他人的批评是完全针对自己个人的。在面对持久的压力和或挫折时，不善于调节自身的情绪，难以维持正常的工作状态，也会在肢体语言上表现出明显的紧张。',
                                            3:u'您比较感性，有时会认为他人的批评是完全针对自己个人的。在面对持久的压力和或挫折时，不太能够调节自身的情绪，在维持正常的工作状态上有一定困难，也会在肢体语言上表现出明显的紧张。',
                                            7:u'您在一般情况下不会让情绪影响到理性思维，不倾向于认为他人的批评是完全针对自己个人的。在面对持久的压力和或挫折时，一定程度上能够调节自身的情绪，维持正常的工作状态，但有时会在肢体语言上表现出一定的紧张。',
                                            10:u'您比较理性，很少会让情绪影响理性思维，不会把他人的批评当成是完全针对自己个人的。您在面对持久的压力和或挫折时，基本上能够调节自身的情绪，维持正常的工作状态，也不太会在肢体语言上表现出紧张。'},
                                u'自主定向':{1:u'您可能对自己的发展方向和目标没有太多思考，面对选择时更多服从主流或权威的意见，在没有他人的管理和支持的情况下会显得无所适从。',
                                            3:u'您对自己的发展方向和目标思考较少，面对选择时比较倾向于服从主流或权威的意见，在没有他人的管理和支持的情况下可能会显得无所适从。',
                                            7:u'您把握自己生活和工作的发展方向和目标的能力和大多数人差不多，面对选择时多少都会受到外界的影响，但在大是大非的问题上还是能够坚持自己的标准，能够一定程度上在没有他人管理和支持的情况下完成工作。',
                                            10:u'您能够明确的把握自己生活和工作的发展方向和目标，面对选择时能够坚持自己的标准，不随大流、不人云亦云，相信自己的价值并不需要通过迎合他人来体现，在工作中不依赖他人的管理和支持。'},
                                u'意义寻求':{1:u'您很难从工作和生活中找到意义和价值，在达成目标的过程中，经常会受到外界因素的干扰，需要有外部监督。',
                                            3:u'您不太能够从工作和生活中找到意义和价值，在达成目标的过程中，容易被外界因素干扰，比较依赖外部的监督。',
                                            7:u'您能够一定程度上从工作和生活中寻求意义和价值，并付出一些努力去达成预设的目标，但有时会受到外界因素影响。',
                                            10:u'您能够主动地在工作和生活中寻求意义和价值，并有计划的通过各种努力来达成预设的目标。'},
                                u'专注投入':{1:u'您在处理工作时非常容易分心，缺乏计划性。您在大部分情况下不能保持注意力的集中，经常在工作中会出现虎头蛇尾的情况。',
                                            3:u'和大部分人相比，您在处理工作时专注度不够，也比较缺乏计划性。在任务不再新颖或不具有挑战性时，您很难保持注意力的集中，可能会出现虎头蛇尾的情况。',
                                            7:u'您能够在处理大部分工作时保证精力充沛，并能够在安排自己的工作计划上有一定的考虑。但在任务不再新颖或不具有挑战性时，您可能不太能够保持注意力的集中，不是特别胜任持续的常规或重复性工作。',
                                            10:u'您倾向于精力充沛地投入到任何工作事务中，并按优先级来安排自己的工作计划。即使当任务不再新颖或不具有挑战性时，您也能够保持注意力的集中，能够较好的胜任持续的常规或重复性工作。'},
                                u'自我拓展':{1:u'您在工作生活一般都会基于已有的经验做出判断，不倾向于学习新的知识和技能，缺少发展自身能力和潜力的意识。',
                                            3:u'您在工作生活中比较拘泥于已有的经验，很少作出一些尝试来发展、兑现自身的能力和潜力，比较缺乏提升自己的知识和技能的意识。',
                                            7:u'您能够一定程度上从工作和生活经验中学习，会作出一些尝试来发展、兑现自身的能力和潜力，在工作不太繁忙时，能够花一些时间提升自己的知识和技能。',
                                            10:u'您能够持续从工作和生活经验中学习并发展自身的能力，会作各种尝试以充分地兑现自己的潜力，不断提升自己的知识和技能，主动拥抱变化以得到新的经验。'},
                                u'灵活变通':{1:u'您看待事物的方式非常保守，明显的倾向于否定新奇的、非传统的观点和工作方法，维持现状。在身处快速变化，需要不断调整自身应对方式的环境时会感到明显的无所适从。',
                                            3:u'您看待事物的方式比较保守，往往会用怀疑的眼光来看待新奇的、非传统的观点和工作方法，倾向于维持现状。在身处快速变化，需要不断调整自身应对方式的环境时会感到无所适从。',
                                            7:u'您看待事物的方式和大多数人相同，能够接受部分新奇的、非传统的观点和工作方法，在必要时不会拘泥于维持现状。在身处快速变化，需要不断调整自身应对方式的环境时，需要一些时间来适应。',
                                            10:u'您倾向于用变化和多元的观点看待事物，能够接受新奇的、非传统的观点和工作方法，不倾向于维持现状。在身处快速变化，需要不断调整自身应对方式的环境时能够较好地适应。'},
                                u'包容差异':{1:u'人际交往中，您相当介意他人的不足或缺点，很容易给人留下待人严苛而不够包容的印象；经常只和观点相近的人进行交流，在与风格有差异的人合作时会遇到很多问题。',
                                            3:u'人际交往中，您可能比较介意他人的不足或缺点，有时会给人留下待人严苛而不够包容的印象；倾向于只和观点相近的人进行交流，不善于与风格有差异的人进行合作。',
                                            7:u'和大多数人一样，您能够正常的和他人建立起信任关系，在正常情况下不倾向于为非原则性的问题和他人对峙或冲突，能够一定程度上接受他人的不同意见和处事风格。',
                                            10:u'您表现出一种随和的气质，能够很快的和他人建立起信任关系，不会为非原则性的问题和他人对峙，较少发生人际冲突，大部分时候能够接受他人的不同意见和处事风格。当事情出错时，也不大容易发脾气或暴怒。'},
                                u'亲和利他':{1:u'人际交往中，您不关注他人的感受和需要，不会从他人的角度考虑问题，并且不倾向于帮助他人。',
                                            3:u'人际交往中，您可能对他人的感受和需要关注不多，不太会从他人的角度考虑问题，并且在他人没有明确提出需要时也不太会主动提供帮助和支持。',
                                            7:u'您待人和大多数人一样友善，对人比较开放而友好。虽然在和陌生人交往时可能不会表现的非常主动和热情，您仍然颇具合作精神、常常能够热心助人，并在自己能力范围内满足他人的合理要求。',
                                            10:u'和大多数人相比，您待人更友善，对人开放而友好，往往在交往的最初就表现的非常主动和热情。您极具合作精神、热心助人，倾向于努力满足他人的合理要求。'},
                                u'自我悦纳':{1:u'您看不到自身的长处，同时非常介意自身的缺点和不足，在大部分情况下都倾向于过低的评价自己。',
                                            3:u'您不太能够客观评价自身的长处，比较介意自身的缺点和不足，在遇到挫折和困难时倾向于过低的评价自己。',
                                            7:u'您基本能够客观评价自身的长处，并接受自身的缺点和不足，但在遇到较大的挫折和困难时可能会有过低评价自己的倾向。',
                                            10:u'您能够客观地评价自身的长处，并接受自身的缺点和不足，即使遇到较大的挫折和困难也不会过低的评价自己'}}
        frontname = settings.DATABASES['front']['NAME']
        sql_query = "select b.tag_value ,sum(a.score) as score from\
            (select question_id,answer_score score\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.question_id=b.object_id and b.tag_id=54\
            and b.is_active=True group by b.tag_value"

        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['peoi2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())

            dictscore = {}
            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]                
                for row in cursor.fetchall():
                    dictscore[row[0]]=row[1]
            
            dict_quota[u'自主定向']['pt']=(dictscore['N1']+dictscore['N2'])*25.00/2
            dict_quota[u'意义寻求']['pt']=(dictscore['N3']+dictscore['N4'])*25.00/2
            dict_quota[u'自我悦纳']['pt']=(dictscore['N5']+dictscore['N6'])*25.00/2
            dict_quota[u'自我拓展']['pt']=(dictscore['N7']+dictscore['N8'])*25.00/2
            dict_quota[u'情绪调节']['pt']=(dictscore['N9']+dictscore['N10'])*25.00/2
            dict_quota[u'专注投入']['pt']=(dictscore['N11']+dictscore['N12'])*25.00/2
            dict_quota[u'亲和利他']['pt']=(dictscore['N13']+dictscore['N14'])*25.00/2
            dict_quota[u'包容差异']['pt']=(dictscore['N15']+dictscore['N16'])*25.00/2
            dict_quota[u'乐观积极']['pt']=(dictscore['N17']+dictscore['N18'])*25.00/2
            dict_quota[u'自信坚韧']['pt']=(dictscore['N19']+dictscore['N20'])*25.00/2
            dict_quota[u'合理归因']['pt']=(dictscore['N21']+dictscore['N22'])*25.00/2
            dict_quota[u'灵活变通']['pt']=(dictscore['N23']+dictscore['N24'])*25.00/2

            for key,value in dict_std.items():                
                zscore=(dict_quota[key]['pt']-value['avg'])*1.00/value['std']
                dict_quota[key]['cdf']=round(normsdist(zscore)*100.00,2)
                i = 1
                for pt in rank_table:
                    if dict_quota[key]['cdf']<=pt:
                        dict_quota[key]['rank']=i
                        break
                    else:
                        i += 1
                sortedlist = sorted(dict_table_dimension[key].items(),key=lambda d:d[0])
                i = 1
                for level in sortedlist:
                    if dict_quota[key]['rank']<=level[0]:
                        dict_quota[key]['desc']=level[1]
                        dict_ranking[i].append(key)
                        break
                    else:
                        i += 1
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS  

    def getMC2019(self, personal_result_id):

        list_quotas = [u"变革推动",u"创新优化",u"客户导向",u"跨界协同",u"团队领导",u"勇于承担",u"正直诚信",u"资源整合",u"系统思维",u"积极进取"]
        dict_score_level = {4.0:'H',2.5:'M',0.0:'L'}
        dict_score_quota_self = {u"变革推动":0.00,u"创新优化":0.00,u"客户导向":0.00,u"跨界协同":0.00
                                ,u"团队领导":0.00,u"勇于承担":0.00,u"正直诚信":0.00,u"资源整合":0.00
                                ,u"系统思维":0.00,u"积极进取":0.00}
        dict_score_quota_others = {u"变革推动":0.00,u"创新优化":0.00,u"客户导向":0.00,u"跨界协同":0.00
                                  ,u"团队领导":0.00,u"勇于承担":0.00,u"正直诚信":0.00,u"资源整合":0.00
                                  ,u"系统思维":0.00,u"积极进取":0.00}
        dict_score_behaviour_self = {u"处事公平公正":0.00,
                                u"打造创新机制及氛围":0.00,
                                u"多形式学习交流":0.00,
                                u"敢于尝试持续创新":0.00,
                                u"敢于当面直谏":0.00,
                                u"高效合理授权":0.00,
                                u"管理阻抗":0.00,
                                u"过程管控与跟踪":0.00,
                                u"捍卫变革":0.00,
                                u"换位思考，促进协作":0.00,
                                u"换位思考，构建解决方案":0.00,
                                u"会付出额外的努力":0.00,
                                u"积极寻求解决办法,坚持不懈":0.00,
                                u"建立合作机制，实现效能最大化":0.00,
                                u"借鉴经验，快速有效优化":0.00,
                                u"理解变革":0.00,
                                u"理解高效团队的重要性":0.00,
                                u"理解其他部门需求及利益":0.00,
                                u"明确职责，主动承担责任":0.00,
                                u"前瞻性分析":0.00,
                                u"倾听并及时反馈":0.00,
                                u"塑造团队文化":0.00,
                                u"调解冲突，达致双赢":0.00,
                                u"挺身而出，成为依靠":0.00,
                                u"为自己设置挑战性目标":0.00,
                                u"问题发现及分析":0.00,
                                u"协调资源超越期望":0.00,
                                u"形成固有并可持续的模式 ":0.00,
                                u"言行一致遵守承诺":0.00,
                                u"以目标为导向，完成工作":0.00,
                                u"有责无疆，积极推进":0.00,
                                u"原因识别及构建解决方案":0.00,
                                u"愿景塑造":0.00,
                                u"主动共享信息 ":0.00,
                                u"主动关注提升满意度":0.00,
                                u"主动关注新事物":0.00,
                                u"主动争取和协调资源 ":0.00,
                                u"转变思维，扩展资源渠道 ":0.00,
                                u"自我激发,从内心寻求动力":0.00,
                                u"做事规范坦率真诚":0.00}
        dict_score_behaviour_others = {u"处事公平公正":0.00,
                                u"打造创新机制及氛围":0.00,
                                u"多形式学习交流":0.00,
                                u"敢于尝试持续创新":0.00,
                                u"敢于当面直谏":0.00,
                                u"高效合理授权":0.00,
                                u"管理阻抗":0.00,
                                u"过程管控与跟踪":0.00,
                                u"捍卫变革":0.00,
                                u"换位思考，促进协作":0.00,
                                u"换位思考，构建解决方案":0.00,
                                u"会付出额外的努力":0.00,
                                u"积极寻求解决办法,坚持不懈":0.00,
                                u"建立合作机制，实现效能最大化":0.00,
                                u"借鉴经验，快速有效优化":0.00,
                                u"理解变革":0.00,
                                u"理解高效团队的重要性":0.00,
                                u"理解其他部门需求及利益":0.00,
                                u"明确职责，主动承担责任":0.00,
                                u"前瞻性分析":0.00,
                                u"倾听并及时反馈":0.00,
                                u"塑造团队文化":0.00,
                                u"调解冲突，达致双赢":0.00,
                                u"挺身而出，成为依靠":0.00,
                                u"为自己设置挑战性目标":0.00,
                                u"问题发现及分析":0.00,
                                u"协调资源超越期望":0.00,
                                u"形成固有并可持续的模式 ":0.00,
                                u"言行一致遵守承诺":0.00,
                                u"以目标为导向，完成工作":0.00,
                                u"有责无疆，积极推进":0.00,
                                u"原因识别及构建解决方案":0.00,
                                u"愿景塑造":0.00,
                                u"主动共享信息 ":0.00,
                                u"主动关注提升满意度":0.00,
                                u"主动关注新事物":0.00,
                                u"主动争取和协调资源 ":0.00,
                                u"转变思维，扩展资源渠道 ":0.00,
                                u"自我激发,从内心寻求动力":0.00,
                                u"做事规范坦率真诚":0.00}
        analyis_self = {}
        analyis_others = {}
        advices = {}
        dict_potrait = {u"潜能区":[],u"优势共识区":[],u"待发展共识区":[],u"盲点":[]}
        dict_analysis = {u"自我评价相对优势能力":[],u"他人评价相对优势能力":[],u"自我评价相对劣势能力":[],u"他人评价相对劣势能力":[]}
        dict_behaviour_question = {"B29":u"处事公平公正",
                                "B05":u"打造创新机制及氛围",
                                "B17":u"多形式学习交流",
                                "B06":u"敢于尝试持续创新",
                                "B30":u"敢于当面直谏",
                                "B18":u"高效合理授权",
                                "B01":u"管理阻抗",
                                "B21":u"过程管控与跟踪",
                                "B02":u"捍卫变革",
                                "B13":u"换位思考，促进协作",
                                "B09":u"换位思考，构建解决方案",
                                "B39":u"会付出额外的努力",
                                "B40":u"积极寻求解决办法,坚持不懈",
                                "B14":u"建立合作机制，实现效能最大化",
                                "B07":u"借鉴经验，快速有效优化",
                                "B03":u"理解变革",
                                "B19":u"理解高效团队的重要性",
                                "B15":u"理解其他部门需求及利益",
                                "B25":u"明确职责，主动承担责任",
                                "B22":u"前瞻性分析",
                                "B10":u"倾听并及时反馈",
                                "B20":u"塑造团队文化",
                                "B16":u"调解冲突，达致双赢",
                                "B26":u"挺身而出，成为依靠",
                                "B37":u"为自己设置挑战性目标",
                                "B23":u"问题发现及分析",
                                "B11":u"协调资源超越期望",
                                "B33":u"形成固有并可持续的模式 ",
                                "B31":u"言行一致遵守承诺",
                                "B27":u"以目标为导向，完成工作",
                                "B28":u"有责无疆，积极推进",
                                "B24":u"原因识别及构建解决方案",
                                "B04":u"愿景塑造",
                                "B34":u"主动共享信息 ",
                                "B12":u"主动关注提升满意度",
                                "B08":u"主动关注新事物",
                                "B35":u"主动争取和协调资源 ",
                                "B36":u"转变思维，扩展资源渠道 ",
                                "B38":u"自我激发,从内心寻求动力",
                                "B32":u"做事规范坦率真诚"}

        dict_quota_advice = \
                    {u"正直诚信":[u"规章制度是促进公司正常有序运行的基础，需要加强遵守规范制度的自觉性，以及互动中坦率真诚的意识",
                                u"诚信是做人之根本，是人际关系建立的基础，加强言出必行的意识，做到言行一致才能赢得他人的尊重和信任",
                                u"公平公正是员工最期望领导者具备的素质之一。加强自身在制定决策、处理问题上的公正性，努力规避个人情感因素的影响，即可赢得下属的尊重，也是表现自己领导风范的一次机会",
                                u"加强维护利益、坚持组织原则的意识，发现内外勾结等情况时，勇于向上反映"],
                    u"勇于承担":[u"加深对工作职责的理解，培养工作主动性及承担困难任务的意识",
                                u"加强对本职岗位工作职责的认识，不清晰的地方可以找相关人员询问清楚",
                                u"增强以实现战略目标为工作导向的意识，主动承担责任，出色完成工作",
                                u"开展工作之前，不妨先想一下需要达成或实现的目标，从目标往回拆分工作任务",
                                u"遇到困难挫折，不要轻言放弃，坚持一下说不定会有不一样的结果",
                                u"淡化职责边界意识，积极协调、推进相关部门共同协作，确保任务完成",
                                u"公司是个人的载体，公司的利益应高于个人利益，作为团队的领航者，您需要在危机时刻主动站出，成为大家找出方向的依靠"],
                    u"创新优化":[u"加强对行业内/市场上新事物、新技术、新方法的敏锐度和关注度",
                                u"主动从竞争对手、内外部客户反馈中发现借鉴价值，并对其进行一定的优化/微创新，提升工作效率",
                                u"借鉴他人在工作上的经验，结合当前行业内的新技术，进行深入的分析，总结尝试过程中的经验教训",
                                u"在团队中鼓励员工进行各方面（如，工作方法）的优化创新，并定期组织经验分享会，树立强烈的创新氛围"],
                    u"客户导向":[u"了解客户真实需求和感受是提供优质客户服务的基础，耐心倾听、了解客户感受，主动将顾客体验反馈给相关人员",
                                u"主动站在客户的角度，充分考虑其需求和期望利益，以最快的速度给予问题反馈和解决",
                                u"加强协调并善用内外部资源，挖掘客户更深层的需求，以满足/超越客户原有的期望，树立的良好形象",
                                u"主动关心客户，了解其当前的困难和发展需求，给予适当的帮助和服务，以确保客户满意度的不断提高"],
                    u"跨界协同":[u"仔细梳理的组织架构，主动向上级/各部门管理者了解不同职能部门的需求和利益",
                                u"理解其他部门的工作流程和工作量，以其他部门角度来看待问题，促进双方共同协作",
                                u"主动了解部门内外冲突的原因，平衡各方的利益，通过双赢的方式解决冲突",
                                u"主动进行各部门间的沟通，共同探讨如何平衡部门间决策的相互影响，以确保达成合作机制"],
                    u"团队领导":[u"总结过往工作中，不同运作效率的团队对部门目标达成的作用，加强对团队的运作效率的了解和支持",
                                u"结合员工的能力现状和工作任务内容才能做到人岗匹配，达到效能的最大化，授权之后也不代表我们领导者工作的结束，还需要进行及时的跟进辅导，才能确保各项工作任务的有序开展",
                                u"为了提升团队的整体效能，作为团队的领导者，很有必要为团队创造多种形式的交流、分享、学习的平台，促进整个团队能力提升",
                                u"确定团队文化的方向，并积极的宣导团队愿景，巩固团队的凝聚力，激发团队自主效率"],
                    u"变革推动":[u"如有可能，可以争取与高层沟通的计划，讨论推动变革的深层原因，加深对变革必要性和收益的理解",
                                u"站在尽可能高的战略角度，为变革做出全局的规划，然后再层层细化，确定变革愿景达成过程中需要每个人付出的努力",
                                u"准备专门的幻灯片或其他材料，为团队成员系统梳理变革的必要性，以及每一位成员在变革中的价值所在，并解答大家可能提出的疑惑",
                                u"为变革设计和运行一个正规的流程，有利于督促自己担当变革推动者的角色，也有利于推动变革的努力取得效果"],
                    u"系统思维":[u"积极去发现工作中出现的问题，不回避问题，并运用多种思维方式来分析问题的成因和解决办法",
                                u"不局限于问题的表面，努力去分析问题的本质原因，以解决问题根源为导向来构建问题解决方案",
                                u"在问题解决过程中，紧密跟踪问题的状态与事态的发展，及时的调整问题解决方案，以快速有效的解决问题为目标",
                                u"主动去了解本行业发展趋势和动态，基于经验和知识对业务发展做出预判，并积极针对预判构建备选方案，以确保业务或流程的顺畅推进"],
                    u"资源整合":[u"信息的传播与共享能够促进组织效率的提升。您可以尝试在公司内部设立资源共享平台，提高自身及他人信息传播的意识，推动各职能部门协调效率的提升",
                                u"客户需求的满足离不开组织内部的共同协作，这就意味着您不仅仅要善用现有资源，同时要争取并协调其他部门资源。因此您可能需要加强对各部门利益的了解，确保客户需求满足",
                                u"市场发展的变化瞬息万变，您在工作中可通过行业报告等途径了解行业最新动态，转变思维模式",
                                u"对于企业来说，不断拓展资源渠道是至关重要的。主动在工作中寻求多方合作对象，认真筛选，推动组织资源的整合效应",
                                u"资源整合是组织发展的必然趋势，首先您需要清晰并坚持组织在目标医院的战略规划，其次您需要从长远的角度考量不同资源相互协调配合所产生的效益，以打造提升组织效能的资源体系；"],
                    u"积极进取":[u"需要主动走出自身的舒适区，尝试对自身提出更高的要求和挑战。",
                                u"需要更多从任务本身发现乐趣，并以此来激励自己全情投入，而不要过于看重来自外部的激励。",
                                u"面对完成任务中的困难和挑战，需要你更多的坚持和投入，有时成功来自于对最后一米的坚持。"]}

        dict_quota_behaviour = {u"正直诚信":[u"做事规范坦率真诚",u"言行一致遵守承诺",u"处事公平公正",u"敢于当面直谏"],
                        u"勇于承担":[u"明确职责，主动承担责任",u"以目标为导向，完成工作",u"有责无疆，积极推进",u"挺身而出，成为依靠"],
                        u"创新优化":[u"主动关注新事物",u"借鉴经验，快速有效优化",u"敢于尝试持续创新",u"打造创新机制及氛围"],
                        u"客户导向":[u"倾听并及时反馈",u"换位思考，构建解决方案",u"协调资源超越期望",u"主动关注提升满意度"],
                        u"跨界协同":[u"理解其他部门需求及利益",u"换位思考，促进协作",u"调解冲突，达致双赢",u"建立合作机制，实现效能最大化"],
                        u"团队领导":[u"理解高效团队的重要性",u"高效合理授权",u"多形式学习交流",u"塑造团队文化"],
                        u"变革推动":[u"理解变革",u"愿景塑造",u"管理阻抗",u"捍卫变革"],
                        u"系统思维":[u"问题发现及分析",u"原因识别及构建解决方案",u"过程管控与跟踪",u"前瞻性分析"],
                        u"资源整合":[u"主动共享信息 ",u"主动争取和协调资源 ",u"转变思维，扩展资源渠道 ",u"形成固有并可持续的模式 "],
                        u"积极进取":[u"为自己设置挑战性目标",u"自我激发,从内心寻求动力",u"会付出额外的努力",u"积极寻求解决办法,坚持不懈"]}

        dict_quota_desc = {u"变革推动":u"能够积极识别和寻求变革的机会和阻力，并为取得建设性的、有益的结果激发变革共识、制定系统计划并主导推进和有效地控制变化。",
                        u"创新优化":u"敢于打破常规，接纳并进行主动创新，善于从不同的角度提出新颖的问题解决方法,推进问题得到改善。",
                        u"积极进取":u"能够从自我价值实现的角度设置高标准、具有挑战性的目标，不断自我激励，寻求各种方法努力获得成功。",
                        u"客户导向":u"能够积极关注并有效识别客户的真实需求，采取有效行动并建立良好的客户互动关系。",
                        u"跨界协同":u"立足公司整体并从流程协同的角度主动打破边界、换位沟通并通力合作，出现分歧时能寻求整合解决，建立组织协同优势",
                        u"团队领导":u"通过有效的机制和方法进行团队价值引导、目标整合、信任建立、潜能激发，塑造优秀团队文化，推动团队高绩效实现。",
                        u"系统思维":u"立足公司战略定位，洞察行业发展的趋势，系统分析业务发展的各种因素，把握本质并结合实际，形成整体判断和系统性的策略安排",
                        u"勇于承担":u"始终立足公司发展的大局，积极地看待转型发展中的问题并敢于负责、主动承担、积极奉献，能包容，善团结。",
                        u"正直诚信":u"坚持从客观事实出发，公正公平，坚持原则，不畏权威，言行一致，推动坦诚信任的组织文化建设。",
                        u"资源整合":u"立足价值链的协同，从增加和创造商业价值的角度，通过合理的方式和机制获取资源，并进行有效配置以实现资源价值最大化"}

        dict_behaviour_desc = {u"做事规范坦率真诚":{"H":u"能够遵守的制度规范，主动真诚地与他人分享信息","M":u"基本能够遵守制度规范，能够在互动中有一定的坦诚交流","L":u"可能在工作、互动中忽视了规章制度，及坦诚的重要性"},
                        u"言行一致遵守承诺":{"H":u"能够言行一致，遵守对他人的承诺，承诺过的事情一定做到","M":u"一般情况下都能够做到言行一致","L":u"言行可能会不一致，很少会将自身的承诺转化为实际行动"},
                        u"处事公平公正":{"H":u"坚持公平公正的原则处理问题、制定决策，对事不对人","M":u"基本能够秉持客观公正的处事原则","L":u"可能在处理问题上掺杂了个人情感"},
                        u"敢于当面直谏":{"H":u"面对权威敢于当面直谏，主动保护组织利益","M":u"大多情况下能够坚持组织原则，向上进行反馈","L":u"可能对权威有一定的畏惧，忽视了组织的利益"},
                        u"明确职责，主动承担责任":{"H":u"清晰自身岗位职责，能够主动承担并处理职责范围内的困难任务","M":u"基本能够清楚工作职责要求，承担起份内的工作","L":u"可能对工作职责和角色不是太清晰，缺乏对本职工作责任的担当"},
                        u"以目标为导向，完成工作":{"H":u"目标导向，为了实现目标，能够承担压力，不择不扣地完成工作内容或任务","M":u"基本能够完成本职或者上级交付的工作","L":u"可能目标导向性较为薄弱，在完成工作任务时会有所折扣"},
                        u"有责无疆，积极推进":{"H":u"能够积极处理职责内外事务，主动推动相关部门协作，推进任务完成","M":u"大多情况下不设定职责边界，并能够推动各部门共同合作完成任务","L":u"可能为自身划分出明确的职责范围，不善于推进各部门的共同协作"},
                        u"挺身而出，成为依靠":{"H":u"始终心系利益，主动在关键时刻挺身而出成为大家的依靠","M":u"面对逆境，基本能够不计较个人得失，为大家找出方向","L":u"面对危难时，或许很难带领大家找出问题解决的方向"},
                        u"主动关注新事物":{"H":u"主动关注并借鉴行业/市场出现上的新事物","M":u"对行业/市场上的新技术、新方法有一定的关注和思考","L":u"可能对行业/市场上的新生事物、新技术、新方法等缺乏一定的了解"},
                        u"借鉴经验，快速有效优化":{"H":u"善于借鉴各方经验及反馈信息快速有效地进行微创新","M":u"优势能够在借鉴他人经验的基础上，对本职工作进行一些优化或微创新","L":u"可能不太善于借鉴他人的经验来完善或优化自己的工作"},
                        u"敢于尝试持续创新":{"H":u"敢于试错并不断地总结分析经验促进工作方法上的创新","M":u"基本能够对工作中的经验和错误进行持续的优化","L":u"可能不太会为了改进工作方法/机制，而去尝试或犯错"},
                        u"打造创新机制及氛围":{"H":u"善于在团队中营造创新的氛围，鼓励并接纳员工的创新","M":u"大多情况下鼓励员工进行业务、工作方法等方面的创新","L":u"可能很少在团队中打造创新机制"},
                        u"倾听并及时反馈":{"H":u"善于倾听内外部客户感受，并及时与相关人员进行反馈","M":u"对内外部客户感受有一定的了解，并与相关人员进行沟通","L":u"可能对内外部客户的感受有所忽视，不能给予相关反馈"},
                        u"换位思考，构建解决方案":{"H":u"善于从内外部客户的角度看待问题，构建解决方案增强客户满意度","M":u"基本能够以内外部客户利益来提供问题解决方案","L":u"很少从内外部客户角度处理问题，提供服务"},
                        u"协调资源超越期望":{"H":u"善于协调各方资源，深化内外部客户需求，超越客户对工作的期望","M":u"基本能够结合内外资源满足/超越客户需求","L":u"可能需要加强资源协作上的技巧，以确保实现/超越内外部客户期望"},
                        u"主动关注提升满意度":{"H":u"能够主动关心内外部客户的发展和困难，并给予支持和帮助，不断提高客户满意度","M":u"对客户有一定的关注，在提供内外部客户支持和帮助方面基本与大多数人一致","L":u"很少了解客户的需求，可能很难使客户满意"},
                        u"理解其他部门需求及利益":{"H":u"充分明晰各部门的需求及利益，了解项目/时间对其他部门的影响","M":u"对各职能部门的需求和利益有一定的了解","L":u"可能很少关注其他部门的利益需求"},
                        u"换位思考，促进协作":{"H":u"主动从其他部门的角度考虑问题，实现各部门之间的相互支持","M":u"基本能够做到各部门之间的相互理解和协作","L":u"可能在工作中从本部门的角度为出发点，缺少了共同合作的精神"},
                        u"调解冲突，达致双赢":{"H":u"善于在利益冲突过程中进行综合考量，制定解决方案，达成各部门间的双赢","M":u"基本能够调节部门内外冲突，实现各部门间利益双赢","L":u"或许很少以双赢的方式解决部门内外冲突"},
                        u"建立合作机制，实现效能最大化":{"H":u"善于建立长期的部门合作机制，实现效益最大化","M":u"对决策的影响有一定的预估，基本能够建立协同合作机制","L":u"可能忽略了各个部门间合作机制的构建"},
                        u"理解高效团队的重要性":{"H":u"清楚理解高效团队对部门目标达成的重要性，会主动去了解团队的运作效率和挑战","M":u"基本能够意识到团队高效运作的重要意义，对团队的运作效率有一定的了解","L":u"可能不太理解高效团队对目标达成的重要性，很少回去了解团队的现状"},
                        u"高效合理授权":{"H":u"善于根据员工的能力进行合理有效的授权，并长期跟踪与反馈","M":u"给予部门员工在工作任务上一定的权限和辅导","L":u"可能在如何授予员工对应的权限和责任有待提升，不太能合理授权"},
                        u"多形式学习交流":{"H":u"积极主动地在团队内部组织多种形式的学习交流活动（如，成功经验分享）","M":u"基本能够根据需求采用不同的方式展开经验分享","L":u"可能不太善于为团队创造不同形式的学习交流活动"},
                        u"塑造团队文化":{"H":u"善于打造团队文化，激发团队自主效能，打造高效团队","M":u"在团队内能够进行愿景宣导，激励团队向心力方面与大多数人一样","L":u"可能缺少团队凝聚力、团队文化的建设"},
                        u"理解变革":{"H":u"清楚理解驱动变革的深层原因，以及变革所能带来的全局收益","M":u"基本能够理解驱动变革的原因，但是对于变革带来的收益认识模糊","L":u"对于公司/行业正在发生的变革缺乏理解，不明白变革的需求以及变革带来的收益"},
                        u"愿景塑造":{"H":u"善于为变革创造一个全局的愿景，并基于愿景的达成恰当地授权他人","M":u"能够基于变革创造愿景，但是缺乏为达成愿景进行授权的技巧","L":u"无法基于变革描述愿景，或是不知道怎样基于愿景进行授权"},
                        u"管理阻抗":{"H":u"在变革中总是能够向团队解释清楚变革带来的积极影响，并且清晰阐明成员的角色和价值，赢得成员对于变革的认可和配合","M":u"在变革中通常能够就变革向团队进行解释，但是对于成员角色和价值的描述有时并不清晰，因此会遇到阻抗和消极对待","L":u"在变革中，几乎不向团队解释变革，无法阐明团队成员的角色和价值，因此往往遇到阻抗和消极的现象"},
                        u"捍卫变革":{"H":u"主动担任变革的捍卫者，自身支持变革的同时还能够鼓励同事参与变革","M":u"认可自己作为变革参与者的一份子，通常能够积极拥护变革，支持变革的发生","L":u"在变革中常常置身事外，没有承担起捍卫变革、推动变革的角色"},
                        u"问题发现及分析":{"H":u"主动关注并发现工作中出现的问题，并能够基于内外部客观事实来分析问题","M":u"基本能够发现工作中出现的一些问题，也能够基于事实来分析问题","L":u"或许不太能够发现工作中的问题，也难以对问题进行深入分析"},
                        u"原因识别及构建解决方案":{"H":u"能够透过问题看本质，识别问题的根本原因，并善于以解决问题根源为目的制定解决方案","M":u"基本能够识别问题较深层次的原因，并能够构建问题的解决方案","L":u"不太能够识别问题的本质原因，难以构建以解决问题根源为目的的解决方案"},
                        u"过程管控与跟踪":{"H":u"善于在解决问题的过程中紧密跟踪，及时调整问题解决方案","M":u"基本能够在问题解决过程中跟踪问题的状况与事态的发展，调整问题的解决方案","L":u"或许不太能够紧密跟踪问题的解决过程，难以及时调整问题解决方案"},
                        u"前瞻性分析":{"H":u"能以前瞻性的视野看待问题，善于发现潜在的机会或风险","M":u"能够提前预计各种情况，不会走一步看一步","L":u"不太能用发展的眼光看待问题，往往只关注眼前的问题"},
                        u"主动共享信息 ":{"H":u"主动在内部建立协作关系，促进资源信息共享","M":u"能够在内部建立协作关系，推动信息传播和共享","L":u"可能较少在组织内部传播、分享信息资源"},
                        u"主动争取和协调资源 ":{"H":u"以公司需求和市场发展为目标，发掘各部门/事业部协作机会，争取并协调组织资源，以满足客户需求","M":u"基于对各部门及事业部利益点的了解，基本能以客户需求为出发点，协调各方资源，推动需求满足","L":u"可能忽视了组织内各事业部及部门的不同利益点，不太擅长协调各部门资源，满足客户需求"},
                        u"转变思维，扩展资源渠道 ":{"H":u"敢于突破思维，引进新资源，促成多方合作，扩展资源渠道","M":u"对新资源持有开放的态度，基本能扩展已有的渠道，推动产品组合的整合效应","L":u"可能偏向于固有的合作思维，较少引进新资源，资源渠道较为单一"},
                        u"形成固有并可持续的模式 ":{"H":u"善于从宏观层面综合考量资源的协调与配合，优化资源配置，敢于打造并固化新的资源整合体系","M":u"基本能从长远发展的角度出发，整体考量资源整合体系，促进组织效能的提升","L":u"可能更多的使用固有的资源体系进行资源配置，不太善于提升组织效能"},
                        u"为自己设置挑战性目标":{"H":u"具有强烈的渴望成功的愿望，勇于挑战现状，设立奋斗的目标","M":u"有一定的追求成功的愿望，一般不会满足于现状，能够给自己设定具有一定挑战性的目标","L":u"面对任务时，可能会安于现状，对自己没有太高的要求"},
                        u"自我激发,从内心寻求动力":{"H":u"在困难和挑战面前，能以自我价值实现为动力，积极调动自身能量，激情投入","M":u"为了目标的达成能够付出和努力行动，有时需要外部的一些肯定或激励才会持续地投入","L":u"在缺乏外部激励时可能会缺乏激情，容易放弃"},
                        u"会付出额外的努力":{"H":u"投入额外的时间和精力，达成行业或组织内最佳的工作成果","M":u"能够投入额外的努力，有追求更好成果的愿望","L":u"可能缺乏额外投入的意愿，更多只愿完成份内的工作。"},
                        u"积极寻求解决办法,坚持不懈":{"H":u"面对困难和挑战仍能够持续投入，利用各种方法保证最终达到目标","M":u"面对困难，能主动面对，并愿意做出一定的投入","L":u"面对困难缺乏自信，容易产生放弃、逃避和退缩的念头"}}        

        default_data = {
            "report_type": "MC2019",
            "msg": {
                "Name": "",
                "Gender": "",
                "TestTime": "",
                "Age":"",
                "scores":{"self":dict_score_quota_self,"others":dict_score_quota_others},
                "analysis":dict_analysis,
                "details_self":analyis_self,
                "details_others":analyis_others,
                "portrait":dict_potrait,
                "advices":advices
            }}

        frontname = settings.DATABASES['front']['NAME']

        sql_query_self = "select b.tag_value ,a.score from\
            (select answer_id,answer_score score\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.answer_id=b.object_id and b.tag_id=54\
            and b.is_active=True"

        sql_query_others = "select b.tag_value, sum(a.score)/count(people_id) from\
            (select question_id,answer_score score,a.evaluated_people_id as people_id \
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id in (%s) and a.survey_id=b.survey_id and a.evaluated_people_id=b.evaluated_people_id\
            and a.project_id=b.project_id and a.status=20 and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.question_id=b.object_id and b.tag_id=54\
            and b.is_active=True group by b.tag_value"            

        try:
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['mc2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Gender"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", None)
            if not default_data["msg"]["Age"]:
                default_data["msg"]["Age"] = u"未知"
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = people_result.finish_time.strftime(u"%Y年%m月%d日")
            else:
                default_data["msg"]["TestTime"] = time.strftime(u"%Y年%m月%d日", time.localtime())

            others =",".join(map(str, PeopleSurveyRelation.objects.filter_active(~Q(id= people_result.id),
                                                            evaluated_people_id=people_result.people_id,
                                                            project_id=people_result.project_id).values_list("id",flat = True)))
                                                                
            with connection.cursor() as cursor:
                # get self mc
                cursor.execute(sql_query_self, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                dictscore = {}
                # get question answers
                for row in cursor.fetchall():
                    if dictscore.has_key(row[0]):
                        dictscore[row[0]]=dictscore[row[0]]+row[1]
                    else:
                        dictscore[row[0]]=row[1]
                # get behaviour score
                for key,value in dictscore.items():
                    if dict_behaviour_question.has_key(key): 
                        dict_score_behaviour_self[dict_behaviour_question[key]]=(value+3)/1.2
                # get quota score
                for key,value in dict_quota_behaviour.items():
                    for bv in value:
                        dict_score_quota_self[key] += dict_score_behaviour_self[bv]
                    dict_score_quota_self[key] = (dict_score_quota_self[key] * 1.00)/len(value)

                # get others mc
                cursor.execute(sql_query_others, [others])
                columns = [col[0] for col in cursor.description]
                dictscore = {}
                # get question answers
                for row in cursor.fetchall():
                    if dictscore.has_key(row[0]):
                        dictscore[row[0]]=dictscore[row[0]]+row[1]
                    else:
                        dictscore[row[0]]=row[1]
                # get behaviour score
                for key,value in dictscore.items():
                    if dict_behaviour_question.has_key(key): 
                        dict_score_behaviour_others[dict_behaviour_question[key]]=(value-1)/0.8
                # get quota score
                for key,value in dict_quota_behaviour.items():
                    for bv in value:
                        dict_score_quota_others[key] += dict_score_behaviour_others[bv]
                    dict_score_quota_others[key] = (dict_score_quota_others[key] * 1.00)/len(value)
            
            #get top.last 2 of self-mc
            keys,values = zip(*sorted(dict_score_quota_self.items(), key=lambda d:d[1],reverse = True))
            dict_analysis[u"自我评价相对优势能力"].extend(keys[:3])
            dict_analysis[u"自我评价相对劣势能力"].extend(keys[-1:-4:-1])
            #get top.last 2 of others-mc
            keys,values = zip(*sorted(dict_score_quota_others.items(), key=lambda d:d[1],reverse = True))
            dict_analysis[u"他人评价相对优势能力"].extend(keys[:3])
            dict_analysis[u"他人评价相对劣势能力"].extend(keys[-1:-4:-1])

            #quota details
            for quota in list_quotas:
                analyis_self[quota]={}
                analyis_self[quota]["pt"]=dict_score_quota_self[quota]
                analyis_self[quota]["desc"]=dict_quota_desc[quota]
                analyis_self[quota]["memo"]=[]
                mark = "L"
                for bv in dict_quota_behaviour[quota]:
                    for margin in dict_score_level.keys():
                        if dict_score_behaviour_self[bv]>=margin:
                            mark = dict_score_level[margin]
                            analyis_self[quota]["memo"].append(\
                                (mark,dict_behaviour_desc[bv][mark]))
                            break
            
            for quota in list_quotas:
                analyis_others[quota]=[]
                for bv in dict_quota_behaviour[quota]:
                    analyis_others[quota].append((bv,dict_score_behaviour_others[bv]))
        
            dict_potrait[u"潜能区"]=list(set(dict_analysis[u"自我评价相对劣势能力"]) &  set(dict_analysis[u"他人评价相对优势能力"]))
            dict_potrait[u"优势共识区"]=list(set(dict_analysis[u"自我评价相对优势能力"]) &  set(dict_analysis[u"他人评价相对优势能力"]))
            dict_potrait[u"待发展共识区"]=list(set(dict_analysis[u"自我评价相对劣势能力"]) &  set(dict_analysis[u"他人评价相对劣势能力"]))
            dict_potrait[u"盲点"]=list(set(dict_analysis[u"自我评价相对优势能力"]) &  set(dict_analysis[u"他人评价相对劣势能力"]))

            dict_analysis[u"自我评价相对优势能力"]=dict_analysis[u"自我评价相对优势能力"][:3]
            dict_analysis[u"自我评价相对劣势能力"]=dict_analysis[u"自我评价相对劣势能力"][:3]
            dict_analysis[u"他人评价相对优势能力"]=dict_analysis[u"他人评价相对优势能力"][:3]
            dict_analysis[u"他人评价相对劣势能力"]=dict_analysis[u"他人评价相对劣势能力"][:3]

            for quota in dict_potrait[u"待发展共识区"]+dict_potrait[u"盲点"]:
                advices[quota]=dict_quota_advice[quota]

        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS      

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
                    [u"管理型职业锚，意味着您追求并致力于职位晋升，倾心于全面管理，独立负责一个单元，可以跨部门整合其他人的努力成果。管理型的您希望承担整体的责任，并将公司的成功与否看作衡量自己工作的标准。具体的技术/职能工作仅仅被看作是您通向全面管理层的必经之路。",
                     u"管理型职业锚的您强调实际的业务管理与控制，注重个人在一般管理与领导领域的进一步发展，希望有机会和时间展示自己的管理才能；管理型的您不愿意放弃任何在组织内获得更高职位的机会，您也愿意承担您所管理组织或单位的业绩与输出。",
                     u"如果您目前还处于技术或者职能工作的领域，您会把这看作是学习的必经过程，也愿意接受本功能组织的管理岗位，但您更愿意接受一般性管理的职位。希望能够依靠个人的分析能力、人际关系、团队领导能力、情商、以及负责任的态度，为本组织或者项目的成功贡献力量。"],
                 u"工作类型":u"管理型职业锚的您希望在工作中能够学习如何行使多项职责；如何综合利用来自多种渠道的信息；如何管理人数不断增加的员工队伍；以及如何运用人际交流技巧。",
                 u"薪酬福利":u"管理型职业锚的您认为薪酬是由所处职位所决定的，因此，管理型的您在管理职位上的追求，也代表了您对于高薪酬福利的期望。",
                 u"工作晋升":u"您拥护组织传统的职业发展道路，追求并致力于工作晋升，倾心于全面管理，独立负责一个部分，可以跨部门整合其他人的努力成果。管理型的您想去承担整体的责任，并将公司的成功与否看成自己的工作。",
                 u"最佳认可方式":u"您希望通过获得更高的薪水以及职位的晋升来得到认可，如果让您去管理大项目，或者邀请出席重要会议，或者派您去参加某些研讨会，使您得以提升自身管理技能，也是不错的认可方式。"},
             u"自主/独立型":
                {u"基本特征":
                    [u"自主/独立型职业锚，意味着您不会放弃任何可以以您的意志或方法定义您职业生涯发展的机会。您追求自主和独立，不愿意受别人约束，也不愿受程序、工作时间、着装方式等规范的制约。不管工作内容是什么，自主/独立型的您都希望能在工作过程中用自己的方式、工作习惯、时间进度和自己的标准来完成工作。",
                     u"为了追求自主、独立，您宁愿放弃安逸的工作环境或优厚的薪金待遇。",
                     u"自主/独立型的您，倾向于从事极具自由的职业，比如自由顾问、教授、独立的商务人士、销售员等等。如果您被局限在一个组织内，您希望职位能够具有灵活与独立性；您有时也会因为希望保留自主的权力而放弃晋升与发展的机会。"],
                 u"工作类型":u"您喜欢专业领域内职责描述清晰、时间明确的工作。对您而言，承包式或项目式工作，全职、兼职或是临时性的工作都是可以接受的。另外您倾向于为“有明确工作目标，却不限制工作完成方式的组织”效力。您能接受组织强加的工作目标，但希望按照自己喜欢的方式完成工作；",
                 u"薪酬福利":u"您喜欢基于工作绩效的工资、奖金，希望能当即付清；",
                 u"工作晋升":u"您希望基于自己以往的成就获得晋升，希望从新的岗位上获取更多的独立和自主权。如果新的职位赋予了您更高的头衔和更多责任，却剥夺了您自由工作的空间，您会感到难以接受；",
                 u"最佳认可方式":u"您最喜欢直接的表扬或认可，勋章、奖品、证书等奖励方式比晋升、获得头衔甚至是金钱更具吸引力。对您而言，如果能在工作上获取更大的自主空间，这将是最有效的激励方式。"},
             u"安全/稳定型":
                {u"基本特征":
                    [u"安全/稳定型职业锚的您主要关注点是争取一份稳定的职业，这种职业锚也显示了对于财务安全性（比如养老金、公积金或医疗保险）、雇佣安全性以及地区选择的重视。",
                     u"作为安全/稳定型中的一员，尽管您也可能因为才干获得在组织内的提升，但是您可能不太在意工作的内容或者是否能够得到职位的提升。",
                     u"安全/稳定型的您关注于围绕着安全与稳定构建全部的自我形象。安全/稳定型的您只有在已经获得职位的成功以及确定的稳定性后才能够显得放松。"],
                 u"工作类型":u"您希望获得一份长期的稳定职业，这些职业能够提供有保障的工作、体面的收入以及可靠的未来生活，这种可靠的未来生活通常是由良好的退休计划和较高的退休金来保证的，有可能的话，您会优先选择政府机关，医疗机构，教育行业，大型的外资或国有企业。",
                 u"薪酬福利":u"您不追求一份令人羡慕的薪金，而更在意稳定长期的财务安全性。对于您来说，除了固定的薪资，您还在意福利的结构，包括各种保险，公积金，休假，固定投资等等。",
                 u"工作晋升":u"对于您来说，追求更为优越的职业或工作的晋升，如果意味着将要在您的生活中注入一种不稳定或保障较差的因素的话，那么您会觉得在一个熟悉的环境中维持一种稳定的、有保障的职业对您来说是更为重要的。",
                 u"最佳认可方式":u"来自组织对于您长期贡献与经验资历的表彰是组织对您最佳的认可方式；而一份长期的或无固定期限的合同，或者组织提供的完善的家庭保障计划，将是对您最好的激励方式。"},
             u"创业型":
                {u"基本特征":
                    [u"创业型职业锚，意味着您不会放弃任何可能创建属于您自己的团队或组织或企业的机会。您愿意基于自己的能力与意愿，承担风险并克服障碍。您愿意向其他人证明您能够依靠自己的努力创建一个企业。您可能为了学习与寻找机会而被雇佣，但是您一旦找到机会便会抽身而出。",
                     u"您愿意去证明您创建企业的成功，您的需求如此强烈使得您愿意去承受可能的失败直到最终成功。极强烈的创造欲使创业型的人要求标新立异、有所创造、并做好冒险的准备。",
                     u"大多数像您一样创业型职业锚的人成为了创业者、发明家或艺术家。但需要澄清的是，市场分析人员、研究开发人员、广告策划人员并不能归入这一类别，因为创业型人的主要动机和价值观是“创造”。"],
                 u"工作类型":u"您希望通过自己的努力创造新的公司、产品或服务。您相信自己是天才，并有很高的动力去证明您具有创造力，而且不断地接受新的挑战；",
                 u"薪酬福利":u"您认为所有权和控制权对您才是最重要的，例如：年薪、股票或期权。您不会在意每月固定的薪资，或者定期的奖金，对您来说，获得与所有权与控制权所对应报酬才是最重要的；您希望得到金钱，但不是出于爱财的缘故，而是因为把金钱当作您完成了某件大事业的有形标志；",
                 u"工作晋升":u"您要求一定的权力和自由，可以不断去创造；",
                 u"最佳认可方式":u"您要求很高的自我认可和公众认可。创造完全属于自己的东西，例如：一件产品、服务、公司或反应成就的财富等。对于您来说，最佳的认可方式就是对您创造的“产品”的认可与赞扬，或者在公开场合给予您受之无愧的表扬。"},
             u"服务型":
                {u"基本特征":
                    [u"服务型职业锚的人一直在追求他们的核心价值，例如：帮助他人，改善人们的安全，通过新的产品消除疾病等。服务型的人一直追寻这种机会，即使变换公司，也不会接受无法实现这种价值的变动或工作提升。",
                     u"作为服务型职业锚的一员，意味着您不会放弃任何有可能创造某种价值的机会，比如改变人居环境，解决环境污染的问题，创造和谐的人际关系，帮助他人，改善人群的安全感，通过新产品的研发治疗疾病，以及其他方式。就算您所关注的工作或事宜有可能影响到组织的现状，您也会始终追求您的职业定位及其价值意义。您也会不愿意接受那些有可能使您不能关注于创造价值的职位转移或提升。"],
                 u"工作类型":u"您希望工作能够创造价值，对他人能有所帮助、使生活更美好。您希望能以自己的价值观影响组织乃至社会；",
                 u"薪酬福利":u"您希望获得基于贡献的、公平的薪资，钱并不是您追求的根本；",
                 u"工作晋升":u"您希望通过认可您的贡献，给您更多的权力和自由来体现自己的价值；",
                 u"最佳认可方式":u"来自同事及上司的认可和支持，与他人共享自己的核心价值。通过自己的努力，给别人带来了帮助或促成了某项事业的成功。能给您继续提供为心中的理想打拼的机会，这才是对您的真正认可。"},
             u"挑战型":
                {u"基本特征":
                    [u"挑战型职业锚的您，喜欢解决看上去无法解决的问题，战胜强硬的对手，克服无法克服的障碍等。对挑战型的您而言，参加工作或职业的原因是工作允许您去战胜各种不可能。您需要新奇、变化和困难，如果工作非常容易，您马上就会厌倦这份工作。",
                     u"作为挑战型职业锚的一员，意味着您不会放弃任何发掘解决问题的方法，克服他人所不能克服的障碍，或者超越您竞争对手的机会。您认为自己可以征服任何事情或任何人；您将成功定义为“克服不可能的障碍，解决不可能解决的问题，或战胜非常强硬的对手”。随着自己的进步，您喜欢寻找越来越强硬的“挑战”，希望在工作中面临越来越艰巨的任务，并享受由战胜或征服而带来的成就感。",
                     u"需要说明的是，您的职业锚类型与技术/职能型之间存在一定差别，即技术/职能型的人只关注某一专业领域内的挑战并持续为之奋斗；而挑战型的人，一旦达成了成就或征服了困难，再让您去做同一类型的任务，就会感觉无聊之极。还有一些挑战型职业锚的人，将挑战定义成人际间的竞争。例如：一些飞行员唯一的目标就是与敌机来一场决战，以向世界证明他们在战斗中的优势；许多销售人员、职业运动员和管理者将职业定义为在每日的战斗或竞赛中胜出。"],
                 u"工作类型":u"对您而言，一定水平的挑战是至关重要的，不管您的工作内容是什么，都需要有“挑战自我的机会”；",
                 u"薪酬福利":u"您希望基于所从事的项目或任务的挑战性、难度得到报酬。金钱并不是您的最终追求，您更看重工作中是否有挑战自我或挑战难题的机会；",
                 u"工作晋升":u"您希望自己的晋升能使自己的“工作为自己提供更多挑战困难或挑战自我的机会”，因而，如果职位提高了，挑战自我的机会减少了，那么您很快就会厌倦这个职位；",
                 u"最佳认可方式":u"您渴望战胜困难或征服对手后的成就感，因此，战胜挑战后的愉悦感会激励着您不断寻求难度更大的挑战。您对自己的认可基于挑战的成败，而不是外在的奖励，因此，对您来说，挑战即是认可，只要给您布置好下一个工作任务就行了。"},
             u"生活型":
                {u"基本特征":
                    [u"生活型职业锚的您，希望将生活的各个主要方面整合为一个整体，喜欢平衡个人的、家庭的和职业的需要，因此，生活型的您需要一个能够提供“足够弹性”的工作环境来实现这一目标。生活型的您甚至可以牺牲职业的一些方面，例如放弃职位的提升或调动，来换取三者的平衡。相对于具体的工作环境、工作内容，生活型的您更关注自己如何生活、在哪里居住、如何处理家庭事情及怎样自我提升等。",
                     u"生活型职业锚是综合了职业与家庭关系的一种职业定位。生活型职业锚现在变得越来越普遍，因为作为家庭主要成员的两方必须同时关注两个同样重要，但是有可能就是不同的职业选择。如果您在生活型方面的得分相对最高，意味着您不会放弃任何有助于整合或平衡个人的需求，与家庭的需求，或者与您职业的需求的机会。您期望那些与生活工作重要的因素能够相互融合成一体，因此，您也愿意去发展您的职业生涯以提供足够的灵活性满足这种融合。"],
                 u"工作类型":u"您希望为生活而工作，而不是为工作而生活，所以在工作上，您不会做过多份外之事。您期望您的工作内容是明确的。",
                 u"薪酬福利":u"您不追求通过加班或参与项目的方式获得额外的收入，您追求属于您的那一份明确工作任务的所得。对于您来说，这份薪酬福利已经能够使您正常快乐的生活，而额外付出的努力获得的收入反而得不偿失。",
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
            if not people_result.report_url:
                people_result.report_url= settings.Reports['disc2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", u"未知")
            if people_result.finish_time:
                default_data["msg"]["CompleteTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["CompleteTime"] = time_format4(datetime.datetime.now())

            score_count_query_dict = UserQuestionAnswerInfo.objects.filter(
                project_id=people_result.project_id,
                survey_id=people_result.survey_id,
                people_id=people_result.people_id,
                is_active=True
            ).values_list('answer_score').annotate(c=Count("id"))
            score_count = list(score_count_query_dict)
            score_count.sort()  # [(0.0, 13), (1.0, 2), (2.0, 3), (4.0, 3), ..., (64.0, 2), (128.0, 5)]
            count = [0 for x in xrange(9)]
            position = [0, 1, 2, 4, 8, 16, 32, 64, 128]
            for tpl in score_count:
                idx = int(tpl[0])
                count[position.index(idx)] = tpl[1]
            mask = count[1: 5]
            under_stress = count[5:]
            self_image = [mask[j] - under_stress[j] for j in xrange(4)]
            for index, dic in enumerate(default_data["msg"]["ChartWorkMask_Indicator"]):
                default_data["msg"]["ChartWorkMask_Indicator"][index]['score'] = mask[index]
            for index, dic in enumerate(default_data["msg"]["ChartBR_UnderStress_Indicator"]):
                default_data["msg"]["ChartBR_UnderStress_Indicator"][index]['score'] = under_stress[index]
            for index, dic in enumerate(default_data["msg"]["ChartSelfImage_Indicator"]):
                default_data["msg"]["ChartSelfImage_Indicator"][index]['score'] = self_image[index]
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
                    res["disc"][title].append([name, score, finally_score])

        for item in disc:
            name_score_list = disc.get(item)
            name_score_list.sort(key=lambda x: x[2], reverse=True)
            statement_key = ''.join([i[0] for i in name_score_list])
            if not statement_key:
                statement_key = u'下移位'
            if len(statement_key) == 4:
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
            if not people_result.report_url:
                people_result.report_url= settings.Reports['mbti2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()
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

    # 中高层180
    def get_zgc180_value(self, personal_result_id):
        u"""中高层180算法"""
        default_data = {
            "report_type": "中高层180模板",
            "msg": {
                "Name": "666",
                "Sex": "男",
                "Age": "25",
                "TestTime": "2018.10.12",
                # "chart11": [{"name": "积极进取", "score": 2},
                #             {"name": "勇于担当", "score": 2},
                #             {"name": "正直诚信", "score": 2},
                #             {"name": "系统思维", "score": 3},
                #             {"name": "变革管理", "score": 2},
                #             {"name": "客户导向", "score": 2},
                #             {"name": "创新优化", "score": 3},
                #             {"name": "团队领导", "score": 3},
                #             {"name": "跨界协同", "score": 4},
                #             {"name": "资源整合", "score": 2},
                #             ],
                # 自评原始维度
                "chart11": [{"name": "积极进取", "score": 2},
                            {"name": "勇于担当", "score": 2},
                            {"name": "正直诚信", "score": 2},
                            {"name": "系统思维", "score": 3},
                            {"name": "变革管理", "score": 2},
                            {"name": "客户导向", "score": 2},
                            {"name": "创新优化", "score": 3},
                            {"name": "团队领导", "score": 3},
                            {"name": "跨界协同", "score": 4},
                            {"name": "资源整合", "score": 2},
                            ],
                # 他评原始维度
                # name  维度名称，score: 维度分    他评
                "chart12": [{"name": "积极进取", "score": 2},
                            {"name": "勇于担当", "score": 2},
                            {"name": "正直诚信", "score": 3},
                            {"name": "系统思维", "score": 3},
                            {"name": "变革管理", "score": 4},
                            {"name": "客户导向", "score": 2},
                            {"name": "创新优化", "score": 3},
                            {"name": "团队领导", "score": 3},
                            {"name": "跨界协同", "score": 2},
                            {"name": "资源整合", "score": 2},
                            ],

                # name  维度名称，score: 维度分    自评
                "chart": [
                    {"name": u"积极进取", "score": 2},
                    {"name": u"勇于担当", "score": 2},
                    {"name": u"正直诚信", "score": 2},
                    {"name": u"系统思维", "score": 3},
                    {"name": u"变革管理", "score": 2},
                    {"name": u"客户导向", "score": 2},
                    {"name": u"创新优化", "score": 3},
                    {"name": u"团队领导", "score": 3},
                    {"name": u"跨界协同", "score": 4},
                    {"name": u"资源整合", "score": 2},
                      ],
                # name  维度名称，score: 维度分     他评
                "chart1": [
                    {"name": u"积极进取", "score": 2},
                    {"name": u"勇于担当", "score": 2},
                    {"name": u"正直诚信", "score": 3},
                    {"name": u"系统思维", "score": 3},
                    {"name": u"变革管理", "score": 4},
                    {"name": u"客户导向", "score": 2},
                    {"name": u"创新优化", "score": 3},
                    {"name": u"团队领导", "score": 3},
                    {"name": u"跨界协同", "score": 2},
                    {"name": u"资源整合", "score": 2},
                       ],
                # name1  维度名称，name  指标（即行为）   score: 指标分     自评
                "chart2": [
                    {"name1": u"积极进取", 'name': u'为自己设置挑战性目标', "score": 2},
                    {"name1": u"积极进取", 'name': u'自我激发，从内心寻求动力', "score": 2},
                    {"name1": u"积极进取", 'name': u'会付出额外的努力', "score": 2},
                    {"name1": u"积极进取", 'name': u'积极寻求解决办法，坚持不懈', "score": 2},

                    {"name1": u"勇于担当", 'name': u'明确职责，主动承担责任', "score": 2},
                    {"name1": u"勇于担当", 'name': u'以目标为导向，完成工作', "score": 2},
                    {"name1": u"勇于担当", 'name': u'有责无疆，积极推进', "score": 2},
                    {"name1": u"勇于担当", 'name': u'挺身而出，成为依靠', "score": 2},

                    {"name1": u"正直诚信", 'name': u'做事规范坦率真诚', "score": 3},
                    {"name1": u"正直诚信", 'name': u'言行一致遵守承诺', "score": 3},
                    {"name1": u"正直诚信", 'name': u'处事公平公正', "score": 3},
                    {"name1": u"正直诚信", 'name': u'敢于当面直谏', "score": 3},

                    {"name1": u"系统思维", 'name': u'原因识别及构建解决方案', "score": 3},
                    {"name1": u"系统思维", 'name': u'过程管控与跟踪', "score": 3},
                    {"name1": u"系统思维", 'name': u'前瞻性分析', "score": 3},
                    {"name1": u"系统思维", 'name': u'问题发现及分析', "score": 3},

                    {"name1": u"变革管理", 'name': u'理解变革', "score": 2},
                    {"name1": u"变革管理", 'name': u'愿景塑造', "score": 2},
                    {"name1": u"变革管理", 'name': u'管理阻抗', "score": 2},
                    {"name1": u"变革管理", 'name': u'捍卫变革', "score": 2},

                    {"name1": u"客户导向", 'name': u'换位思考，构建解决方案', "score": 2},
                    {"name1": u"客户导向", 'name': u'倾听并及时反馈', "score": 2},
                    {"name1": u"客户导向", 'name': u'主动关注提升满意度', "score": 2},
                    {"name1": u"客户导向", 'name': u'协调资源超越期望', "score": 2},

                    {"name1": u"创新优化", 'name': u'打造创新机制及氛围', "score": 3},
                    {"name1": u"创新优化", 'name': u'主动关注新事物', "score": 3},
                    {"name1": u"创新优化", 'name': u'勇于尝试持续创新', "score": 3},
                    {"name1": u"创新优化", 'name': u'借鉴经验，快速有效优化', "score": 3},

                    {"name1": u"团队领导", 'name': u'理解高效团队的重要性', "score": 3},
                    {"name1": u"团队领导", 'name': u'高效合理授权', "score": 3},
                    {"name1": u"团队领导", 'name': u'塑造团队文化', "score": 3},
                    {"name1": u"团队领导", 'name': u'多形式学习交流', "score": 3},

                    {"name1": u"跨界协同", 'name': u'调节冲突，达至双赢', "score": 2},
                    {"name1": u"跨界协同", 'name': u'建立合作机制，实现效能最大化', "score": 2},
                    {"name1": u"跨界协同", 'name': u'理解其他部门需求及利益', "score": 2},
                    {"name1": u"跨界协同", 'name': u'换位思考，促进协作', "score": 2},

                    {"name1": u"资源整合", 'name': u'主动共享信息', "score": 2},
                    {"name1": u"资源整合", 'name': u'形成固有并可持续的模式', "score": 2},
                    {"name1": u"资源整合", 'name': u'主动争取和协调资源', "score": 2},
                    {"name1": u"资源整合", 'name': u'转变思维，扩展资源渠道', "score": 2},
                ],
                # name1  维度名称，name  指标（即行为）   score: 指标分     他评
                "chart3": [
                    {"name1": u"积极进取", 'name': u'为自己设置挑战性目标', "score": 2},
                    {"name1": u"积极进取", 'name': u'自我激发，从内心寻求动力', "score": 2},
                    {"name1": u"积极进取", 'name': u'会付出额外的努力', "score": 2},
                    {"name1": u"积极进取", 'name': u'积极寻求解决办法，坚持不懈', "score": 2},

                    {"name1": u"勇于担当", 'name': u'明确职责，主动承担责任', "score": 2},
                    {"name1": u"勇于担当", 'name': u'以目标为导向，完成工作', "score": 2},
                    {"name1": u"勇于担当", 'name': u'有责无疆，积极推进', "score": 2},
                    {"name1": u"勇于担当", 'name': u'挺身而出，成为依靠', "score": 2},

                    {"name1": u"正直诚信", 'name': u'做事规范坦率真诚', "score": 3},
                    {"name1": u"正直诚信", 'name': u'言行一致遵守承诺', "score": 3},
                    {"name1": u"正直诚信", 'name': u'处事公平公正', "score": 3},
                    {"name1": u"正直诚信", 'name': u'敢于当面直谏', "score": 3},

                    {"name1": u"系统思维", 'name': u'原因识别及构建解决方案', "score": 3},
                    {"name1": u"系统思维", 'name': u'过程管控与跟踪', "score": 3},
                    {"name1": u"系统思维", 'name': u'前瞻性分析', "score": 3},
                    {"name1": u"系统思维", 'name': u'问题发现及分析', "score": 3},

                    {"name1": u"变革管理", 'name': u'理解变革', "score": 2},
                    {"name1": u"变革管理", 'name': u'愿景塑造', "score": 2},
                    {"name1": u"变革管理", 'name': u'管理阻抗', "score": 2},
                    {"name1": u"变革管理", 'name': u'捍卫变革', "score": 2},

                    {"name1": u"客户导向", 'name': u'换位思考，构建解决方案', "score": 2},
                    {"name1": u"客户导向", 'name': u'倾听并及时反馈', "score": 2},
                    {"name1": u"客户导向", 'name': u'主动关注提升满意度', "score": 2},
                    {"name1": u"客户导向", 'name': u'协调资源超越期望', "score": 2},

                    {"name1": u"创新优化", 'name': u'打造创新机制及氛围', "score": 3},
                    {"name1": u"创新优化", 'name': u'主动关注新事物', "score": 3},
                    {"name1": u"创新优化", 'name': u'勇于尝试持续创新', "score": 3},
                    {"name1": u"创新优化", 'name': u'借鉴经验，快速有效优化', "score": 3},

                    {"name1": u"团队领导", 'name': u'理解高效团队的重要性', "score": 3},
                    {"name1": u"团队领导", 'name': u'高效合理授权', "score": 3},
                    {"name1": u"团队领导", 'name': u'塑造团队文化', "score": 3},
                    {"name1": u"团队领导", 'name': u'多形式学习交流', "score": 3},

                    {"name1": u"跨界协同", 'name': u'调节冲突，达至双赢', "score": 2},
                    {"name1": u"跨界协同", 'name': u'建立合作机制，实现效能最大化', "score": 2},
                    {"name1": u"跨界协同", 'name': u'理解其他部门需求及利益', "score": 2},
                    {"name1": u"跨界协同", 'name': u'换位思考，促进协作', "score": 2},

                    {"name1": u"资源整合", 'name': u'主动共享信息', "score": 2},
                    {"name1": u"资源整合", 'name': u'形成固有并可持续的模式', "score": 2},
                    {"name1": u"资源整合", 'name': u'主动争取和协调资源', "score": 2},
                    {"name1": u"资源整合", 'name': u'转变思维，扩展资源渠道', "score": 2},
                ],
            }
        }
        try:
            dimension_id_name_map = {}
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            # if not people_result.dimension_score or not people_result.substandard_score:
                # SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
            time.sleep(0.3)
            SurveyAlgorithm.algorithm_zgc180(personal_result_id, form_type=Survey.FORM_TYPE_NORMAL)
            # 算完分都重定义被评价人
            psr_qs = PeopleSurveyRelation.objects.get(id=personal_result_id)
            o_qs = PeopleSurveyRelation.objects.filter(project_id=psr_qs.project_id,
                                                       evaluated_people_id=psr_qs.evaluated_people_id,
                                                       people_id=psr_qs.evaluated_people_id,
                                                       status=PeopleSurveyRelation.STATUS_FINISH)
            if not o_qs.exists():
                # 该他评没有自评
                err_logger.error("%s for ZGC180 not self ZGC180" % personal_result_id)                
                return
            else:

                personal_result_id = o_qs[0].id


            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value(u"性别", u"未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", u"未知")
            if type(default_data["msg"]["Age"]) == int:
                default_data["msg"]["Age"] = "{}".format(default_data["msg"]["Age"])
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            # 自评维度
            dimension_score_map = people_result.dimension_score_map["self"]
            for info in default_data["msg"]["chart"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][0:2] == info["name"][0:2]:
                        dimension_id_name_map[dimension_id] = dimension_score_map[dimension_id]["name"]
                        info["score"] = dimension_score_map[dimension_id]["score"]
                        break
            #  自评维度原始
            for info in default_data["msg"]["chart11"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][0:2] == info["name"][0:2]:
                        # dimension_id_name_map[dimension_id] = dimension_score_map[dimension_id]["name"]
                        info["score"] = dimension_score_map[dimension_id]["row_score"]
                        break
            # 自评子标
            substandard_score_map = people_result.substandard_score_map["self"]
            for info in default_data["msg"]["chart2"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"][0:3] == info["name"][0:3] and info["name1"][0:2] == substandard_score_map[substandard_id]["name1"][0:2]:
                    # if substandard_score_map[substandard_id]["name"][0:4] == info["name"]:
                        info["score"] = substandard_score_map[substandard_id]["score"]
                        # info["name1"] = dimension_id_name_map[str(substandard_score_map[substandard_id]["dimension_id"])]
                        break
            # # 他评维度
            dimension_score_map = people_result.dimension_score_map["others"]
            for info in default_data["msg"]["chart1"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][0:2] == info["name"][0:2]:
                        dimension_id_name_map[dimension_id] = dimension_score_map[dimension_id]["name"]
                        info["score"] = round(dimension_score_map[dimension_id]["score"])
                        break
            # 他评维度原始
            for info in default_data["msg"]["chart12"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][0:2] == info["name"][0:2]:
                        # dimension_id_name_map[dimension_id] = dimension_score_map[dimension_id]["name"]
                        info["score"] = dimension_score_map[dimension_id]["score"]
                        break
            # # 他评子标
            substandard_score_map = people_result.substandard_score_map["others"]
            for info in default_data["msg"]["chart3"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"][0:3] == info["name"][0:3] and info["name1"][0:2] == substandard_score_map[substandard_id]["name1"][0:2]:
                    # if substandard_score_map[substandard_id]["name"] == info["name"]:
                        info["score"] = substandard_score_map[substandard_id]["score"]
                        # info["name1"] = dimension_id_name_map[str(substandard_score_map[substandard_id]["dimension_id"])]
                        break
        except Exception, e:
            err_logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

    # 中高层90
    def get_zgc90_value(self, personal_result_id):
        u"""中高层90算法"""
        default_data = {
            "report_type": "中高层90模板",
            "msg": {
                "Name": "666",
                "Sex": "男",
                "Age": "25",
                "TestTime": "2018.10.12",
                # name  维度名称，score: 维度分    自评 ， 新增维度原始分
                "chart11": [{"name": "积极进取", "score": 2},
                            {"name": "勇于担当", "score": 2},
                            {"name": "正直诚信", "score": 2},
                            {"name": "系统思维", "score": 3},
                            {"name": "变革管理", "score": 2},
                            {"name": "客户导向", "score": 2},
                            {"name": "创新优化", "score": 3},
                            {"name": "团队领导", "score": 3},
                            {"name": "跨界协同", "score": 4},
                            {"name": "资源整合", "score": 2},
                            ],

                # name  维度名称，score: 维度分    自评
                "chart": [
                    {"name": u"积极进取", "score": 2},
                    {"name": u"勇于担当", "score": 2},
                    {"name": u"正直诚信", "score": 2},
                    {"name": u"系统思维", "score": 3},
                    {"name": u"变革管理", "score": 2},
                    {"name": u"客户导向", "score": 2},
                    {"name": u"创新优化", "score": 3},
                    {"name": u"团队领导", "score": 3},
                    {"name": u"跨界协同", "score": 4},
                    {"name": u"资源整合", "score": 2},
                ],
            # name1  维度名称，name  指标（即行为）   score: 指标分     自评
                "chart2": [
                    {"name1": u"积极进取", 'name': u'为自己设置挑战性目标', "score": 2},
                    {"name1": u"积极进取", 'name': u'自我激发，从内心寻求动力', "score": 2},
                    {"name1": u"积极进取", 'name': u'会付出额外的努力', "score": 2},
                    {"name1": u"积极进取", 'name': u'积极寻求解决办法，坚持不懈', "score": 2},

                    {"name1": u"勇于担当", 'name': u'明确职责，主动承担责任', "score": 2},
                    {"name1": u"勇于担当", 'name': u'以目标为导向，完成工作', "score": 2},
                    {"name1": u"勇于担当", 'name': u'有责无疆，积极推进', "score": 2},
                    {"name1": u"勇于担当", 'name': u'挺身而出，成为依靠', "score": 2},

                    {"name1": u"正直诚信", 'name': u'做事规范坦率真诚', "score": 3},
                    {"name1": u"正直诚信", 'name': u'言行一致遵守承诺', "score": 3},
                    {"name1": u"正直诚信", 'name': u'处事公平公正', "score": 3},
                    {"name1": u"正直诚信", 'name': u'敢于当面直谏', "score": 3},

                    {"name1": u"系统思维", 'name': u'原因识别及构建解决方案', "score": 3},
                    {"name1": u"系统思维", 'name': u'过程管控与跟踪', "score": 3},
                    {"name1": u"系统思维", 'name': u'前瞻性分析', "score": 3},
                    {"name1": u"系统思维", 'name': u'问题发现及分析', "score": 3},

                    {"name1": u"变革管理", 'name': u'理解变革', "score": 2},
                    {"name1": u"变革管理", 'name': u'愿景塑造', "score": 2},
                    {"name1": u"变革管理", 'name': u'管理阻抗', "score": 2},
                    {"name1": u"变革管理", 'name': u'捍卫变革', "score": 2},

                    {"name1": u"客户导向", 'name': u'换位思考，构建解决方案', "score": 2},
                    {"name1": u"客户导向", 'name': u'倾听并及时反馈', "score": 2},
                    {"name1": u"客户导向", 'name': u'主动关注提升满意度', "score": 2},
                    {"name1": u"客户导向", 'name': u'协调资源超越期望', "score": 2},

                    {"name1": u"创新优化", 'name': u'打造创新机制及氛围', "score": 3},
                    {"name1": u"创新优化", 'name': u'主动关注新事物', "score": 3},
                    {"name1": u"创新优化", 'name': u'勇于尝试持续创新', "score": 3},
                    {"name1": u"创新优化", 'name': u'借鉴经验，快速有效优化', "score": 3},

                    {"name1": u"团队领导", 'name': u'理解高效团队的重要性', "score": 3},
                    {"name1": u"团队领导", 'name': u'高效合理授权', "score": 3},
                    {"name1": u"团队领导", 'name': u'塑造团队文化', "score": 3},
                    {"name1": u"团队领导", 'name': u'多形式学习交流', "score": 3},

                    {"name1": u"跨界协同", 'name': u'调节冲突，达至双赢', "score": 2},
                    {"name1": u"跨界协同", 'name': u'建立合作机制，实现效能最大化', "score": 2},
                    {"name1": u"跨界协同", 'name': u'理解其他部门需求及利益', "score": 2},
                    {"name1": u"跨界协同", 'name': u'换位思考，促进协作', "score": 2},

                    {"name1": u"资源整合", 'name': u'主动共享信息', "score": 2},
                    {"name1": u"资源整合", 'name': u'形成固有并可持续的模式', "score": 2},
                    {"name1": u"资源整合", 'name': u'主动争取和协调资源', "score": 2},
                    {"name1": u"资源整合", 'name': u'转变思维，扩展资源渠道', "score": 2},
                ],
            }
        }
        try:
            dimension_id_name_map = {}
            people_result = PeopleSurveyRelation.objects.get(
                id=personal_result_id
            )
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return default_data, ErrorCode.INVALID_INPUT
            # if not people_result.dimension_score or not people_result.substandard_score:
                # SurveyAlgorithm.algorithm_gzjzg(personal_result_id)
            time.sleep(0.3)
            # SurveyAlgorithm.algorithm_zgc(personal_result_id, form_type=Survey.FORM_TYPE_NORMAL)
            SurveyAlgorithm.algorithm_zgc(personal_result_id)
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)
            people = People.objects.get(id=people_result.people_id)
            default_data["msg"]["Name"] = people.display_name
            default_data["msg"]["Sex"] = people.get_info_value(u"性别", "未知")
            default_data["msg"]["Age"] = people.get_info_value(u"年龄", "未知")
            if type(default_data["msg"]["Age"]) == int:
                default_data["msg"]["Age"] = "{}".format(default_data["msg"]["Age"])
            if people_result.finish_time:
                default_data["msg"]["TestTime"] = time_format4(people_result.finish_time)
            else:
                default_data["msg"]["TestTime"] = time_format4(datetime.datetime.now())
            dimension_score_map = people_result.dimension_score_map["self"]
            # 新增 维度原始分
            for info in default_data["msg"]["chart11"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][:2] == info["name"][:2]:
                        # dimension_id_name_map[dimension_id] = dimension_score_map[dimension_id]["name"]
                        info["score"] = dimension_score_map[dimension_id]["row_score"]
                        break
            # 原来维度转换分维度
            for info in default_data["msg"]["chart"]:
                for dimension_id in dimension_score_map:
                    if dimension_score_map[dimension_id]["name"][:2] == info["name"][:2]:
                        dimension_id_name_map[dimension_id] = dimension_score_map[dimension_id]["name"]
                        info["score"] = dimension_score_map[dimension_id]["score"]
                        break
            substandard_score_map = people_result.substandard_score_map["self"]
            for info in default_data["msg"]["chart2"]:
                for substandard_id in substandard_score_map:
                    if substandard_score_map[substandard_id]["name"][0:3] == info["name"][0:3] and info["name1"][0:2] == substandard_score_map[substandard_id]["name1"][0:2]:
                        info["score"] = substandard_score_map[substandard_id]["score"]
                        # info["name1"] = dimension_id_name_map[str(substandard_score_map[substandard_id]["dimension_id"])]
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

        happy_ability_config_map = {
            "自主定向": {
                 "average_value": 62.64,
                 "standard_diff_value": 18.09},
            "意义寻求": {
                "average_value": 74.13,
                "standard_diff_value": 18.87},
            "自我悦纳": {
                "average_value": 73.43,
                "standard_diff_value": 18.67},
            "自我拓展": {
                "average_value": 69.75,
                "standard_diff_value": 17.14},
            "情绪调节": {
                "average_value": 72.1,
                "standard_diff_value": 19.24},
            "专注投入": {
                "average_value": 66.86,
                "standard_diff_value": 18.92},
            "亲和利他": {
                "average_value": 60.94,
                "standard_diff_value": 16.8},
            "包容差异": {
                "average_value": 73.23,
                "standard_diff_value": 20.86},
            "乐观积极": {
                "average_value": 73.53,
                "standard_diff_value": 19.6},
            "自信坚韧": {
                "average_value": 71.59,
                "standard_diff_value": 21.68},
            "合理归因": {
                "average_value": 71.96,
                "standard_diff_value": 18.47},
            "灵活变通": {
                "average_value": 68.62,
                "standard_diff_value": 18.6}
        }

        average_value = 69.898
        standard_diff_value = 18.912
        positive_comments = []
        negative_comments = []
        negative_quotas = []
        substandard_score_map = {}
        normdist_score_map = {}
        dimension_score = 0.00

        try:
            #get personal assess status info
            people_result = PeopleSurveyRelation.objects.get(id=personal_result_id)

            #exit when not completed
            if people_result.status != PeopleSurveyRelation.STATUS_FINISH:
                return data, ErrorCode.INVALID_INPUT
            if not people_result.report_url:
                people_result.report_url= settings.Reports['peoi2019'] % (personal_result_id)
                people_result.report_status=PeopleSurveyRelation.STATUS_FINISH
                people_result.save()

            frontname = settings.DATABASES['front']['NAME']
            sql_query = "select b.tag_value ,a.score from\
                (select question_id,answer_score score\
                from " + frontname + ".front_peoplesurveyrelation a,\
                " + frontname + ".front_userquestionanswerinfo b\
                where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
                and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
                where a.question_id=b.object_id and b.tag_id=54\
                and b.is_active=True"
            
            with connection.cursor() as cursor:
                cursor.execute(sql_query, [personal_result_id])
                columns = [col[0] for col in cursor.description]
                dictscore = {}
                for row in cursor.fetchall():
                    if dictscore.has_key(row[0]):
                        dictscore[row[0]]=dictscore[row[0]]+row[1]
                    else:
                        dictscore[row[0]]=row[1]
            
            weight=12.50
            substandard_score_map['自主定向']=(dictscore['N1']+dictscore['N2'])*weight
            substandard_score_map['意义寻求']=(dictscore['N3']+dictscore['N4'])*weight
            substandard_score_map['自我悦纳']=(dictscore['N5']+dictscore['N6'])*weight
            substandard_score_map['自我拓展']=(dictscore['N7']+dictscore['N8'])*weight
            substandard_score_map['情绪调节']=(dictscore['N9']+dictscore['N10'])*weight
            substandard_score_map['专注投入']=(dictscore['N11']+dictscore['N12'])*weight
            substandard_score_map['亲和利他']=(dictscore['N13']+dictscore['N14'])*weight
            substandard_score_map['包容差异']=(dictscore['N15']+dictscore['N16'])*weight
            substandard_score_map['乐观积极']=(dictscore['N17']+dictscore['N18'])*weight
            substandard_score_map['自信坚韧']=(dictscore['N19']+dictscore['N20'])*weight
            substandard_score_map['合理归因']=(dictscore['N21']+dictscore['N22'])*weight
            substandard_score_map['灵活变通']=(dictscore['N23']+dictscore['N24'])*weight

            dimension_score = (\
                substandard_score_map['自主定向']+substandard_score_map['意义寻求']+\
                substandard_score_map['自我悦纳']+substandard_score_map['自我拓展']+\
                substandard_score_map['情绪调节']+substandard_score_map['专注投入']+\
                substandard_score_map['亲和利他']+substandard_score_map['包容差异']+\
                substandard_score_map['乐观积极']+substandard_score_map['自信坚韧']+\
                substandard_score_map['合理归因']+substandard_score_map['灵活变通'])/12.00

            normdist_score_map['自主定向']=normsdist((substandard_score_map['自主定向']-happy_ability_config_map['自主定向']['average_value'])/happy_ability_config_map['自主定向']['standard_diff_value'])*100
            normdist_score_map['意义寻求']=normsdist((substandard_score_map['意义寻求']-happy_ability_config_map['意义寻求']['average_value'])/happy_ability_config_map['意义寻求']['standard_diff_value'])*100
            normdist_score_map['自我悦纳']=normsdist((substandard_score_map['自我悦纳']-happy_ability_config_map['自我悦纳']['average_value'])/happy_ability_config_map['自我悦纳']['standard_diff_value'])*100
            normdist_score_map['自我拓展']=normsdist((substandard_score_map['自我拓展']-happy_ability_config_map['自我拓展']['average_value'])/happy_ability_config_map['自我拓展']['standard_diff_value'])*100
            normdist_score_map['情绪调节']=normsdist((substandard_score_map['情绪调节']-happy_ability_config_map['情绪调节']['average_value'])/happy_ability_config_map['情绪调节']['standard_diff_value'])*100
            normdist_score_map['专注投入']=normsdist((substandard_score_map['专注投入']-happy_ability_config_map['专注投入']['average_value'])/happy_ability_config_map['专注投入']['standard_diff_value'])*100
            normdist_score_map['亲和利他']=normsdist((substandard_score_map['亲和利他']-happy_ability_config_map['亲和利他']['average_value'])/happy_ability_config_map['亲和利他']['standard_diff_value'])*100
            normdist_score_map['包容差异']=normsdist((substandard_score_map['包容差异']-happy_ability_config_map['包容差异']['average_value'])/happy_ability_config_map['包容差异']['standard_diff_value'])*100
            normdist_score_map['乐观积极']=normsdist((substandard_score_map['乐观积极']-happy_ability_config_map['乐观积极']['average_value'])/happy_ability_config_map['乐观积极']['standard_diff_value'])*100
            normdist_score_map['自信坚韧']=normsdist((substandard_score_map['自信坚韧']-happy_ability_config_map['自信坚韧']['average_value'])/happy_ability_config_map['自信坚韧']['standard_diff_value'])*100
            normdist_score_map['合理归因']=normsdist((substandard_score_map['合理归因']-happy_ability_config_map['合理归因']['average_value'])/happy_ability_config_map['合理归因']['standard_diff_value'])*100
            normdist_score_map['灵活变通']=normsdist((substandard_score_map['灵活变通']-happy_ability_config_map['灵活变通']['average_value'])/happy_ability_config_map['灵活变通']['standard_diff_value'])*100


            people = People.objects.get(id=people_result.people_id)
            total_score = 100
            normsdist_score = 100
            comment = []
            
            data["msg"]["name"] = people.display_name
            sex = people.get_info_value("性别", "男")
            if sex not in ["男", "女"]:
                sex = "男"

            total_score = round(dimension_score, 2)
            normsdist_score = normsdist(((total_score - average_value) *1.00)/standard_diff_value*1.00) * 100
            data["msg"]["total"] = total_score

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
                if substandard_score_map[info["name"]] >= 100:
                    comment = POSITIVE_COMMENTS[info["name"]].split('/')
                    positive_comments.append(comment[random.randint(0,len(comment)-1)])
                elif substandard_score_map[info["name"]] < 75:
                    comment = NEGATIVE_COMMENTS[info["name"]].split('/')
                    negative_comments.append(comment[random.randint(0,len(comment)-1)])
                    negative_quotas.append(info["name"])

                percentage_score = round(normdist_score_map[info["name"]], 2)
                if percentage_score > 100:
                    info["score"] = 10
                else:
                    for index, index_score in enumerate(SCORE_MAP):
                        if percentage_score <= index_score:
                            info["score"] = index + 1
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

class BlockStatusView(AuthenticationExceptView, WdCreateAPIView):

    POST_CHECK_REQUEST_PARAMETER = ('survey_id', 'project_id','block_id')

    def post(self, request, *args, **kwargs):
        user_question_answer_list = []
        people_qs = People.objects.filter_active(user_id=self.request.user.id)
        self.evaluated_people_id = self.request.data.get("evaluated_people_id", 0)
        if not people_qs.exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.PERMISSION_FAIL)
        people = people_qs[0]
        
        surveyinfoquery = SurveyInfo.objects.filter_active(survey_id=self.survey_id,project_id=self.project_id).first()
        if not surveyinfoquery:
            return general_json_response(status.HTTP_200_OK, ErrorCode.NOT_EXISTED)
        surveyinfo = json.loads(surveyinfoquery.block_info)
        configinfo = json.loads(surveyinfoquery.config_info)
        # exit if not by part
        if configinfo['test_type']!=Survey.TEST_TYPE_BY_PART:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"isfinish":int(True)})        
        blockquery = UserSurveyBlockStatus.objects.filter_active(people_id=people.id,survey_id=self.survey_id,project_id=self.project_id,status=20,is_finish=True)
        if self.evaluated_people_id>0:
            blockquery.filter(evaluated_people_id=self.evaluated_people_id)
        finishedblocks = blockquery.values_list('block_id',flat=True)
        if not finishedblocks:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"isfinish":int(False)})
        surveyblocks = set([info['id'] for info in surveyinfo])
        finishedblocks = set(finishedblocks)
        finishedblocks.add(self.block_id)
        if len(surveyblocks) > len(surveyblocks & finishedblocks):
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"isfinish":int(False)})
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"isfinish":int(True)}) 

class AnonymousEntryView(AuthenticationExceptView, WdCreateAPIView):

    def survey_register_normal(self, account, pwd, survey_id_base64, assess_id_base64):
        survey_id = 0
        assess_id = base64.b64decode(assess_id_base64)
        try:
            project = AssessProject.objects.get(id=assess_id)
            #check register balance
            balance = Balance.objects.filter(enterprise_id=project.enterprise_id,sku__lte=2,validto__gte=date.today()).first()
            if balance:
                if balance.number<1:
                    return ErrorCode.OVERLIMIT
                else:
                    Consume.objects.create(balance_id=balance.id,
                                           number=1)
        except:
            err_logger.error("project not found: %s" % assess_id)
            return ErrorCode.INVALID_INPUT

        user, code = UserAccountUtils.user_register(pwd,account,role_type=AuthUser.ROLE_ANONYMOUS)
        if code != ErrorCode.SUCCESS:
            return code

        people = People.objects.create(user_id=user.id, username=account)
        EnterpriseAccount.objects.create(enterprise_id=project.enterprise_id,account_name=user.account_name,user_id=user.id,people_id=people.id)
        
        try:
            send_one_user_survey(project.id, people.id)
        except Exception, e:
            err_logger.error("people survey relation error, msg: %s" %e)
        return ErrorCode.SUCCESS, user, project.enterprise_id


    def post(self, request, *args, **kwargs):
        survey_id_base64 = self.request.data.get("bs", None)
        assess_id_base64 = self.request.data.get("ba", None)
        rst_code = ErrorCode.SUCCESS
        enterprise = 0

        if not assess_id_base64:
            err_logger.error("ba field must not be empty for anonymous assess")
            return general_json_response(status.HTTP_200_OK, rst_code, {"is_login": ErrorCode.INVALID_INPUT, "user_info": None})
        
        account = str(uuid.uuid4())
        pwd = "0000"

        rst_code, user, enterprise = self.survey_register_normal(account, pwd, survey_id_base64, assess_id_base64)
        if not BaseOrganization.objects.filter(enterprise_id=enterprise).first():
            enterprise = 0
        try:
            user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
            user_info = people_login(request, user, self.get_serializer_context())
            user_info['enterprise'] = enterprise
        except Exception, e:
            err_logger.error("Register_FOR_Login error, msg is %s" % e)
            user_info = None
        return general_json_response(status.HTTP_200_OK, rst_code, {"is_login": err_code, "user_info": user_info})