# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import copy
import json

import datetime
from rest_framework import serializers

from assessment.models import AssessSurveyRelation, AssessProject, AssessProjectSurveyConfig
from front.models import PeopleSurveyRelation, SurveyInfo, SurveyQuestionInfo, UserQuestionInfo, UserSurveyBlockStatus, \
    UserQuestionAnswerInfo
from front.tasks import survey_sync, algorithm_task
from research.models import ResearchModel, ResearchDimension
from survey.models import Survey
from utils.logger import get_logger

logger = get_logger("front")


class SurveyInfoSerializer(serializers.ModelSerializer):
    u"""测验问卷信息序列化"""

    config = serializers.SerializerMethodField()
    block_info = serializers.SerializerMethodField()
    show_people_info = serializers.SerializerMethodField()
    time_limit_original = serializers.SerializerMethodField()

    class Meta:
        model = SurveyInfo
        fields = ("survey_id", "project_id", "survey_name", 'en_survey_name', "survey_desc", 'en_survey_desc',
                  "project_name", "en_project_name", "survey_type", "begin_time", "end_time", "project_type", "config",
                  "status", "block_info", "form_type", "time_limit", "show_people_info", "time_limit_original")

    def get_config(self, obj):
        if not obj.config_info:
            return obj.DEFAULT_CONFIG
        config = json.loads(obj.config_info)
        rst_config = copy.deepcopy(SurveyInfo.DEFAULT_CONFIG)
        for config_key in config:
            if config_key in rst_config:
                rst_config[config_key] = config[config_key]
        return rst_config

    def get_block_info(self, obj):
        if not obj.block_info:
            return {}
        return json.loads(obj.block_info)

    def get_show_people_info(self, obj):
        try:
            return AssessProject.objects.get(id=obj.project_id).show_people_info
        except:
            return True

    def get_time_limit_original(self, obj):
        try:
            return obj.time_limit
        except:
            return 0


class PeopleSurveySerializer(serializers.ModelSerializer):
    u"""用户测验列表序列化"""

    survey_info = serializers.SerializerMethodField()

    class Meta:
        model = PeopleSurveyRelation
        fields = ("id", 'people_id', 'survey_info', 'report_status', 'report_url', 'role_type', 'evaluated_people_id',
                  'finish_time', 'en_report_url', 'project_id')

    def __get_survey_from_admin(self, obj):
        # TODO：360
        survey_info_obj = survey_sync(obj.survey_id, obj.project_id)
        if not survey_info_obj:
            return None, {}
        return survey_info_obj, SurveyInfoSerializer(instance=survey_info_obj).data

    def __get_read_status(self, obj, survey_info_obj):
        if survey_info_obj.form_type == Survey.FORM_TYPE_FORCE or survey_info_obj.test_type == SurveyInfo.TEST_TYPE_BY_QUESTION:
            qs = UserSurveyBlockStatus.objects.filter_active(
                people_id=obj.people_id, survey_id=obj.survey_id, project_id=obj.project_id,
                role_type=obj.role_type, evaluated_people_id=obj.evaluated_people_id
            )
            if not qs.exists():
                read_status = UserSurveyBlockStatus.STATUS_UNREAD
                answer_count_time = 0
            else:
                read_status = qs[0].status
                answer_count_time = qs[0].answer_count_time
            return {"survey_read_status": read_status, "answer_count_time": answer_count_time}
        else:
            block_read_status = {}
            survey_read_status = UserSurveyBlockStatus.STATUS_UNREAD
            for block in json.loads(survey_info_obj.block_info):
                block_read_status[block["id"]] = {
                    "read_status": UserSurveyBlockStatus.STATUS_UNREAD,
                    "answer_count_time": 0
                }
                # status_info = {"id": block["id"], "status": UserSurveyBlockStatus.STATUS_UNREAD}
                qs = UserSurveyBlockStatus.objects.filter_active(
                    people_id=obj.people_id, survey_id=obj.survey_id, project_id=obj.project_id,
                    block_id=block["id"], role_type=obj.role_type, evaluated_people_id=obj.evaluated_people_id
                )
                if qs.exists():
                    user_block_info = qs[0]
                    survey_read_status = UserSurveyBlockStatus.STATUS_READ
                    block_read_status[block["id"]] = {
                        "read_status": UserSurveyBlockStatus.STATUS_READ,
                        "answer_count_time": user_block_info.answer_count_time,
                        "is_finish": user_block_info.is_finish
                    }
            if survey_read_status == UserSurveyBlockStatus.STATUS_UNREAD:
                qs = UserSurveyBlockStatus.objects.filter_active(
                    people_id=obj.people_id, survey_id=obj.survey_id, project_id=obj.project_id,
                    block_id=UserSurveyBlockStatus.BLOCK_PART_ALL, role_type=obj.role_type, evaluated_people_id=obj.evaluated_people_id
                )
                if qs.exists():
                    survey_read_status = UserSurveyBlockStatus.STATUS_READ
            return {"survey_read_status": survey_read_status, "block_read_status": block_read_status}

    def get_survey_info(self, obj):
        # TODO 从缓存中获取问卷信息
        survey_info_qs = SurveyInfo.objects.filter_active(survey_id=obj.survey_id, project_id=obj.project_id)
        obj_modify = False
        if not survey_info_qs.exists():
            survey_info_obj, survey_info = self.__get_survey_from_admin(obj)
            if not survey_info_obj:
                return {}
        else:
            survey_info_obj = survey_info_qs[0]
            survey_info = SurveyInfoSerializer(instance=survey_info_obj).data
        # 问卷时间未到
        if survey_info["status"] == SurveyInfo.STATUS_WAITING:
            # 未开始  0
            pass
        # 问卷开始测评
        elif survey_info["status"] == SurveyInfo.STATUS_WORKING:  # 已开放 10
            # 进行中  拆成 已开发和答卷中
            survey_info["status"] = obj.status
            if obj.status == PeopleSurveyRelation.STATUS_NOT_BEGIN:
                obj.status = PeopleSurveyRelation.STATUS_DOING  # 10
                survey_info["status"] = obj.status  # 9.17 加 s_s是10，但o_s 是0，前面赋值为0，就有问题
                obj_modify = True
            if obj.begin_answer_time and not obj.finish_time:
                obj.status = PeopleSurveyRelation.STATUS_DOING_PART
                survey_info["status"] = obj.status    # 答卷中  15
                obj_modify = True
        # 问卷结束测评
        elif survey_info["status"] == SurveyInfo.STATUS_END:
            # 用户做完问卷
            if obj.status == PeopleSurveyRelation.STATUS_FINISH:
                survey_info["status"] = obj.status
            # 用户未做完问卷
            else:
                # 已过期
                survey_info["status"] = PeopleSurveyRelation.STATUS_EXPIRED
                if obj.status != PeopleSurveyRelation.STATUS_EXPIRED:
                    obj.status = PeopleSurveyRelation.STATUS_EXPIRED
                    obj_modify = True
        read_status = self.__get_read_status(obj, survey_info_obj)
        survey_info["read_status"] = read_status
        survey_info["overtime"] = False
        t_l_o = survey_info.get("time_limit_original", None)
        if not t_l_o:
            survey_info["time_limit_original"] = int(survey_info["time_limit"])
        if int(survey_info["time_limit"]):
            if obj.is_overtime:
                survey_info["overtime"] = True
                survey_info["time_limit"] = -1
                survey_info["status"] = PeopleSurveyRelation.STATUS_FINISH
                if obj.status != PeopleSurveyRelation.STATUS_FINISH:
                    obj.status = PeopleSurveyRelation.STATUS_FINISH
                    if not obj.finish_time:
                        obj.finish_time = datetime.datetime.now()
                    obj_modify = True
                    algorithm_task.delay(obj.id)
            else:
                if obj.begin_answer_time:
                    now = datetime.datetime.now()
                    if obj.begin_answer_time + datetime.timedelta(minutes=int(survey_info["time_limit"])) < now:
                        survey_info["overtime"] = True
                        survey_info["time_limit"] = -1 # 0 为不限时问卷
                        survey_info["status"] = PeopleSurveyRelation.STATUS_FINISH
                        obj.is_overtime = True
                        if obj.status != PeopleSurveyRelation.STATUS_FINISH:
                            obj.status = PeopleSurveyRelation.STATUS_FINISH
                            if not obj.finish_time:
                                obj.finish_time = datetime.datetime.now()
                            algorithm_task.delay(obj.id)
                        obj_modify = True
                    else:
                        survey_info["time_limit"] = survey_info_obj.time_limit - ((now - obj.begin_answer_time).seconds) / 60
                        if survey_info["time_limit"] < 1:
                            survey_info["time_limit"] = 1
        if obj_modify:
            # TODO: 异步实现
            obj.save()
        return survey_info


class SurveyQuestionInfoSerializer(serializers.ModelSerializer):
    u"""问卷题目信息序列化"""

    question_info = serializers.SerializerMethodField()

    class Meta:
        model = SurveyQuestionInfo
        fields = ("survey_id", "project_id", "question_info", 'en_question_info', "block_id")

    def get_question_info(self, obj):
        if not obj.question_info:
            return {}
        return json.loads(obj.question_info)


class UserQuestionInfoSerializer(serializers.ModelSerializer):
    u"""问卷题目信息序列化"""

    question_info = serializers.SerializerMethodField()

    class Meta:
        model = UserQuestionInfo
        fields = ("survey_id", "project_id", "question_info", "block_id")

    def get_question_info(self, obj):
        if not obj.question_info:
            return {}
        return json.loads(obj.question_info)


class UserProjectGatherInfoSerializer(serializers.ModelSerializer):
    u"""问卷序列化"""
    pass


class PeopleSurveyResultSimpleSerializer(serializers.ModelSerializer):

    people_info = serializers.SerializerMethodField()
    survey_info = serializers.SerializerMethodField()
    answer_count = serializers.SerializerMethodField()

    class Meta:
        model = PeopleSurveyRelation
        fields = ('id', 'people_info', 'survey_info', 'model_score', 'answer_count')

    def get_people_info(self, obj):
        from wduser.models import People
        people = People.objects.get(id=obj.people_id)
        display_name = people.username
        if not display_name:
            display_name = people.phone if people.phone else people.email
        return {'display_name': display_name, 'people_id': people.id}

    def get_survey_info(self, obj):
        info = {"survey_name": "", "survey_id": obj.survey_id}
        qs = SurveyInfo.objects.filter_active(project_id=obj.project_id, survey_id=obj.survey_id)
        if qs.exists():
            survey = qs[0]
            info["survey_name"] = survey.survey_name
        return info

    def get_answer_count(self, obj):
        return UserQuestionAnswerInfo.objects.filter_active(
            people_id=obj.people_id,
            survey_id=obj.survey_id,
            project_id=obj.project_id
        ).values_list("question_id", flat=True).distinct().count()
