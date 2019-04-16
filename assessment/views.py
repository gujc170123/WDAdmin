# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import datetime
import os
import re
import shutil
import time
import json
import base64
from urllib import quote

from django.contrib.auth.hashers import make_password
from django.db.models import Q
from rest_framework.parsers import MultiPartParser
from django.http import FileResponse, HttpResponse

# Create your views here.
from rest_framework import status

from WeiDuAdmin import settings
from assessment.assess_utils import AssessImportExport
from assessment.models import AssessProject, AssessOrganization, AssessSurveyRelation, \
    AssessGatherInfo, AssessProjectSurveyConfig, AssessUser, AssessSurveyUserDistribute
from assessment.serializers import AssessmentBasicSerializer, \
    AssessmentSurveyRelationPostSerializer, AssessmentSurveyRelationGetSerializer, AssessGatherInfoSerializer, \
    AssessProjectSurveyConfigSerializer, AssessmentSurveyRelationDetailGetSerializer, AssessUserSerializer, \
    Assess360TestUserStatisticsSerialzier
from assessment.tasks import send_survey_active_codes, distribute_project, \
    statistics_user_count, statistics_project_survey_user_count, get_people_list_task, file_task, search_key_words, \
    assess_people_create_in_sql_task, import_assess_user_task_0916
from front.models import PeopleSurveyRelation, SurveyInfo, SurveyQuestionInfo, UserQuestionAnswerInfo
from front.tasks import get_360_report
from question.models import Question
from research.models import ResearchModel
from research.serializers import ResearchModelDetailSerializer
from survey.models import SurveyQuestionResult
from utils import data2file, zip_folder, get_random_char, get_random_int
from utils.aliyun.email import EmailUtils
from utils.aliyun.oss import AliyunOss
from utils.cache.cache_utils import FileStatusCache
from utils.excel import ExcelUtils
from utils.logger import get_logger
from utils.regular import RegularUtils, Convert
from utils.response import general_json_response, ErrorCode
from utils.views import WdListCreateAPIView, WdRetrieveUpdateAPIView, WdDestroyAPIView, \
    WdExeclExportView, WdListAPIView, WdCreateAPIView, AuthenticationExceptView
from wduser.models import PeopleOrganization, People, Organization, AuthUser, RoleUser, RoleBusinessPermission, \
    BusinessPermission, RoleUserBusiness, EnterpriseAccount, PeopleAccount
from wduser.serializers import PeopleSerializer, PeopleSerializer360
from survey.models import Survey

logger = get_logger("assessment")
DINGZHI_4_TYPE_ACCOUNT = [4, 5, 1, -1]


def polling_survey(random_num, random_index, polling_list):
    y = random_num * random_index % len(polling_list)
    his_survey_list = polling_list[y:y + random_num]
    if y + random_num > len(polling_list):
        his_survey_list += polling_list[0: (random_num - (len(polling_list) - y))]
    return his_survey_list, random_index + 1


def delete_assesssurveyuserdistribute(assess_id, people_ids):
    assesssurveyuserdistribute_qs = AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id)
    for assesssurveyuserdistribute_obj in assesssurveyuserdistribute_qs:
        distribute_people_ids = json.loads(assesssurveyuserdistribute_obj.people_ids)
        for id in people_ids:
            if id in distribute_people_ids:
                distribute_people_ids.remove(id)
        new_people_ids = json.dumps(distribute_people_ids)
        assesssurveyuserdistribute_obj.people_ids = new_people_ids
        assesssurveyuserdistribute_obj.save()


def get_people_ids_qs(assess_id):
    org_codes_qs = AssessOrganization.objects.filter_active(assess_id=assess_id).values_list('organization_code', flat=True)
    if not org_codes_qs.exists():
        return ErrorCode.PROJECT_ORG_EMPTY_ERROR, u'项目组织为空', None
    people_org_qs_ids = PeopleOrganization.objects.filter_active(org_code__in=org_codes_qs).distinct()
    if not people_org_qs_ids.exists():
        return ErrorCode.ORG_PEOPLE_IN_ASSESS_ERROR, u"项目组织下没有人", None
    return ErrorCode.SUCCESS, None, people_org_qs_ids


def get_org_codes(org_codes):
    org_list = []
    for org_code in org_codes:
        org_list.append(org_code["identification_code"])
    return org_list


def check_account_in_enterprise(account, all_user_account, new_account_name=[]):
    if account in all_user_account:
        return ErrorCode.FAILURE
    if account in new_account_name:
        return ErrorCode.FAILURE
    return ErrorCode.SUCCESS


def check_org(org_codes):
    try:
        for org_code in org_codes:
            org_obj = Organization.objects.filter_active(id=org_code["id"], identification_code=org_code["identification_code"])
            if not org_obj.exists():
                return ErrorCode.FAILURE
        return ErrorCode.SUCCESS
    except Exception, e:
        logger.error("check input org_id_code_error %s" % e)
        return ErrorCode.FAILURE


def get_all_account_in_enterprise(enterpeise_id):
    all_assess_ids = AssessProject.objects.filter_active(enterprise_id=enterpeise_id).values_list('id', flat=True)
    all_assessuser_ids = AssessUser.objects.filter_active(assess_id__in=all_assess_ids).values_list('people_id',
                                                                                                    flat=True).distinct()
    all_people_ids = People.objects.filter_active(id__in=all_assessuser_ids).values_list('user_id',
                                                                                         flat=True).distinct()
    all_user_account = AuthUser.objects.filter(id__in=all_people_ids).values_list('account_name', flat=True).distinct()
    return all_user_account


def do_one_infos(infos):
    try:
        key_infos = []
        for info in infos:
            key_info = dict()
            info_id = info.get('id', None)
            info_value = info.get('info_values', None)
            info_name = info.get('info_name', None)
            if info_name and info_value:
                key_info["key_name"] = info_name
                key_info["key_value"] = info_value
                key_info["key_id"] = info_id
                key_infos.append(key_info)
        return key_infos
    except Exception, e:
        logger.error('add one do his infos error %s' % e)
        return None


def do_org(finish_peoples):
    try:
        people_org_list = []
        for finish_people in finish_peoples:
            people = finish_people[0]
            org_codes = finish_people[1]["org_codes"]
            ops = finish_people[1]['ops']
            # 2表示修改
            if ops == 2:
                PeopleOrganization.objects.filter_active(people_id=people.id).update(is_active=False)
            new_codes = []
            for org_code in org_codes:
                org_code = str_check(org_code)
                po_qs = PeopleOrganization.objects.filter_active(
                    people_id=people.id, org_code=org_code
                    )
                if (not po_qs.exists()) and (org_code not in new_codes):
                    people_org_list.append(
                        PeopleOrganization(
                            people_id=people.id, org_code=org_code
                            )
                    )
                    new_codes.append(org_code)
        PeopleOrganization.objects.bulk_create(people_org_list)
        return ErrorCode.SUCCESS, None
    except Exception, e:
        logger.error("do_org, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u'组织修改失败'


def str_check(str_obj):
    if type(str_obj) == int or type(str_obj) == long:
        str_obj = str(long(str_obj))
    elif type(str_obj) == float:
        str_obj = str(long(str_obj))
    return str_obj


def get_orgs_info(info):
    org_names = []
    for name in info:
        if name:
            org_names.append(name)
    return org_names


def get_org(org_names, assess_id, index=0, parent_id=0):
    # 根据项目id 和组织名字和父组织id找到该组织
    org_qs = Organization.objects.filter_active(assess_id=assess_id, name=org_names[index], parent_id=parent_id)
    if not org_qs or org_qs.count() > 1:
        return None
    org = org_qs[0]
    if index == len(org_names) - 1:
        return org
    return get_org(org_names, assess_id, index+1, org.id)


def get_active_code():
    return get_random_int(8)


def get_mima(mima):
    mima = str_check(mima)  # 密码
    mima = str('123456' if not mima else mima)
    return make_password(mima)


def check_survey_if_has_distributed(assess_id, survey_id):
    # check_survey_if_has_distributed(assess_id,survey_id)
    # return 分发的人的id的列表
    distribute_users = AssessSurveyUserDistribute.objects.filter_active(
        assess_id=assess_id, survey_id=survey_id
    )
    if distribute_users.exists():
        distribute_user_ids = json.loads(
            distribute_users.values_list("people_ids", flat=True)[0])
    else:
        # 否则就是空
        distribute_user_ids = []
    return distribute_user_ids, distribute_users


class AssessmentListCreateView(WdListCreateAPIView):
    u"""
    GET：测评项目获取列表
    POST：创建测评项目"""

    model = AssessProject
    serializer_class = AssessmentBasicSerializer
    POST_DATA_ID_RESPONSE = True
    POST_CHECK_REQUEST_PARAMETER = ('enterprise_id', 'name')
    GET_CHECK_REQUEST_PARAMETER = ('enterprise_id', )
    SEARCH_FIELDS = ('name', )
    FILTER_FIELDS = ("assess_type", )

    def post_check_parameter(self, kwargs):
        rst_code = super(AssessmentListCreateView, self).post_check_parameter(kwargs)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        assess_type = self.request.data.get("assess_type", AssessProject.TYPE_ORGANIZATION)
        # 新建项目取消组织必填
        # if int(assess_type) == AssessProject.TYPE_ORGANIZATION:
        #     org_infos = self.request.data.get('org_infos', [])
        #     if not org_infos:
        #         return ErrorCode.INVALID_INPUT
        return rst_code

    def qs_order_by(self, qs):
        # TODO: 测验人次排序
        order_by = self.get_order_by_name()
        if order_by == "-create_time":
            return qs.order_by("-id")
        elif order_by == "create_time":
            return qs.order_by("id")
        elif order_by == "-name":
            return qs.order_by(Convert('name', 'gbk').desc())
        elif order_by == "name":
            return qs.order_by(Convert('name', 'gbk').asc())
        elif order_by == "-test_count":
            return qs.order_by("-user_count")
        elif order_by == "test_count":
            return qs.order_by("user_count")
        elif order_by == "-begin_time":
            return qs.order_by("-begin_time")
        elif order_by == "begin_time":
            return qs.order_by("begin_time")
        else:
            return super(AssessmentListCreateView, self).qs_order_by(qs)

    def qs_filter(self, qs):
        get_360_report.delay(self.enterprise_id)
        qs = super(AssessmentListCreateView, self).qs_filter(qs)
        if self.enterprise_id == 'all':
            pass
        else:
            qs = qs.filter(enterprise_id=self.enterprise_id)
        project_status = self.request.GET.get("project_status", None)
        now = datetime.datetime.now()
        if project_status is not None and len(project_status) > 0:
            project_status = int(project_status)
            if project_status == AssessProject.STATUS_WAITING:
                qs = qs.filter(Q(begin_time__gt=now) | Q(begin_time__isnull=True))
            elif project_status == AssessProject.STATUS_WORKING:
                qs = qs.filter(begin_time__lt=now, end_time__gt=now)
            elif project_status == AssessProject.STATUS_END:
                qs = qs.filter(end_time__lt=now)
        # 设置问卷是否发布过
        #AssessProject.objects.filter_active(begin_time__gt=now, has_distributed=False).update(has_distributed=True)
        distribute_project.delay(self.enterprise_id)
        statistics_user_count.delay(self.enterprise_id)
        return qs

    def qs_business_role(self, qs):
        user = self.request.user
        if user.role_type == AuthUser.ROLE_SUPER_ADMIN:
            return qs
        role_ids = RoleUser.objects.filter_active(
            user_id=self.request.user.id).values_list("role_id", flat=True)
        pm_ids = RoleBusinessPermission.objects.filter_active(
            role_id__in=role_ids).values_list("permission_id", flat=True)
        if BusinessPermission.PERMISSION_ALL in pm_ids or BusinessPermission.PERMISSION_ENTERPRISE_BUSINESS in pm_ids \
                or BusinessPermission.PERMISSION_ENTERPRISE_MASTER in pm_ids or \
                        BusinessPermission.PERMISSION_ENTERPRISE_ALL_SEE in pm_ids:
            return qs
        if BusinessPermission.PERMISSION_ENTERPRISE_PART in pm_ids:
            if self.enterprise_id != 'all':
                has_permissions = RoleUserBusiness.objects.filter_active(
                    user_id=self.request.user.id, model_type=RoleUserBusiness.MODEL_TYPE_ENTERPRISE,
                    model_id=self.enterprise_id
                ).exists()
                if has_permissions:
                    return qs
        role_user_qs = RoleUserBusiness.objects.filter_active(
            user_id=self.request.user.id, model_type=RoleUserBusiness.MODEL_TYPE_PROJECT)
        model_ids = role_user_qs.values_list("model_id", flat=True)
        return qs.filter(id__in=model_ids)

    def perform_create(self, serializer):
        super(AssessmentListCreateView, self).perform_create(serializer)
        org_infos = self.request.data.get('org_infos', [])
        org_rel = []
        for org_info in org_infos:
            org_rel.append(AssessOrganization(
                assess_id=serializer.data["id"],
                organization_id=org_info["id"],
                organization_code=org_info["identification_code"]
            ))
        AssessOrganization.objects.bulk_create(org_rel)
        RoleUserBusiness.objects.create(
            user_id=self.request.user.id, model_type=RoleUserBusiness.MODEL_TYPE_PROJECT,
            model_id=serializer.data["id"]
        )


class AssessRetrieveUpdateDestroyView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""测评项目详情接口
    GET：获取详情
    PUT：修改信息
    DELETE：删除项目"""
    # TODO： 项目删除，需要检查是否有问卷，如有问卷，不能删除

    model = AssessProject
    serializer_class = AssessmentBasicSerializer

    def post_check_parameter(self, kwargs):
        rst_code = super(AssessRetrieveUpdateDestroyView, self).post_check_parameter(kwargs)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        is_answer_survey_by_order = self.request.data.get("is_answer_survey_by_order", False)
        if is_answer_survey_by_order:
            orders = self.request.data.get("orders", [])
            if not orders:
                return ErrorCode.INVALID_INPUT
        # 随机数判断 ,增加 原本是 变成 否，则清掉原来的全部
        has_survey_random = self.request.data.get("has_survey_random", None)
        if has_survey_random is not None:
            # 如果传入是False
            if not has_survey_random:
                #  将随机数据清除
                AssessProject.objects.filter_active(id=self.get_object().id).update(has_survey_random=False, survey_random_number=0)
                AssessSurveyRelation.objects.filter_active(assess_id=self.get_id()).update(survey_been_random=False)
            elif int(self.request.data.get("survey_random_number", 0)) > len(self.request.data.get("survey_ids_random", [])):
                return ErrorCode.SURVEY_RAMDOM_NUM_ERROR

        self.begin_time = self.request.data.get("begin_time", None)
        self.end_time = self.request.data.get("end_time", None)
        obj = self.get_object()
        self.old_begin_time = obj.begin_time
        self.old_end_time = obj.end_time
        return rst_code

    def for_random_func(self, assess_id):
        # {"assess_id": "6","survey_ids": ["84", "85"],"survey_ids_random": ["84","85","86"]}
        survey_ids_random = self.request.data.get("survey_ids_random", [])
        # 依次修改每个被关联问卷的随机字段
        AssessSurveyRelation.objects.filter_active(assess_id=assess_id).update(survey_been_random=False)
        survey_ids = [int(survey_id) for survey_id in survey_ids_random]
        # for survey_info in survey_ids_random:
        AssessSurveyRelation.objects.filter_active(assess_id=assess_id, survey_id__in=survey_ids).update(survey_been_random=True)

    def perform_update(self, serializer):
        super(AssessRetrieveUpdateDestroyView, self).perform_update(serializer)
        assess_id = self.get_id()
        org_infos = self.request.data.get('org_infos', None)
        ct = time.time()
        if self.begin_time and self.begin_time != self.old_begin_time:
            SurveyInfo.objects.filter_active(project_id=assess_id).update(begin_time=self.begin_time)
            begin_timestamp = time.mktime(time.strptime(self.begin_time, "%Y-%m-%d %H:%M:%S"))
            if begin_timestamp > ct:
                PeopleSurveyRelation.objects.filter_active(
                    project_id=assess_id,
                    status__in=[PeopleSurveyRelation.STATUS_DOING, PeopleSurveyRelation.STATUS_EXPIRED]
                ).update(status=PeopleSurveyRelation.STATUS_NOT_BEGIN)
        if self.end_time and self.end_time != self.old_end_time:
            SurveyInfo.objects.filter_active(project_id=assess_id).update(end_time=self.end_time)
            end_timestamp = time.mktime(time.strptime(self.end_time, "%Y-%m-%d %H:%M:%S"))
            if end_timestamp < ct:
                PeopleSurveyRelation.objects.filter_active(
                    project_id=assess_id,
                    status__in=[PeopleSurveyRelation.STATUS_DOING, PeopleSurveyRelation.STATUS_NOT_BEGIN]
                ).update(status=PeopleSurveyRelation.STATUS_EXPIRED)
            if end_timestamp > ct:
                PeopleSurveyRelation.objects.filter_active(
                    project_id=assess_id,
                    status=PeopleSurveyRelation.STATUS_EXPIRED
                ).update(status=PeopleSurveyRelation.STATUS_DOING)

        is_answer_survey_by_order = self.request.data.get("is_answer_survey_by_order", False)
        if is_answer_survey_by_order:
            orders = self.request.data.get("orders", [])
            for index, order_id in enumerate(orders):
                AssessSurveyRelation.objects.filter_active(id=order_id).update(order_number=index+1)

        # 取消组织
        if org_infos is not None:
            AssessOrganization.objects.filter(assess_id=assess_id).update(is_active=False)
            org_infos = self.request.data.get('org_infos', [])
            if org_infos:
                org_rel = []
                for org_info in org_infos:
                    org_rel.append(AssessOrganization(
                        assess_id=assess_id,
                        organization_id=org_info["id"],
                        organization_code=org_info["identification_code"]

                    ))
                AssessOrganization.objects.bulk_create(org_rel)

        has_survey_random = self.request.data.get("has_survey_random", False)
        if has_survey_random:
            self.for_random_func(assess_id)

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        now = datetime.datetime.now()
        # now = now.replace(tzinfo=pytz.timezone(settings.TIME_ZONE))
        if obj.begin_time is not None and now > obj.begin_time:
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_BEGIN_CAN_NOT_DELETE)
        logger.info('user_id %s want delete assess_id %s' % (self.request.user.id, obj.id))
        return super(AssessRetrieveUpdateDestroyView, self).delete(request, *args, **kwargs)

    def perform_destroy(self, instance):
        super(AssessRetrieveUpdateDestroyView, self).perform_destroy(instance)
        AssessOrganization.objects.filter(assess_id=self.get_id()).update(is_active=False)


class AssessSurveyRelationView(WdListCreateAPIView, WdDestroyAPIView):
    u"""项目与问卷的关联
    @POST: 关联项目问卷
    @GET: 查看关联的项目问卷列表
    @DELETE: 删除关联的问卷
    """
    model = AssessSurveyRelation
    p_serializer_class = AssessmentSurveyRelationPostSerializer
    g_serializer_class = AssessmentSurveyRelationGetSerializer
    POST_CHECK_REQUEST_PARAMETER = ("assess_id", "survey_ids")
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )
    DELETE_CHECK_REQUEST_PARAMETER = ("survey_ids", "assess_id")
    FILTER_FIELDS = ("assess_id", )

    def post_check_parameter(self, kwargs):
        rst_code = super(AssessSurveyRelationView, self).post_check_parameter(kwargs)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        assessment = AssessProject.objects.get(id=self.assess_id)
        # self.request.data["begin_time"] = assessment.begin_time
        # self.request.data["end_time"] = assessment.end_time
        self.request.data["custom_config"] = json.dumps({
            # "finish_redirect": assessment.finish_redirect,
            "assess_logo": assessment.assess_logo,
            # "advert_url": assessment.advert_url
        })
        self.assessment = assessment
        if AssessSurveyRelation.objects.filter_active(
                assess_id=self.assess_id,
                survey_id__in=[int(id) for id in self.survey_ids],
        ).exists():
            return ErrorCode.PROJECT_SURVEY_RELATION_REPEAT
        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        assess_survey = []
        for survey_id in self.survey_ids:
            assess_survey.append(AssessSurveyRelation(
                assess_id=self.assess_id,
                survey_id=survey_id,
                custom_config=self.request.data["custom_config"]

            ))
        AssessSurveyRelation.objects.bulk_create(assess_survey)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def get(self, request, *args, **kwargs):
        statistics_project_survey_user_count.delay(self.assess_id)
        return super(AssessSurveyRelationView, self).get(request, *args, **kwargs)

    def qs_order_by(self, qs):
        return qs.order_by("order_number")

    def qs_search(self, qs):

        # key_words 问卷名字
        key_words = self.request.GET.get("key_words", None)
        if not key_words:
            return qs
        # 模糊查询 得到问卷
        survey_qs = Survey.objects.filter_active(title__icontains=key_words)
        # 通过 survey_id__in  过滤
        qs = qs.filter(survey_id__in=survey_qs.values_list("id", flat=True))
        return qs

    def delete(self, request, *args, **kwargs):
        if "," in self.survey_ids:
            self.survey_ids = [int(obj_id) for obj_id in self.survey_ids.split(",")]
        else:
            self.survey_ids = [int(self.survey_ids)]
        if AssessSurveyRelation.objects.filter_active(assess_id=self.assess_id, survey_id__in=self.survey_ids, user_count__gt=0).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_SURVEY_USED_FORBID_DELETE)
        logger.info('user_id %s want delete assess_id %s with survey_ids %s' % (self.request.user.id, self.assess_id, self.survey_ids))
        AssessSurveyRelation.objects.filter_active(assess_id=self.assess_id, survey_id__in=self.survey_ids).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class AssessSurveyRelationDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""
    项目与问卷的关联详情
    @GET: 查看关联的问卷详情
    @PUT: 修改问卷配置
    """
    model = AssessSurveyRelation
    p_serializer_class = AssessmentSurveyRelationPostSerializer
    g_serializer_class = AssessmentSurveyRelationDetailGetSerializer

    def post_check_parameter(self, kwargs):
        rst_code = super(AssessSurveyRelationDetailView, self).post_check_parameter(kwargs)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        obj = self.get_object()
        try:
            survey_obj = Survey.objects.get(id=obj.survey_id)
        except:
            return ErrorCode.PROJECT_SURVEY_RELATION_VALID
        self.request.data["custom_config"] = json.dumps({
            # "finish_redirect": self.request.data.get("finish_redirect", obj.finish_redirect),
            "assess_logo": self.request.data.get("assess_logo", obj.assess_logo),
            "survey_name": self.request.data.get("survey_name", survey_obj.title),
            "en_survey_name": self.request.data.get("en_survey_name", survey_obj.en_title),
            # "advert_url": self.request.data.get("advert_url", obj.advert_url),
            # "distribute_type": self.request.data.get("distribute_type", obj.distribute_type),
        })
        return rst_code

    def perform_update(self, serializer):
        super(AssessSurveyRelationDetailView, self).perform_update(serializer)
        obj = self.get_object()
        if self.request.data.get("assess_logo", None) is not None:
            assess_logo = obj.assess_logo
            survey_info_qs = SurveyInfo.objects.filter_active(survey_id=obj.survey_id, project_id=obj.assess_id)
            for survey_info in survey_info_qs:
                survey_info.set_assess_log(assess_logo)


class AssessSurveyRelationDistributeView(WdListCreateAPIView):
    u"""
    项目与问卷的分发信息
    @GET: 查看关联的问卷分发信息
    @POST：分发按钮

    @version: 20180725 分发
    @GET：查看项目的分发信息
    @POST: 分发按钮
    """
    model = AssessSurveyRelation
    # serializer_class = AssessmentSurveyRelationDistributeSerializer
    POST_CHECK_REQUEST_PARAMETER = ("assess_id", )
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )

    def get_all_survey_finish_people_count(self, finish_people_ids, assess_id):
        """
        已完成的人数 = 有问卷的人数 - 人中有（未开始，已开放，答卷中, 已过期的人）
        即，应该问卷中只有已完成卷子的人
        """
        # 传入有问卷的人， 去掉所有卷子中有 未开始，未完成
        # 已完成的 = 有卷子的 - 有卷子的 - 做了一半的
        not_finish_count = PeopleSurveyRelation.objects.filter_active(project_id=assess_id,
                                                                      people_id__in=finish_people_ids,
                                                                      status__in=[
                                                                          PeopleSurveyRelation.STATUS_NOT_BEGIN,
                                                                          PeopleSurveyRelation.STATUS_DOING,
                                                                          PeopleSurveyRelation.STATUS_DOING_PART,
                                                                          PeopleSurveyRelation.STATUS_EXPIRED
                                                                      ]
                                                                      ).values_list(
            "people_id", flat=True).distinct().count()
        f_count = len(finish_people_ids) - not_finish_count
        return f_count

    def get_doing_survey_people_count(self, people_ids, assess_id):
        """
        已分发的人：有问卷子的人 - 卷子中有（完成的，过期的， 答卷的状态的人）
        """
        beign_count = PeopleSurveyRelation.objects.filter_active(project_id=assess_id,
                                                                      people_id__in=people_ids,
                                                                      status__in=[
                                                                          PeopleSurveyRelation.STATUS_FINISH,
                                                                          PeopleSurveyRelation.STATUS_DOING_PART
                                                                      ]
                                                                      ).values_list(
            "people_id", flat=True).distinct().count()
        not_count = len(people_ids) - beign_count
        return not_count

    def send_active_code(self, people_ids):
        send_survey_active_codes.delay(people_ids)

    def distribute360(self):
        role_surveys = AssessSurveyRelation.objects.filter_active(
            assess_id=self.assess_id).values("role_type", "survey_id")
        role_survey_map = dict()
        for role_survey in role_surveys:
            role_survey_map[role_survey["role_type"]] = role_survey["survey_id"]
        assess_users = AssessUser.objects.filter_active(
            assess_id=self.assess_id, role_type=AssessUser.ROLE_TYPE_SELF
        )
        new_distribute_people_ids = []
        for assess_user in assess_users:
            # 该自评人员的分发情况
            evaluated_people = People.objects.get(id=assess_user.people_id)
            for role_types in AssessUser.ROLE_CHOICES:
                role_type = role_types[0]
                if role_type == AssessUser.ROLE_TYPE_NORMAL:
                    continue
                if role_type in role_survey_map:
                    survey_id = role_survey_map[role_type]
                else:
                    return ErrorCode.PROJECT_SURVEY_RELATION_VALID
                survey = Survey.objects.get(id=survey_id)
                distribute_users = AssessSurveyUserDistribute.objects.filter_active(
                    assess_id=self.assess_id, evaluated_people_id=evaluated_people.id,
                    role_type=role_type, survey_id=survey_id
                )
                has_distribute = distribute_users.exists()
                if has_distribute:
                    distribute_user_ids = json.loads(
                        distribute_users.values_list("people_ids", flat=True)[0])
                else:
                    distribute_user_ids = []
                # 该角色下的评价人员
                role_people_ids = AssessUser.objects.filter_active(
                    assess_id=self.assess_id, people_id=evaluated_people.id, role_type=role_type
                ).values_list("role_people_id", flat=True)

                # TODO： 问卷同步到front
                people_survey_list = []
                for people_id in role_people_ids:
                    if people_id not in distribute_user_ids:
                        # TODO: 分发 发送短信或邮件 注意是否可以批量发送
                        survey_name = survey.title
                        if role_type != AssessUser.ROLE_TYPE_SELF:
                            survey_name = u"%s(评价%s)" %(survey.title, evaluated_people.username)
                        people_survey_list.append(PeopleSurveyRelation(
                            people_id=people_id,
                            survey_id=survey_id,
                            project_id=self.assess_id,
                            survey_name=survey_name,
                            role_type=role_type,
                            evaluated_people_id=evaluated_people.id

                        ))
                        distribute_user_ids.append(people_id)
                        if people_id not in new_distribute_people_ids:
                            new_distribute_people_ids.append(people_id)
                PeopleSurveyRelation.objects.bulk_create(people_survey_list)
                if has_distribute:
                    distribute_users.update(people_ids=json.dumps(distribute_user_ids))
                else:
                    AssessSurveyUserDistribute.objects.create(
                        assess_id=self.assess_id, survey_id=survey_id,
                        people_ids=json.dumps(distribute_user_ids),
                        evaluated_people_id=evaluated_people.id,
                        role_type=role_type
                    )
        self.send_active_code(new_distribute_people_ids)
        return ErrorCode.SUCCESS

    # 批量 2000K一次创建
    def distribute_normal(self):
        # 分发问卷
        def get_random_survey_distribute_info(assess_id, random_survey_qs):
            random_survey_ids = random_survey_qs.values_list("survey_id", flat=True)
            random_survey_total_ids = []
            for random_survey_id in random_survey_ids:
                asud_qs = AssessSurveyUserDistribute.objects.filter_active(
                    assess_id=assess_id, survey_id=random_survey_id
                )
                if asud_qs.exists():
                    d_user_ids = json.loads(asud_qs[0].people_ids)
                    if type(d_user_ids) != list:
                        d_user_ids = []
                    random_survey_total_ids.extend(d_user_ids)
            return random_survey_total_ids

        def polling_survey(random_num, random_index, polling_list):
            y = random_num * random_index % len(polling_list)
            his_survey_list = polling_list[y:y + random_num]
            if y + random_num > len(polling_list):
                his_survey_list += polling_list[0: (random_num - (len(polling_list) - y))]
            return his_survey_list, random_index + 1

        assess_id = self.assess_id
        people_ids = self.request.data.get("ids", None)
        if not people_ids:
            people_ids = AssessUser.objects.filter_active(assess_id=assess_id).values_list("people_id", flat=True).distinct()
            if not people_ids:
                return ErrorCode.ORG_PEOPLE_IN_ASSESS_ERROR   # 项目组织下没有人
        #  一以下可以单独拉出来 传入assess_id, people_id , ,给这个人发送问卷
        new_distribute_ids = []
        # 问卷初始状态
        assessment_obj = AssessProject.objects.get(id=assess_id)
        status = PeopleSurveyRelation.STATUS_DOING if assessment_obj.project_status == AssessProject.STATUS_WORKING else PeopleSurveyRelation.STATUS_NOT_BEGIN
        # 哪些问卷
        all_survey_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id).distinct().order_by("-order_number")
        if all_survey_qs.count() == 0:
            return ErrorCode.PROJECT_SURVEY_RELATION_VALID   # 项目没有关联问卷
        all_survey_ids = all_survey_qs.values_list("survey_id", flat=True)
        # 找到相关问卷的发送信息
        survey_assess_distribute_dict = {}
        for survey_id in all_survey_ids:
            asud_qs = AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id, survey_id=survey_id)
            if asud_qs.exists():
                dist_people_ids = json.loads(asud_qs[0].people_ids)
                if type(dist_people_ids) != list:
                    dist_people_ids = []
            else:
                AssessSurveyUserDistribute.objects.create(assess_id=assess_id, survey_id=survey_id, people_ids=json.dumps([]))
                dist_people_ids = []
            survey_assess_distribute_dict[survey_id] = dist_people_ids

        random_survey_qs = all_survey_qs.filter(survey_been_random=True)
        normal_survey_qs = all_survey_qs.filter(survey_been_random=False)

        normal_survey_ids = list(normal_survey_qs.values_list('survey_id', flat=True))
        row_random_survey_ids = list(random_survey_qs.values_list('survey_id', flat=True))
        random_distribute_people_info_out = get_random_survey_distribute_info(assess_id, random_survey_qs)

        random_num = assessment_obj.survey_random_number
        if random_num:
            if len(random_survey_qs) < random_num:
                random_num = len(random_survey_qs)
        random_index = assessment_obj.survey_random_index  # 随机标志位

        people_survey_b_create_list = []
        for people_id in people_ids:
            # 找到随机的问卷
            if random_num and random_survey_qs.exists() and (people_id not in random_distribute_people_info_out):
                random_survey_ids, random_index = polling_survey(random_num, random_index, row_random_survey_ids)
            else:
                random_survey_ids, random_index = [], random_index
            # 排序
            person_survey_ids_list = [i for i in all_survey_ids if i in list(set(normal_survey_ids).union(set(random_survey_ids)))]
            for survey_id in person_survey_ids_list:
                survey = Survey.objects.get(id=survey_id)
                distribute_users = survey_assess_distribute_dict[survey_id]
                if people_id not in distribute_users:
                    people_survey_b_create_list.append(PeopleSurveyRelation(
                        people_id=people_id,
                        survey_id=survey_id,
                        project_id=assess_id,
                        survey_name=survey.title,
                        status=status
                    ))
                    survey_assess_distribute_dict[survey_id].append(people_id)
                    if people_id not in new_distribute_ids:
                        new_distribute_ids.append(people_id)
            # 批量创建
            if len(people_survey_b_create_list) > 2000:
                PeopleSurveyRelation.objects.bulk_create(people_survey_b_create_list)
                logger.info("people_b_create_survey")
                people_survey_b_create_list = []
        # 发送最后一批问卷
        if people_survey_b_create_list:
            logger.info("people_b_create_survey")
            PeopleSurveyRelation.objects.bulk_create(people_survey_b_create_list)
        # 发激活码
        if new_distribute_ids:
            self.send_active_code(new_distribute_ids)
        # 保留发卷信息
        for survey_id in survey_assess_distribute_dict:
            AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id, survey_id=survey_id).update(people_ids=json.dumps(survey_assess_distribute_dict[survey_id]))
        # 轮询标志位
        assessment_obj.survey_random_index = random_index
        assessment_obj.save()
        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        self.assessment = AssessProject.objects.get(id=self.assess_id)
        if self.assessment.assess_type == AssessProject.TYPE_360:
            rst_code = self.distribute360()
        else:
            rst_code = self.distribute_normal()
        return general_json_response(status.HTTP_200_OK, rst_code)

    def get_project_url(self):
        # TODO: join-project interface
        project_id_bs64 = quote(base64.b64encode(str(self.assess_id)))
        return settings.CLIENT_HOST + '/people/join-project/?ba=%s&bs=0' % (project_id_bs64)

    def get_open_project_user_statistics(self):
        """
        开放测评人数统计：
        总人数 ： 有问卷的人数
        有问卷的人数： 有问卷的人数
        未分发的人数： 总人数 - 有问卷的人数 = 0
        已完成的人数： 有问卷的人数 - 人中有（未开始，已开放，答卷中的人）
        已分发（未开始，已分发的人） ：有问卷子的人 - 卷子中有（完成的，过期的， 答卷的状态的人）
        # 注意： 一个人有2张问卷的话，可以是一张已分发的状态，一张已完成的状态
        答卷中的人数： 有卷子数 - 已完成 - 已分发的
        分发数量： 0 开放问卷没有分发按钮

        1226修改，将状态已过期的人，归为已分发
        """
        user_qs = PeopleSurveyRelation.objects.filter_active(project_id=self.assess_id)
        all_count = user_qs.values_list("people_id", flat=True).distinct().count()
        people_with_survey_ids = user_qs.values_list('people_id', flat=True).distinct()
        wei_fen_fa = all_count - people_with_survey_ids.count()  # 未分发 就是 0
        yi_wan_cheng = self.get_all_survey_finish_people_count(people_with_survey_ids, self.assess_id)
        yi_fen_fa = self.get_doing_survey_people_count(people_with_survey_ids, self.assess_id)
        da_juan_zhong = people_with_survey_ids.count() - yi_wan_cheng - yi_fen_fa
        distribute_count = 0
        return {
            "count": all_count,  # 项目下人总数
            "doing_count": da_juan_zhong,  # 答卷中
            "not_begin_count": yi_fen_fa,  # 已开发
            "finish_count": yi_wan_cheng,  # 已完成
            "not_started": wei_fen_fa,  # 未分发
            "distribute_count": distribute_count  # 分发数量
        }

    def get_import_project_user_statistics(self):
        """
        组织型项目：
        总人数： 项目下的用户
        有问卷的人数
        未分发： 总人数 - 有问卷的人数
        已完成的人数： 有问卷的人数 - 人中有（未开始，已开放，答卷中的人）
        未开始这个状态： 项目没有开始问卷已经分发的状态
        已分发（未开始，已分发的人） ：有问卷子的人 - 卷子中有（完成的，过期的， 答卷的状态的人）
        答卷中： 有问卷的人数 - 已完成 - 已分发
        分发数量： 有问卷的人数不就得了？
        """
        po_qs = AssessUser.objects.filter_active(assess_id=self.assess_id).values_list("people_id", flat=True).distinct()
        all_count = po_qs.count()
        user_qs = PeopleSurveyRelation.objects.filter_active(project_id=self.assess_id)
        people_ids = user_qs.values_list('people_id', flat=True).distinct()
        wei_fen_fa = all_count - people_ids.count()  # 未分发
        yi_wan_cheng = self.get_all_survey_finish_people_count(list(people_ids), self.assess_id)
        # distribute_qs = AssessSurveyUserDistribute.objects.filter_active(assess_id=self.assess_id)
        yi_fen_fa = self.get_doing_survey_people_count(list(people_ids), self.assess_id)
        da_juan_zhong = people_ids.count() - yi_wan_cheng - yi_fen_fa
        # if distribute_qs.exists():
        #     pid_all = []
        #     for distribute_qs_one in distribute_qs:
        #         pids = json.loads(distribute_qs_one.people_ids)
        #         pid_all.extend(pids)
        #     distribute_count = People.objects.filter_active(id__in=set(pid_all)).count()
        # else:
        #     distribute_count = 0
        distribute_count = people_ids.count()
        return {
            "count": all_count,  # 项目下人总数，有卷子和没卷子的
            "doing_count": da_juan_zhong,  # 答卷中
            "not_begin_count": yi_fen_fa,  # 已分发，为开始的
            "finish_count": yi_wan_cheng,  # 完成的
            "not_started": wei_fen_fa,  # 没卷子的
            "distribute_count": distribute_count  # 分发数量
        }

    def get_distribute_info(self):
        project = AssessProject.objects.get(id=self.assess_id)
        if project.distribute_type == AssessProject.DISTRIBUTE_OPEN:
            user_statistics = self.get_open_project_user_statistics()
        else:
            user_statistics = self.get_import_project_user_statistics()
        org_ids = AssessOrganization.objects.filter_active(
            assess_id=self.assess_id).values_list("organization_id", flat=True)
        org_infos = Organization.objects.filter_active(id__in=org_ids).values("id", "name", "identification_code")
        return {
            "user_statistics": user_statistics,
            "distribute_type": project.distribute_type,
            "org_infos": org_infos
        }

    def get(self, request, *args, **kwargs):
        data = {
            "url": self.get_project_url(),
            "distribute_info": self.get_distribute_info()
        }
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)


class AssessSurveyUserExport(WdExeclExportView):
    u"""问卷人员导出"""

    def get(self, request, *args, **kwargs):
        assess_id = self.request.GET.get("assess_id", None)
        survey_ids = list(AssessSurveyRelation.objects.filter_active(
            assess_id=assess_id).values_list("survey_id", flat=True))
        if len(survey_ids) == 0:
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_PEOPLE_ERROR, {'msg': u'项目下没有参与人员'})
        org_codes = self.request.GET.get("org_codes", None)
        user = self.request.user
        email = user.email
        if not email:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_HAS_ERROR, {'msg': u'您没有邮箱,请检查,修改邮箱'})
        # 前往task修改
        # get_people_list_task(assess_id, org_codes, email, user.id)
        get_people_list_task.delay(assess_id, org_codes, email, user.id, is_simple=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {'msg': u"正在下载, 请检查邮箱 %s " % email})


class AssessGatherInfoView(WdListCreateAPIView):
    u"""项目收集信息"""

    model = AssessGatherInfo
    serializer_class = AssessGatherInfoSerializer
    POST_DATA_ID_RESPONSE = True
    POST_CHECK_REQUEST_PARAMETER = ('info_name', 'info_type')
    GET_CHECK_REQUEST_PARAMETER = ('assess_id', )
    FILTER_FIELDS = ('assess_id', )

    def post_check_parameter(self, kwargs):
        rst_code = super(AssessGatherInfoView, self).post_check_parameter(kwargs)
        # 如果有传入个人信息是否可见则
        # show_people_info = self.request.data.get('show_people_info', None)
        # if show_people_info is not None:
        #     assess_id = self.request.data.get('assess_id', None)
        #     AssessProject.objects.filter_active(id=assess_id).update(show_people_info=show_people_info)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        if self.info_type == AssessGatherInfo.INFO_TYPE_LIST:
            info_values = self.request.data.get("info_values", None)
            if not info_values:
                return ErrorCode.INVALID_INPUT
            setattr(self, 'info_values', info_values)
        return ErrorCode.SUCCESS

    def perform_create(self, serializer):
        super(AssessGatherInfoView, self).perform_create(serializer)
        if self.info_type == AssessGatherInfo.INFO_TYPE_LIST:
            obj = AssessGatherInfo.objects.get(id=serializer.data["id"])
            obj.config_info = json.dumps(self.info_values)
            obj.save()

    # def get(self, request, *args, **kwargs):
    #     info = AssessProject.objects.filter_active(id=self.assess_id).show_people_info
    #     ret = super(AssessGatherInfoView, self).get(request, *args, **kwargs)
    #     ret[2].append({'show_people_info': info})
    #     return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, ret)


# 8.31 一个接口获取自定义和系统信息
class AssessGatherAllInfoView(WdListCreateAPIView):
    u"""项目收集信息"""

    model = AssessGatherInfo
    serializer_class = AssessGatherInfoSerializer
    GET_CHECK_REQUEST_PARAMETER = ('assess_id',)
    FILTER_FIELDS = ('assess_id',)

    def qs_filter(self, qs):
        qs = AssessGatherInfo.objects.filter_active(assess_id__in=[0, self.assess_id])
        return qs


class AssessGatherInfoDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""收集信息的删除 修改"""

    model = AssessGatherInfo
    serializer_class = AssessGatherInfoSerializer

    def perform_update(self, serializer):
        super(AssessGatherInfoDetailView, self).perform_update(serializer)
        obj = self.get_object()
        if obj.info_type == AssessGatherInfo.INFO_TYPE_LIST:
            info_values = self.request.data.get("info_values", [])
            obj.config_info = json.dumps(info_values)
            obj.save()


class AssessProjectSurveyConfigView(WdListCreateAPIView):
    u"""自定义配置设置"""

    model = AssessProjectSurveyConfig
    serializer_class = AssessProjectSurveyConfigSerializer
    POST_CHECK_REQUEST_PARAMETER = ("assess_id", "survey_id", "model_types", "model_id", "contents")

    def post(self, request, *args, **kwargs):
        bulk_list = []
        en_contents = self.request.data.get('en_contents', None)
        for index, model_type in enumerate(self.model_types):
            AssessProjectSurveyConfig.objects.filter_active(
                assess_id=self.assess_id,
                survey_id=self.survey_id,
                model_type=model_type,
                model_id=self.model_id
            ).update(is_active=False)
            content = self.contents[index]
            if en_contents:
                try:
                    en_content = en_contents[index]
                except:
                    en_content = None
            if model_type == AssessProjectSurveyConfig.MODEL_TYPE_SLIDE_OPTION:
                content = json.dumps(content)
                if en_contents:
                    en_content = json.dumps(en_content)
            if en_contents:
                bulk_list.append(
                    AssessProjectSurveyConfig(
                        assess_id=self.assess_id,
                        survey_id=self.survey_id,
                        model_type=model_type,
                        model_id=self.model_id,
                        content=content,
                        en_content=en_content
                    )
                )
            else:
                bulk_list.append(
                    AssessProjectSurveyConfig(
                        assess_id=self.assess_id,
                        survey_id=self.survey_id,
                        model_type=model_type,
                        model_id=self.model_id,
                        content=content,
                    )
                )
        AssessProjectSurveyConfig.objects.bulk_create(bulk_list)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class AssessSurveyImportExportView(AuthenticationExceptView, WdExeclExportView):
    u"""项目参与人员的导入导出
    GET：项目参与人员模板的导出，数据的导出
    POST：项目参与人员的提交
    """
    IMPORT_TEMPLATE = 'new_import'
    EXPORT_DATA = "export_data"
    DEDICATED_LINK = "dedicated_link"

    POST_CHECK_REQUEST_PARAMETER = ("assess_id",)

    def get_file(self):
        export_type = self.request.GET.get("export_type", self.IMPORT_TEMPLATE)
        self.assess_id = self.request.GET.get('assess_id', None)
        if export_type == self.EXPORT_DATA:
            return self.export_org_data()
        elif export_type == self.IMPORT_TEMPLATE:
            return self.export_template(self.assess_id)
        elif export_type == self.DEDICATED_LINK and self.assess_id is not None:
            return self.export_dedicated_link()

    def export_template(self, assess_id):
        file_path, file_name = AssessImportExport.export_template(assess_id)
        self.default_export_file_name = file_name
        return file_path

    def export_dedicated_link(self):
        file_path, file_name = AssessImportExport.export_dedicated_link(self.assess_id)
        self.default_export_file_name = file_name
        return file_path

    def export_org_data(self):
        pass

    def post(self, request, *args, **kwargs):
        u"""组织人员导入"""
        self.parser_classes = (MultiPartParser,)
        file_data = request.data["file"]
        file_name = request.data["name"]
        file_path = AssessImportExport.import_data(file_data, file_name, self.assess_id)
        key = 'assess_id_%s' % self.assess_id
        FileStatusCache(key).set_verify_code(5)
        error_code, msg, index, new_user, old_user = import_assess_user_task_0916(self.assess_id, file_path)
        if error_code == ErrorCode.SUCCESS:
            assess_people_create_in_sql_task.delay(old_user, new_user, self.assess_id)
            # assess_people_create_in_sql_task(old_user, new_user, self.assess_id)
        else:
            FileStatusCache(key).set_verify_code(100)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            'err_code': error_code,
            'data_index': index,
            "data_msg": msg
        })

class AssessUserListView(WdListAPIView, WdDestroyAPIView):
    u"""
    @GET：项目人员列表
    @version: 20180805 @summary: 可以在线批量删除
    @DELETE: 在线批量删除
    """
    model = People
    serializer_class = PeopleSerializer
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )
    DELETE_CHECK_REQUEST_PARAMETER = ("assess_id", "people_ids")
    # FILTER_FIELDS = ("assess_id", )
    SEARCH_FIELDS = ("username", "phone", "email", "account_name", "name")

    p_serializer_class = PeopleSerializer
    POST_DATA_RESPONSE = True
    UPDATE_TAG = False
    partial = False

    def get_check_parameter(self, kwargs):
        if self.GET_CHECK_REQUEST_PARAMETER:
            for parameter in self.GET_CHECK_REQUEST_PARAMETER:
                setattr(self, parameter, kwargs.get(parameter, None))
                if getattr(self, parameter) is None:
                    return ErrorCode.INVALID_INPUT
        assess_type = AssessProject.objects.filter_active(id=self.assess_id)[0].assess_type
        user_id = self.request.GET.get('user_id', None)
        if assess_type == 300 and user_id:
            self.serializer_class = PeopleSerializer360
        return ErrorCode.SUCCESS

    def qs_search(self, qs):
        u"""REF: restframe work SearchFilter"""
        # 传入qs
        # 返回qs_serach后的qs

        key_words = self.request.GET.get(self.SEARCH_KEY, None)
        if key_words is None or not key_words:
            return qs

        search_sql = []
        for search_field in self.SEARCH_FIELDS:
            search_sql.append([search_field, Q(**{"%s__icontains" % search_field: key_words})])

        # search_sql += self.process_foreign_search()
        search_sql += self.process_tag_search(qs, key_words)
        if len(search_sql) == 0:
            return qs
        else:
            # SEARCH_FIELDS = ("username", "phone", "email", "account_name", "org_name")
            search_sql_people = []
            search_sql_authuser = []
            search_sql_org = []
            for search_sql_one in search_sql:
                if search_sql_one[0] in ["username", "phone", "email"]:
                    search_sql_people.append(search_sql_one[1])
                elif search_sql_one[0] in ["account_name"]:
                    search_sql_authuser.append(search_sql_one[1])
                else:
                    search_sql_org.append(search_sql_one[1])
            #  people中找key_words
            # def search_key_words(qs, search_sql_people, search_sql_authuser, search_sql_org):
            #     query_people = reduce(operator.or_, search_sql_people)
            #     qs_people_raw = qs
            #     qs_people = qs_people_raw.filter(query_people).values_list("id", flat=True)
            #     # authuser_acocunt_name 中到关键字
            #     query_authuser = reduce(operator.or_, search_sql_authuser)
            #     qs_user_ids = qs.values_list('user_id', flat=True)
            #     qs_authuser_raw = AuthUser.objects.filter(id__in=qs_user_ids)
            #     qs_authuser = qs_authuser_raw.filter(query_authuser).values_list("id", flat=True)
            #     qs_authuser = qs.filter(user_id__in=qs_authuser).values_list("id", flat=True)
            #     # 组织名中找关键字
            #     query_org = reduce(operator.or_, search_sql_org)
            #     qs_ids = qs.values_list('id', flat=True)
            #     qs_org_codes = PeopleOrganization.objects.filter_active(people_id__in=qs_ids).values_list("org_code", flat=True).distinct()
            #     qs_org_raw = Organization.objects.filter_active(identification_code__in=qs_org_codes)
            #     qs_org = qs_org_raw.filter(query_org).values_list("identification_code", flat=True)
            #     qs_org = PeopleOrganization.objects.filter_active(org_code__in=qs_org).values_list("people_id", flat=True).distinct()
            #     qs_org_list = list(qs_org)
            #     qs_org_people = []
            #     for x in qs_org_list:
            #         if x in list(qs_ids):
            #             qs_org_people.append(x)
            #
            #     all_qs_ids = list(qs_people) + list(qs_authuser) + qs_org_people
            #     qs = People.objects.filter_active(id__in=all_qs_ids).distinct()
            #     return qs
            qs = search_key_words(qs, search_sql_people, search_sql_authuser, search_sql_org)
        return qs

    def qs_filter(self, qs):
        # check_people_status_change.delay(self.assess_id)
        qs = super(AssessUserListView, self).qs_filter(qs)
        people_ids = AssessUser.objects.filter_active(
            assess_id=self.assess_id).values_list("people_id", flat=True)
        qs = qs.filter(id__in=people_ids).distinct()
        org_code = self.request.GET.get("org_code", None)
        if not org_code:
            return qs
        people_ids = PeopleOrganization.objects.filter_active(org_code=org_code).values_list(
            "people_id", flat=True
        )
        qs = qs.filter(id__in=people_ids)
        return qs

    def delete(self, request, *args, **kwargs):
        self.people_ids = [int(id) for id in self.people_ids.split(",")]
        AssessUser.objects.filter_active(assess_id=self.assess_id, people_id__in=self.people_ids).update(is_active=False)
        orgs = AssessOrganization.objects.filter_active(assess_id=self.assess_id).values_list("organization_code", flat=True)
        PeopleOrganization.objects.filter_active(
            people_id__in=self.people_ids, org_code__in=orgs).update(is_active=False)
        PeopleSurveyRelation.objects.filter_active(project_id=self.assess_id, people_id__in=self.people_ids).update(is_active=False)
        delete_assesssurveyuserdistribute(self.assess_id, self.people_ids)
        logger.info('user_id %s want delete assess_id %s with people_ids %s' % (self.request.user.id, self.assess_id, self.people_ids))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class AssessUserCreateView(WdCreateAPIView):
    # POST：新增一个项目用户
    POST_CHECK_REQUEST_PARAMETER = ('assess_id', 'username', 'org_names')

    def post(self, request, *args, **kwargs):
        infos = request.data.get('infos', None)
        mima = request.data.get('password', None)
        phone = request.data.get('phone', None)
        email = request.data.get('email', None)

        type1 = request.data.get('type1', None)
        type2 = request.data.get('type2', None)
        type3 = request.data.get('type3', None)
        type4 = request.data.get('type4', None)
        if type1 or type2 or type3 or type4:
            type_list = [type1, type2, type3, type4]
        else:
            type_list = []

        account_name = request.data.get('account_name', None)
        assess_id = self.assess_id
        nickname = self.username
        org_codes = self.org_names
        username = nickname + get_random_char(6)
        active_code = get_active_code()
        moreinfo = None
        assess_obj = AssessProject.objects.get(id=assess_id)
        ep_id = assess_obj.enterprise_id
        if type_list:
            for index, typenum in enumerate(type_list):
                if PeopleAccount.objects.filter_active(account_value=typenum, account_type=int(DINGZHI_4_TYPE_ACCOUNT[index]), enterprise_id=ep_id).exists():
                    return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                                 {'msg': u'账户%s在本企业已存在' % typenum})
        if account_name:
            if EnterpriseAccount.objects.filter(account_name=account_name, enterprise_id=assess_obj.enterprise_id).exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NAME_ERROR, {'msg': u'账户在本企业已存在'})
        if not org_codes:
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_EMPTY_ERROR, {'msg': u'项目组织为空'})
        #
        for org_code in org_codes:
            # [{"id":1}]
            org_obj = Organization.objects.filter_active(id=org_code["id"])
            if not org_obj.exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_INPUT_ERROR,
                                             {'msg': u'项目组织输入有误'})
            else:
                org_code["identification_code"] = org_obj[0].identification_code
        #
        org_check = check_org(org_codes)
        if org_check != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_INPUT_ERROR, {'msg': u'项目组织输入有误'})
        org_codes = get_org_codes(org_codes)
        if infos:
            key_infos = do_one_infos(infos)
            if key_infos is None:
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_INFO_ERROR, {'msg': u'增加信息异常'})
            # 增加的时候有dumps
            moreinfo = json.dumps(key_infos)
        if phone:
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_REGUL_ERROR, {'msg': u'新增用户失败，手机格式有误'})
            if People.objects.filter_active(phone=phone).count():
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR, {'msg': u'新增用户失败，手机已被使用'})
        if email:
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_REGUL_ERROR, {'msg': u'新增用户失败，邮箱格式有误'})
            if People.objects.filter_active(email=email).count():
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_USED_ERROR, {'msg': u'新增用户失败，邮箱已被使用'})

        try:
            authuser_obj = AuthUser.objects.create(
                username=username,
                account_name=account_name,
                nickname=nickname,
                password=get_mima(mima),
                phone=phone,
                email=email
            )
            new_people_obj = People.objects.create(
                username=nickname,
                user_id=authuser_obj.id,
                phone=phone,
                email=email,
                active_code=active_code,
                active_code_valid=True,
                more_info=moreinfo
            )
            if type_list:
                for index, typenum in enumerate(type_list):
                    PeopleAccount.objects.create(people_id=new_people_obj.id, account_value=typenum, account_type=int(DINGZHI_4_TYPE_ACCOUNT[index]), enterprise_id=ep_id)
            if account_name:
                EnterpriseAccount.objects.create(
                    user_id=authuser_obj.id,
                    people_id=new_people_obj.id,
                    enterprise_id=assess_obj.enterprise_id,
                    account_name=account_name
                )
            ret = do_org([(new_people_obj, {'org_codes': org_codes, 'ops': None})])
            if ret[0] != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_INPUT_ERROR, {'msg': u'组织有误'})
            AssessUser.objects.create(assess_id=assess_id, people_id=new_people_obj.id)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {'msg': u'成功'})
        except Exception, e:
            logger.error("新增单用户失败 %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {'msg': u'新增单用户失败'})


class AssessUseDetailView(WdRetrieveUpdateAPIView):
    model = People
    serializer_class = PeopleSerializer

    def put(self, request, *args, **kwargs):
        try:
            people_obj = self.get_object()
            authuser_obj = AuthUser.objects.get(id=people_obj.user_id)
        except Exception, e:
            logger.error('not this people %s' % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_FOUND)
        infos = request.data.get('infos', None)
        phone = str_check(request.data.get('phone', None))
        email = request.data.get('email', None)
        account_name = request.data.get('account_name', None)
        assess_id = request.data.get('assess_id', None)
        nickname = request.data.get('username', None)
        org_codes = request.data.get('org_names', None)
        mima = request.data.get('password', None)
        if mima:
            password = get_mima(mima)
        else:
            password = None
        moreinfo = None
        if account_name and (account_name != authuser_obj.account_name):
            assess_obj = AssessProject.objects.get(id=assess_id)
            if EnterpriseAccount.objects.filter_active(account_name=account_name, enterprise_id=assess_obj.enterprise_id).exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'data': u'账户在本企业已存在'})
        if not org_codes:
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_EMPTY_ERROR, {'msg': u'项目组织为空'})
        for org_code in org_codes:
            # [{"id":1}]
            org_obj = Organization.objects.filter_active(id=org_code["id"])
            if not org_obj.exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_INPUT_ERROR,
                                             {'msg': u'项目组织输入有误'})
            else:
                org_code["identification_code"] = org_obj[0].identification_code

        org_check = check_org(org_codes)
        if org_check != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_ORG_INPUT_ERROR, {'msg': u'项目组织输入有误'})
        org_codes = get_org_codes(org_codes)
        if infos:
            key_infos = do_one_infos(infos)
            if key_infos is None:
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_INFO_ERROR, {'msg': u'增加信息异常'})
            # 修改的时候没有dump
            moreinfo = key_infos
        if phone:
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'手机格式有误'})
            try:
                phone_obj = AuthUser.objects.get(phone=phone, is_active=True)
                if phone_obj != authuser_obj:
                    return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                                 {'msg': u'手机已被使用'})
            except:
                pass
        if email:
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'邮箱格式有误'})
            try:
                email_obj = AuthUser.objects.get(email=email, is_active=True)
                if email_obj != authuser_obj:
                    return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'邮箱已被使用'})
            except:
                pass
        try:
            if password:
                authuser_obj.password = password
            authuser_obj.account_name = account_name
            authuser_obj.nickname = nickname
            authuser_obj.phone = phone
            authuser_obj.email = email
            authuser_obj.save()
            people_obj.phone = phone
            people_obj.email = email
            if moreinfo:  # 有新信息  [{}, {} ,{}]
                if people_obj.more_info:  # 有旧信息  unicode "[{},{}]"
                    try:
                        old_info = json.loads(people_obj.more_info)  # 旧信息 unicode -> str -> []
                        old_key_name = [x['key_name'] for x in old_info]
                        for new_key in moreinfo:
                            if new_key['key_name'] in old_key_name:
                                old_info[old_key_name.index(new_key["key_name"])]['key_value'] = new_key["key_value"]
                            else:
                                old_info.append(new_key)
                        people_obj.more_info = json.dumps(old_info)
                    except:
                        # 失败，则不要旧信息了
                        people_obj.more_info = json.dumps(moreinfo)
                else:
                    people_obj.more_info = json.dumps(moreinfo)
            people_obj.username = nickname
            people_obj.save()
            if account_name:
                try:
                    ea_obj = EnterpriseAccount.objects.get(user_id=authuser_obj.id)
                    ea_obj.account_name = account_name
                except:
                    ass_obj = AssessProject.objects.filter(id=assess_id)[0]
                    EnterpriseAccount.objects.create(
                        user_id=authuser_obj.id,
                        people_id=people_obj.id,
                        enterprise_id=ass_obj.enterprise_id,
                        account_name=account_name
                    )
            # 修改组织
            ass_org_codes = Organization.objects.filter_active(assess_id=assess_id).values_list("identification_code", flat=True)
            PeopleOrganization.objects.filter_active(people_id=people_obj.id, org_code__in=ass_org_codes).update(is_active=False)
            for codes in org_codes:
                PeopleOrganization.objects.create(people_id=people_obj.id, org_code=codes)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        except Exception, e:
            logger.error("update %d error %s" % (people_obj.id, e))
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_UPDATE_ERROR, {'msg': u'修改异常'})


class Assess360UserListView(WdListCreateAPIView):
    u"""360项目人员设置和管理
    @GET：360分角色人员列表
    @POST：360分角色人员设置
    360角色人员列表
    /api/v1/assessment/project360/user/
    GET请求
    assess_id：项目ID
    role_type： 角色类型 20 自评，30:上级，40:下级 50:同级 60:供应商
    role_people_id: 角色人员ID

    360角色人员设置
    POST请求
    assess_id ： 项目ID
    role_type：角色类型
    role_people_id： 角色人员ID，自评人员 == 0，其他角色时 role_people_id == 自评人员ID
    user_ids：归于该角色的人员ID数组    这个user_id 是 people的id
    # 90°人员导入，就是 定位一个人people_id（手机，邮箱，账户？）, 定位导入的上下级，
    定位导入的项目id, 定位导入的全部角色的id（手机，邮箱，账户？）,, 操作
    """
    model = AssessUser
    serializer_class = AssessUserSerializer
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", "role_type", "user_id")
    POST_CHECK_REQUEST_PARAMETER = ("assess_id", "role_type", "user_id", "role_user_ids")  #  项目， 上下级 ， user  ,  上下级哪些人
    FILTER_FIELDS = ("assess_id", "role_type")

    def qs_filter(self, qs):
        qs = super(Assess360UserListView, self).qs_filter(qs)
        if int(self.role_type) == AssessUser.ROLE_TYPE_SELF:
            return qs
        else:
            return qs.filter(people_id=self.user_id)

    def post(self, request, *args, **kwargs):
        # if self.role_type == 40:  #  下级
        #     if AssessUser.objects.filter_active(
        #         assess_id=self.assess_id,
        #         people_id=self.user_id,
        #         role_type=30   # 检查上级
        #     ).exists():
        #         return general_json_response(status.HTTP_200_OK, ErrorCode.ASSESSUSER_360_ROLE_TYPE_UP_DOWN_ERROR,
        #                                      {"msg": "42212该用户已有上级，不能设置下级"})
        #
        # 检查这个人有没有上级，如果有
        #
        self.role_user_ids = [int(user_id) for user_id in self.role_user_ids]
        assess_user_bulk_list = []
        for role_user_id in self.role_user_ids:
            if self.user_id == role_user_id:
                AssessUser.objects.get_or_create(
                    assess_id=self.assess_id,
                    people_id=self.user_id,
                    role_type=AssessUser.ROLE_TYPE_SELF,
                    role_people_id=role_user_id,
                    is_active=True
                )
                continue

            if self.role_type == AssessUser.ROLE_TYPE_SELF:
                user_id = role_user_id
            else:
                user_id = self.user_id
            if not AssessUser.objects.filter_active(
                assess_id=self.assess_id,
                people_id=user_id,
                role_type=self.role_type,
                role_people_id=role_user_id
            ).exists():
                assess_user_bulk_list.append(AssessUser(
                    assess_id=self.assess_id,
                    people_id=user_id,
                    role_type=self.role_type,
                    role_people_id=role_user_id
                ))
        if self.role_type == AssessUser.ROLE_TYPE_SELF:
            AssessUser.objects.filter_active(
                assess_id=self.assess_id,
                role_type=self.role_type,
            ).exclude(role_people_id__in=self.role_user_ids).update(is_active=False)
        else:
            AssessUser.objects.filter_active(
                assess_id=self.assess_id,
                role_type=self.role_type,
                people_id=self.user_id
            ).exclude(role_people_id__in=self.role_user_ids).update(is_active=False)
        AssessUser.objects.bulk_create(assess_user_bulk_list)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class Assess360UpuserImportView(WdListCreateAPIView):
    u"""
    #注意，先要给这个人设置一个自评，，，可能。
    @POST：360分角色人员设置
    assess_id：项目ID
    role_type： 角色类型 20 自评，30:上级，40:下级 50:同级 60:供应商
    role_people_id： 角色人员ID，自评人员 == 0，其他角色时 role_people_id == 自评人员ID
    user_ids：归于该角色的人员ID数组    这个user_id 是 people的id    被评人
    # 90°人员导入，就是 定位一个人people_id（手机，邮箱，账户？）, 定位导入的上下级，
    定位导入的项目id, 定位导入的全部角色的id（手机，邮箱，账户？）,, 操作
    """
    model = AssessUser
    serializer_class = AssessUserSerializer
    POST_CHECK_REQUEST_PARAMETER = ("assess_id", "role_type", "user_id")  #  项目， 上下级 ， user  ,  上下级哪些人

    def check_import_role_data(self, assess_id, file_path):
        project = AssessProject.objects.get(id=assess_id)
        data = ExcelUtils().read_rows(file_path)
        people_ids = []
        for index, infos in enumerate(data):
            if index == 0:
                continue
            account = str_check(infos[1])
            phone = str_check(infos[2])
            email = str_check(infos[3])
            if not (email or phone or account):
                return ErrorCode.FAILURE, u"手机/邮箱/账号都没有", index, people_ids
            else:
                one_user = []
                if account:
                    ea_qs = EnterpriseAccount.objects.filter_active(account_name=account,
                                                                    enterprise_id=project.enterprise_id)
                    if ea_qs.count() == 0:
                        return ErrorCode.FAILURE, u"没有该账户", index, people_ids
                    elif ea_qs.count() == 1:
                        a_user_id = ea_qs[0].user_id
                        if a_user_id not in one_user:
                            one_user.append(a_user_id)
                    else:
                        return ErrorCode.FAILURE, u"账户重复", index, people_ids
                if email:
                    e_qs = AuthUser.objects.filter(email=email)
                    if e_qs.count() == 0:
                        return ErrorCode.FAILURE, u"没有该邮箱", index, people_ids
                    elif e_qs.count() == 1:
                        e_user_id = e_qs[0].id
                        if e_user_id not in one_user:
                            one_user.append(e_user_id)
                    else:
                        return ErrorCode.FAILURE, u"邮箱重复", index, people_ids
                if phone:
                    p_qs = AuthUser.objects.filter(phone=phone)
                    if p_qs.count() == 0:
                        return ErrorCode.FAILURE, u"没有该手机", index, people_ids
                    elif p_qs.count() == 1:
                        p_user_id = p_qs[0].id
                        if p_user_id not in one_user:
                            one_user.append(p_user_id)
                    else:
                        return ErrorCode.FAILURE, u"手机重复", index, people_ids
                if len(one_user) == 1:
                    pp_qs = People.objects.filter(user_id=one_user[0])
                    if pp_qs.count() == 1:
                        people_ids.append(pp_qs[0].id)
                    else:
                        return ErrorCode.FAILURE, u"该用户一个user对应2个people", index, people_ids
                else:
                    return ErrorCode.FAILURE, u"手机/邮箱/账户对应不同用户", index, people_ids
        # 第一行的index是0
        return ErrorCode.SUCCESS, u'成功', index, people_ids

    def all_role_user_ids_for_user(self, ids, assess_id, role_type, input_user_ids):
        # ids 评价人; input_user_id 被评人;
        role_user_ids = [int(x) for x in ids]
        assess_user_bulk_list = []
        for input_user_id in input_user_ids:
            for role_user_id in role_user_ids:
                if role_type == AssessUser.ROLE_TYPE_SELF:
                    user_id = role_user_id
                else:
                    user_id = input_user_id
                if not AssessUser.objects.filter_active(
                        assess_id=assess_id,
                        people_id=user_id,
                        role_type=role_type,
                        role_people_id=role_user_id
                ).exists():
                    assess_user_bulk_list.append(AssessUser(
                        assess_id=assess_id,
                        people_id=user_id,
                        role_type=role_type,
                        role_people_id=role_user_id
                    ))
            if role_type == AssessUser.ROLE_TYPE_SELF:
                AssessUser.objects.filter_active(
                    assess_id=assess_id,
                    role_type=role_type,
                ).exclude(role_people_id__in=role_user_ids).update(is_active=False)
            else:
                # 这里会将非导入批次的人全部删除， 与手动增加保持一致的效果
                AssessUser.objects.filter_active(
                    assess_id=assess_id,
                    role_type=role_type,
                    people_id=input_user_id
                ).exclude(role_people_id__in=role_user_ids).update(is_active=False)
        AssessUser.objects.bulk_create(assess_user_bulk_list)
        return None

    # 360项目 90°人员导入  备用
    def post(self, request, *args, **kwargs):
        self.parser_classes = (MultiPartParser,)
        file_data = request.data["file"]     # 文件
        file_name = request.data["name"]      # 文件名
        assess_id = request.data["assess_id"]   # 项目id
        role_type = request.data["role_type"]   # 上下级关系
        input_user_ids = request.data["user_id"]  # people id 被评人 list 形式的传入值
        if type(input_user_ids) != list:
            input_user_ids = [input_user_ids]
        # 现在的文件是 姓名，账户 ， 手机 ， 邮箱
        file_path = AssessImportExport.import_data(file_data, file_name, self.assess_id)
        error_code, msg, index, ids = self.check_import_role_data(self.assess_id, file_path)
        if error_code == ErrorCode.SUCCESS:
            self.all_role_user_ids_for_user(ids, assess_id, role_type, input_user_ids)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            'err_code': error_code,
            'data_index': index,
            "data_msg": msg
        })


class Assess360UserCopyView(WdCreateAPIView):
    u"""360项目人员角色人员拷贝
    @POST：360项目人员角色人员拷贝
    """
    model = AssessUser
    serializer_class = None
    POST_CHECK_REQUEST_PARAMETER = (
        "assess_id", "copy_from_role_type", "copy_from_user_id", "copy_to_user_id", "copy_to_role_type")

    def post(self, request, *args, **kwargs):
        role_uids = AssessUser.objects.filter_active(
            people_id=self.copy_from_user_id, assess_id=self.assess_id, role_type=self.copy_from_role_type).values_list("role_people_id", flat=True)
        bulk_list = []
        for role_uid in role_uids:
            if AssessUser.objects.filter_active(
                people_id=self.copy_to_user_id, assess_id=self.assess_id, role_type=self.copy_to_role_type,
                role_people_id=role_uid
            ).exists():
                continue
            bulk_list.append(
                AssessUser(
                    people_id=self.copy_to_user_id, assess_id=self.assess_id, role_type=self.copy_to_role_type,
                    role_people_id=role_uid
                )
            )
        AssessUser.objects.bulk_create(bulk_list)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class Assess360TestUserStatisticsView(WdListAPIView):
    u"""360项目 被评价人员列表和统计"""
    model = AssessUser
    serializer_class = Assess360TestUserStatisticsSerialzier
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )
    FILTER_FIELDS = ("assess_id", )

    def qs_filter(self, qs):
        qs = super(Assess360TestUserStatisticsView, self).qs_filter(qs)
        return qs.filter(role_type=AssessUser.ROLE_TYPE_SELF)


class Assess360SurveyRelation(WdListCreateAPIView):
    u"""360项目问卷关联"""

    model = AssessSurveyRelation
    g_serializer_class = AssessmentSurveyRelationGetSerializer
    p_serializer_class = AssessmentSurveyRelationPostSerializer
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )
    POST_CHECK_REQUEST_PARAMETER = ("assess_id", "relations")
    FILTER_FIELDS = ("assess_id", )

    def post(self, request, *args, **kwargs):
        is_batch = request.data.get("is_batch", None)
        AssessSurveyRelation.objects.filter_active(
            assess_id=self.assess_id).update(is_active=False)
        if is_batch is None:
            bulk_list = []
            for relation in self.relations:
                role_type = relation["role_type"]
                survey_id = relation["survey_id"]
                bulk_list.append(AssessSurveyRelation(
                    assess_id=self.assess_id,
                    survey_id=survey_id,
                    role_type=role_type
                ))
            AssessSurveyRelation.objects.bulk_create(bulk_list)
        else:
            bulk_list = []
            relation = self.relations[0]
            survey_id = relation["survey_id"]
            for role in AssessUser.ROLE_CHOICES:
                role_type = role[0]
                if role_type == AssessUser.ROLE_TYPE_NORMAL:
                    continue
                bulk_list.append(AssessSurveyRelation(
                    assess_id=self.assess_id,
                    survey_id=survey_id,
                    role_type=role_type
                ))
            AssessSurveyRelation.objects.bulk_create(bulk_list)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class DownloadReportView(WdExeclExportView):
    u"""报告下载"""

    default_export_file_name = "report.zip"

    def down_data_to_file(self, url, file_name, file_path):
        import urllib2
        logger.debug("download report url is %s" % url)
        req = urllib2.Request(url.encode("utf-8"))
        rst = urllib2.urlopen(req)
        fdata = rst.read()
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        data2file(fdata, file_name, file_path)

    def get_file(self):
        people_ids = self.request.GET.get("ids", "")
        project_id = self.request.GET.get("assess_id", None)
        is_debug = self.request.GET.get("is_debug", None)
        if is_debug == "abcdefg":
            is_debug = True
        else:
            is_debug = False
        if not is_debug and (project_id is None or not people_ids):
            return None
        people_ids = people_ids.split(",")
        if self.people_id_all_list:
            people_ids = [str(id) for id in self.people_id_all_list]
        if is_debug:
            people_ids = list(PeopleSurveyRelation.objects.filter_active(
                report_status=PeopleSurveyRelation.REPORT_SUCCESS,
                report_url__isnull=False
            ).values_list("people_id", flat=True).order_by("-id")[:3])
        logger.debug("%s download report people ids is %s" % (str(self.request.user.id), ",".join(people_ids)))
        # 开始做文件
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        timestamp = int(time.time()*100)
        parent_path = "%s-report-download-%s" % (self.request.user.id, str(timestamp))
        zip_path = os.path.join("download", "report", now, parent_path)
        file_path = os.path.join(zip_path, 'report')
        for people_id in people_ids:
            people = People.objects.get(id=people_id)
            if not is_debug:
                relations = PeopleSurveyRelation.objects.filter_active(
                    project_id=project_id,
                    people_id=people_id,
                    report_status=PeopleSurveyRelation.REPORT_SUCCESS,
                    report_url__isnull=False
                )
            else:
                relations = PeopleSurveyRelation.objects.filter_active(
                    people_id=people_id,
                    report_status=PeopleSurveyRelation.REPORT_SUCCESS,
                    report_url__isnull=False
                )
            # report 下的某个人的报告文件夹
            account_name = AuthUser.objects.filter(id=people.user_id).values_list("account_name", flat=True)
            account_b = None
            if account_name.exists():
                account_b = account_name[0]
            phone = people.phone
            email = people.email
            if account_b:
                fold_name_b = account_b
            elif phone:
                fold_name_b = phone
            elif email:
                fold_name_b = email
            else:
                fold_name_b = people.id
            people_file_path = os.path.join(file_path, "%s_%s" % (people.username, fold_name_b))
            for relation in relations:
                if relation.report_url:
                    self.down_data_to_file(relation.report_url, u"%s.pdf" % relation.survey_name, people_file_path)
        # 大文件夹
        zip_file_path = "%s.zip" % zip_path
        if not os.path.exists(file_path):
            return None
        zip_folder(zip_path, zip_file_path)
        self.default_export_file_name = "%s.zip" % parent_path
        return zip_file_path

    def get(self, request, *args, **kwargs):
        all_peoples = self.request.GET.get("all", None)
        self.people_id_all_list = []
        # 下载全部报告
        if all_peoples is not None:
            project_id = self.request.GET.get("assess_id", None)
            self.people_id_all_list = list(AssessUser.objects.filter_active(assess_id=project_id).values_list("people_id", flat=True))
            if len(self.people_id_all_list) == 0:
                return general_json_response(status.HTTP_200_OK, ErrorCode.PROJECT_PEOPLE_ERROR, {'msg': u'项目下没有参与人员'})
            authuser_obj = AuthUser.objects.get(id=self.request.user.id)
            if not authuser_obj.email:
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_HAS_ERROR, {'msg': u'您没有邮箱,请检查,修改邮箱'})
            file_task.delay(authuser_obj.id, authuser_obj.email, self.people_id_all_list, project_id)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {'msg': u'正在下载批量报告中,请注意检查邮箱%s' % authuser_obj.email})
        else:
        # 下载指定报告
            file_full_path = self.get_file()
            if file_full_path is None:
                return HttpResponse(u"目前尚未生成报告，请稍后再试")
            r = FileResponse(open(file_full_path, "rb"))
            r['Content-Disposition'] = 'attachment; filename=%s' % self.default_export_file_name
            return r


class AssessmentFileStatusView(AuthenticationExceptView, WdListAPIView):
    """获取上传进度状态"""

    def get(self, request, *args, **kwargs):
        assess_id = request.GET.get("assess_id", 'None')
        if not assess_id:
            file_status = 100
        else:
            key = 'assess_id_%s' % assess_id
            file_status = FileStatusCache(key).get_verify_code()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"status": file_status})