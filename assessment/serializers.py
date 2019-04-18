# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import base64
import json
from urllib import quote

from rest_framework import serializers

from WeiDuAdmin import settings
from assessment.models import AssessProject, AssessOrganization, AssessSurveyRelation, AssessGatherInfo, \
    AssessProjectSurveyConfig, AssessUser, AssessSurveyUser, AssessSurveyUserDistribute
from front.models import PeopleSurveyRelation
from survey.models import Survey
from utils.serializers import WdTagListSerializer
from wduser.models import Organization, People, PeopleOrganization, EnterpriseInfo


class AssessmentBasicSerializer(WdTagListSerializer, serializers.ModelSerializer):
    u"""测评项目列表 创建序列化"""

    org_infos = serializers.SerializerMethodField()

    class Meta:
        model = AssessProject
        fields = ('id', 'name', 'en_name', 'enterprise_id', 'begin_time', 'end_time', 'advert_url', 'assess_type',
                  'project_status', 'finish_choices', 'finish_redirect', 'finish_txt', 'assess_logo', 'org_infos',
                  "user_count", "distribute_type", "has_distributed", 'is_answer_survey_by_order', 'has_survey_random',
                  'survey_random_number', 'show_people_info')

    def get_org_infos(self, obj):
        org_ids = AssessOrganization.objects.filter_active(assess_id=obj.id).values_list("organization_id", flat=True)
        return Organization.objects.filter_active(id__in=org_ids).values("id", "name", "identification_code")


class AssessmentSurveyRelationPostSerializer(serializers.ModelSerializer):
    u"""项目问卷关联创建序列"""

    class Meta:
        model = AssessSurveyRelation
        fields = ("id", "assess_id", "survey_id", "role_type",
                  "custom_config", "people_view_report", "survey_been_random")


class AssessmentSurveyRelationGetSerializer(serializers.ModelSerializer):
    u"""项目问卷关联序列"""

    survey_info = serializers.SerializerMethodField()

    class Meta:
        model = AssessSurveyRelation
        fields = ("id", "survey_info", "assess_id", "survey_id", "role_type", "begin_time", "end_time", "survey_status",
                  "assess_logo", "user_count", "people_view_report", "survey_been_random")

    def get_survey_info(self, obj):
        if obj.custom_config:
            config = json.loads(obj.custom_config)
        else:
            config = {}
        title = config.get('survey_name', None)
        en_title = config.get('en_survey_name', None)
        obj = Survey.objects.get(id=obj.survey_id)
        if not title:
            title = obj.title
            en_title = obj.en_title
        return {
            "survey_name": title,
            "en_survey_name": en_title,
            "survey_id": obj.id,
            "model_id": obj.model_id,
            "form_type": obj.form_type,
            "see_detail_permission": obj.see_detail_permission
        }


class AssessSurveyReportListSerializer(AssessmentSurveyRelationGetSerializer):
    enterprise_project_info = serializers.SerializerMethodField()

    class Meta:
        model = AssessSurveyRelation
        fields = AssessmentSurveyRelationGetSerializer.Meta.fields + ('enterprise_project_info', )

    def get_enterprise_project_info(self, obj):
        try:
            project = AssessProject.objects.get(id=obj.assess_id)
            enterprise = EnterpriseInfo.objects.get(id=project.enterprise_id)
            return {
                "enterprise_name": enterprise.cn_name, "enterprise_id": enterprise.id,
                "project_name": project.name, "project_id": project.id
            }
        except:
            return {}


class AssessmentSurveyRelationDetailGetSerializer(AssessmentSurveyRelationGetSerializer):
    u"""项目问卷详情接口"""

    class Meta:
        model = AssessSurveyRelation
        fields = AssessmentSurveyRelationGetSerializer.Meta.fields


class AssessGatherInfoSerializer(serializers.ModelSerializer):
    u"""收集信息 序列号"""

    info_values = serializers.SerializerMethodField()

    class Meta:
        model = AssessGatherInfo
        fields = ('id', 'info_name', 'info_type', 'info_values', 'assess_id', 'is_required', 'is_modified')

    def get_info_values(self, obj):
        if not obj.config_info:
            return None
        custom_config = json.loads(obj.config_info)
        return custom_config


class AssessProjectSurveyConfigSerializer(serializers.ModelSerializer):
    u"""自定义配置"""

    class Meta:
        model = AssessProjectSurveyConfig
        fields = ("assess_id", "survey_id", "model_type", "model_id", "content")


class AssessUserSerializer(serializers.ModelSerializer):
    u"""项目人员列表序列化"""

    org_names = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()

    class Meta:
        model = AssessUser
        fields = ("assess_id", "username", "user_id", "phone", "email", "org_names", "role_type", "role_people_id")

    def __get_people_info(self, obj):
        if hasattr(obj, '__cache__') and 'people_info' in obj.__cache__:
            return obj.__cache__["people_info"]
        if not hasattr(obj, '__cache__'):
            obj.__cache__ = {}
        if obj.role_type == AssessUser.ROLE_TYPE_NORMAL:
            people = People.objects.get(id=obj.people_id)
        else:
            people = People.objects.get(id=obj.role_people_id)
        obj.__cache__["people_info"] = {
            "username": people.username,
            "phone": people.phone,
            "email": people.email,
            "org_codes": people.org_codes,
            "id": people.id
        }
        return obj.__cache__["people_info"]

    def get_org_names(self, obj):
        info = self.__get_people_info(obj)
        org_codes = info["org_codes"]
        return list(Organization.objects.filter_active(
            identification_code__in=org_codes).values_list("name", flat=True))

    def get_username(self, obj):
        info = self.__get_people_info(obj)
        return info["username"]

    def get_phone(self, obj):
        info = self.__get_people_info(obj)
        return info["phone"]

    def get_email(self, obj):
        info = self.__get_people_info(obj)
        return info["email"]

    def get_user_id(self, obj):
        info = self.__get_people_info(obj)
        return info["id"]


class Assess360TestUserStatisticsSerialzier(serializers.ModelSerializer):
    u"""360被评价人员统计"""

    username = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = AssessUser
        fields = ("assess_id", "username", "user_id", "statistics", "role_type")

    def __get_people_info(self, obj):
        if hasattr(obj, '__cache__') and 'people_info' in obj.__cache__:
            return obj.__cache__["people_info"]
        if not hasattr(obj, '__cache__'):
            obj.__cache__ = {}
        if obj.role_type == AssessUser.ROLE_TYPE_NORMAL:
            people = People.objects.get(id=obj.people_id)
        else:
            people = People.objects.get(id=obj.role_people_id)
        obj.__cache__["people_info"] = {
            "username": people.username,
            "phone": people.phone,
            "email": people.email,
            "org_codes": people.org_codes,
            "id": people.id
        }
        return obj.__cache__["people_info"]

    def get_username(self, obj):
        info = self.__get_people_info(obj)
        return info["username"]

    def get_user_id(self, obj):
        info = self.__get_people_info(obj)
        return info["id"]

    def __get_count(self, role_type, obj):
        level_qs = AssessUser.objects.filter_active(
            assess_id=obj.assess_id, people_id=obj.people_id, role_type=role_type).values_list(
            "role_people_id", flat=True).distinct()
        level_count = level_qs.count()
        level_survey_qs = AssessSurveyRelation.objects.filter_active(
            assess_id=obj.assess_id,
            role_type=role_type
        )
        if not level_survey_qs.exists():
            level_finished_count = 0
        else:
            survey_id = level_survey_qs[0].survey_id
            level_finished_count = PeopleSurveyRelation.objects.filter_active(
                project_id=obj.assess_id, survey_id=survey_id, status__in=[
                    PeopleSurveyRelation.STATUS_EXPIRED, PeopleSurveyRelation.STATUS_FINISH],
                evaluated_people_id=obj.people_id, role_type=role_type
            ).count()
        return level_count, level_finished_count

    def get_statistics(self, obj):
        high_level_count, high_level_finished_count = self.__get_count(AssessUser.ROLE_TYPE_HIGHER_LEVEL, obj)
        low_level_count, low_level_finished_count = self.__get_count(AssessUser.ROLE_TYPE_LOWER_LEVEL, obj)
        same_level_count, same_level_finished_count = self.__get_count(AssessUser.ROLE_TYPE_SAME_LEVEL, obj)
        supplier_level_count, supplier_level_finished_count = self.__get_count(AssessUser.ROLE_TYPE_SUPPLIER_LEVEL, obj)
        self_level_count, self_level_finished_count = self.__get_count(AssessUser.ROLE_TYPE_SELF, obj)

        return {
            "high_level": {"count": high_level_count, "finished": high_level_finished_count},
            "low_level": {"count": low_level_count, "finished": low_level_finished_count},
            "same_level": {"count": same_level_count, "finished": same_level_finished_count},
            "supplier_level": {"count": supplier_level_count, "finished": supplier_level_finished_count},
            "self_level": {"count": self_level_count, "finished": self_level_finished_count}
        }
