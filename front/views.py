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
from utils.logger import get_logger
from utils.rpc_service.report_service import ReportService
from utils.regular import RegularUtils
from utils.response import ErrorCode, general_json_response
from utils.views import WdListCreateAPIView, WdListAPIView, WdCreateAPIView, AuthenticationExceptView, \
    WdRetrieveUpdateAPIView, WdRetrieveAPIView
from wduser.models import AuthUser, People, PeopleOrganization, Organization, EnterpriseInfo, EnterpriseAccount, \
    PeopleAccount
from wduser.serializers import UserBasicSerializer, OrganizationBasicSerializer
from wduser.user_utils import UserAccountUtils

logger = get_logger("front")


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
    # 如果 EA表上线
    # ea_qs = EnterpriseAccount.objects.filter(account_name=account, enterprise_id=enterprise_qs[0].id)
    # if ea_qs.count() == 1:
    #     user_want_login_obj = AuthUser.objects.get(id=ea_qs[0].user_id)
    #     return ErrorCode.SUCCESS, u"ok", user_want_login_obj
    # else:
    #     au_qs = AuthUser.objects.filter(Q(phone=account)|Q(email=account))
    #     au_qs = au_qs.filter(is_active=True)
    #     if au_qs.count() == 1:
    #         return ErrorCode.SUCCESS, u"ok", au_qs[0]
    # return ErrorCode.USER_ACCOUNT_NOT_FOUND, u'找不到该用户', None
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
                logger.info("peopke_id can not find people user obj")
                pass
        return ErrorCode.FAILURE, None

    def post(self, request, *args, **kwargs):
        link = request.data.get('enterprise_dedicated_link', None)
        account = request.data.get('account', None)
        # account_type = request.data.get('account_type', None)
        pwd = request.data.get("pwd", None)
        if account is None or pwd is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        # ret, user = self.find_user_with_account(account, account_type)
        # if ret == ErrorCode.SUCCESS:
        #     pass
        # else:
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
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        user_info = people_login(request, user, self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)
        # return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"user_info": user_info, "login_account": account})
#


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
            logger.error("web logout error, msg(%s)" % e)
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
            logger.error("project not found: %s" % assess_id)
            return ErrorCode.INVALID_INPUT
        if project.distribute_type != AssessProject.DISTRIBUTE_OPEN:
            logger.error("project is not open: %s" % project.id)
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
            logger.error("people survey relation error, msg: %s" %e)
        return ErrorCode.SUCCESS, user

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
            rst_code, user = self.survey_register_normal(account, pwd, survey_id_base64, assess_id_base64)
        # 注册后返回用户信息以便直接跳转登陆
        try:
            # 理论成功创建用户应该都合法，err_code只是复用代码
            user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
            user_info = people_login(request, user, self.get_serializer_context())
        # except:
        except Exception, e:
            logger.error("Register_FOR_Login error, msg is %s" % e)
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
        logger.debug("survey_info.test_type is %s" % survey_info.test_type)
        if survey_info.test_type != SurveyInfo.TEST_TYPE_BY_QUESTION:
            block_info = json.loads(survey_info.block_info)
            if block_info:
                # 如果有块信息
                # logger.info("all_%s" % block_info)
                this_block = {}
                for block in block_info:
                    # logger.info("%s_%s" % (str_check(self.block_id), str_check(block.get("id", 0))))
                    if str(self.block_id) == str(block.get("id", 0)):
                        this_block = block
                        break
                # 判断当前块是不是顺序答题
                logger.debug("this_block.order_number is %s" % this_block.get("order_number", 0))
                if this_block.get("order_number", 0):
                    # logger.info("t_%s" % this_block)
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
                            logger.debug("block_id, survey_id, project_id, people_id is %s, %s, %s, %s" %(
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


class UserAnswerQuestionView(WdListCreateAPIView):
    u"""用户回答"""

    model = UserQuestionAnswerInfo
    serializer_class = None
    # serializer_class = UserQuestionInfoSerializer

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
        "DISC_NEW": 'self.get_professional_value',
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
    }

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
            logger.error("get report data error, msg: %s" % e)
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
            logger.error("get report data error, msg: %s " % e)
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
            logger.error("get report data error, msg: %s " % e)
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
            logger.error("get report data error, msg: %s " % e)
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
            logger.error("get report data error, msg: %s " % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

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
            logger.error("get report data error, msg: %s " % e)
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
            logger.error("get report data error, msg: %s " % e)
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
                    {"name": "乐观积极", "score": 6, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Optimistic and positive"},
                    {"name": "自信坚韧", "score": 8, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Confident and tenacity"},
                    {"name": "合理归因", "score": 7, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Reasoning"},
                    {"name": "情绪调节", "score": 9, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Emotion regulation"},
                    {"name": "意义寻求", "score": 5, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Meaning pursuit"},
                    {"name": "自主定向", "score": 7, "raw_score": 57.5, "percentage": '15.4%',"en_name": "Autonomy and direction"},
                    {"name": "专注投入", "score": 4, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Devotion"},
                    {"name": "自我拓展", "score": 3, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Self enhancing"},
                    {"name": "灵活变通", "score": 2, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Flexibility"},
                    {"name": "包容差异", "score": 9, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Diversity"},
                    {"name": "亲和利他", "score": 7, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Affinity and altruism"},
                    {"name": "自我悦纳", "score": 6, "raw_score": 57.5, "percentage": '15.4%', "en_name": "Self acceptance"},

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
            logger.error("get report data error, msg: %s " % e)
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
                # {'name': '安全健康', 'score': 100, 'dimension': '安全保障需求'},
                # {'name': '环境舒适', 'score': 90, 'dimension': '安全保障需求'},
                # {'name': '物质保障', 'score': 80, 'dimension': '安全保障需求'},
                # {'name': '休闲娱乐', 'score': 70, 'dimension': '安全保障需求'},
                # {'name': '职业稳定', 'score': 60, 'dimension': '安全保障需求'},
                # {'name': '亲和倾向', 'score': 40, 'dimension': '情感归属需求'},
                # {'name': '友谊友爱', 'score': 30, 'dimension': '情感归属需求'},
                # {'name': '关系信任', 'score': 20, 'dimension': '情感归属需求'},
                # {'name': '人际支持', 'score': 20, 'dimension': '情感归属需求'},
                # {'name': '群体归属', 'score': 20, 'dimension': '情感归属需求'},
                # {'name': '寻求认可', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '获得肯定', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '声望地位', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '自我尊重', 'score': 10, 'dimension': '尊重认可需求'},
                # {'name': '自主决定', 'score': 10, 'dimension': '尊重认可需求'},
                # {'name': '目标定向', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '能力成长', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '探索创新', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '成就导向', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '权力影响', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '助人利他', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '责任担当', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '意义追求', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '使命驱动', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '社会促进', 'score': 10, 'dimension': '使命利他需求'},

            ],
            # 指标（生活）
            "chart2": [
                # {'name': '安全健康', 'score': 100, 'dimension': '安全保障需求'},
                # {'name': '环境舒适', 'score': 100, 'dimension': '安全保障需求'},
                # {'name': '物质保障', 'score': 100, 'dimension': '安全保障需求'},
                # {'name': '休闲娱乐', 'score': 100, 'dimension': '安全保障需求'},
                # {'name': '职业稳定', 'score': 100, 'dimension': '安全保障需求'},
                # {'name': '亲和倾向', 'score': 40, 'dimension': '情感归属需求'},
                # {'name': '友谊友爱', 'score': 30, 'dimension': '情感归属需求'},
                # {'name': '关系信任', 'score': 20, 'dimension': '情感归属需求'},
                # {'name': '人际支持', 'score': 20, 'dimension': '情感归属需求'},
                # {'name': '群体归属', 'score': 20, 'dimension': '情感归属需求'},
                # {'name': '寻求认可', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '获得肯定', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '声望地位', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '自我尊重', 'score': 10, 'dimension': '尊重认可需求'},
                # {'name': '自主决定', 'score': 10, 'dimension': '尊重认可需求'},
                # {'name': '目标定向', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '能力成长', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '探索创新', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '成就导向', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '权力影响', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '助人利他', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '责任担当', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '意义追求', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '使命驱动', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '社会促进', 'score': 10, 'dimension': '使命利他需求'},

            ],
            # 指标（工作）
            "chart3": [
                # {'name': '亲和倾向', 'score': 100, 'dimension': '情感归属需求'},
                # {'name': '友谊友爱', 'score': 100, 'dimension': '情感归属需求'},
                # {'name': '关系信任', 'score': 100, 'dimension': '情感归属需求'},
                # {'name': '人际支持', 'score': 100, 'dimension': '情感归属需求'},
                # {'name': '群体归属', 'score': 100, 'dimension': '情感归属需求'},
                # {'name': '安全健康', 'score': 50, 'dimension': '安全保障需求'},
                # {'name': '环境舒适', 'score': 40, 'dimension': '安全保障需求'},
                # {'name': '物质保障', 'score': 30, 'dimension': '安全保障需求'},
                # {'name': '休闲娱乐', 'score': 30, 'dimension': '安全保障需求'},
                # {'name': '职业稳定', 'score': 30, 'dimension': '安全保障需求'},
                #
                # {'name': '寻求认可', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '获得肯定', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '声望地位', 'score': 20, 'dimension': '尊重认可需求'},
                # {'name': '自我尊重', 'score': 10, 'dimension': '尊重认可需求'},
                # {'name': '自主决定', 'score': 10, 'dimension': '尊重认可需求'},
                # {'name': '目标定向', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '能力成长', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '探索创新', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '成就导向', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '权力影响', 'score': 10, 'dimension': '成长成就需求'},
                # {'name': '助人利他', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '责任担当', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '意义追求', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '使命驱动', 'score': 10, 'dimension': '使命利他需求'},
                # {'name': '社会促进', 'score': 10, 'dimension': '使命利他需求'},

            ],
            # 维度名  分值
            "chart4": [
                # {'name': '安全保障需求', 'score': 100, },
                # {'name': '使命利他需求', 'score': 90, },
                # {'name': '成长成就需求', 'score': 80, },
                # {'name': '尊重认可需求', 'score': 70, },
                # {'name': '情感归属需求', 'score': 60, },
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
            logger.error("get report data error, msg: %s " % e)
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
            logger.error("get report data error, msg: %s" % e)
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
            logger.error("get report data error, msg: %s" % e)
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
            logger.error("get report data error, msg: %s" % e)
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
            logger.error("get report data error, msg: %s" % e)
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
            logger.error("get report data error, msg: %s" % e)
            return default_data, ErrorCode.INVALID_INPUT
        return default_data, ErrorCode.SUCCESS

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
        :param kwargs:
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
            logger.error("ReportDataView error, msg is %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": "%s" %e})


class FinishTxTView(WdRetrieveAPIView):
    GET_CHECK_REQUEST_PARAMETER = ("project_id", )
    model = AssessProject
    serializer_class = AssessmentBasicSerializer

    # def get(self, request, *args, **kwargs):
    #     try:
    #         obj = AssessProject.objects.get(id=self.assess_id)
    #     except:
    #         logger.error("assessproject not exists error %s" % e)
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
        logger.debug("report callback of %s, %s" %(personal_result_id, report_status))
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