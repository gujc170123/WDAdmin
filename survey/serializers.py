# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from rest_framework import serializers

from assessment.models import AssessProjectSurveyConfig
from survey.models import Survey, SurveyQuestionResult
from utils.serializers import WdTagListSerializer


class SurveyBasicSerializer(WdTagListSerializer, serializers.ModelSerializer):
    u"""调查新建与列表"""
    use_count = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = ("id", "model_id", "title", "en_title", "survey_type", "form_type", "custom_config",
                  "survey_status", "desc", 'en_desc', "model_name", "use_count",
                  "time_limit", "force_option_num", "force_base_level")

    def get_use_count(self, obj):
        # 燕计划，临时前端返回问卷使用次数为0，方便调整信息
        return 0


class SurveyForceQuestionResultSerializer(serializers.ModelSerializer):
    u"""问卷题目关联结果  """

    title = serializers.SerializerMethodField()
    force_titles = serializers.SerializerMethodField()
    en_title = serializers.SerializerMethodField()
    en_force_titles = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = SurveyQuestionResult
        fields = ("id", "order_num", "title", "force_titles", "options"
                  , "en_title", "en_force_titles")

    def get_title(self, obj):
        u"""获取题干
        支持项目中自定义题干
        """
        request = self.context.get("request", None)
        is_test = self.context.get("is_test", False)
        title = SurveyQuestionResult.get_force_question_title(obj.custom_config)
        if not is_test and (not request or request.GET.get("with_custom_config", None) != "1"):
            return title
        if is_test:
            assess_id = self.context.get("assess_id", None)
            survey_id = self.context.get("survey_id", None)
        else:
            assess_id = request.GET.get("assess_id", 0)
            survey_id = request.GET.get("survey_id", 0)
        if not assess_id or not survey_id:
            return title
        qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_QUESTION,
            model_id=obj.id
        ).order_by("-id")
        if not qs.exists():
            return title
        # @version: 20180725 @summary: 自定义题干设置，支持单选 单选填空 多选 多选填空 滑块，互斥题
        return qs[0].content

    def get_force_titles(self, obj):
        return SurveyQuestionResult.get_force_titles(obj.custom_config)

    def get_en_title(self, obj):
        request = self.context.get("request", None)
        is_test = self.context.get("is_test", False)
        en_title = SurveyQuestionResult.get_en_force_question_title(obj.custom_config)
        if not is_test and (not request or request.GET.get("with_custom_config", None) != "1"):
            return en_title
        if is_test:
            assess_id = self.context.get("assess_id", None)
            survey_id = self.context.get("survey_id", None)
        else:
            assess_id = request.GET.get("assess_id", 0)
            survey_id = request.GET.get("survey_id", 0)
        if not assess_id or not survey_id:
            return en_title
        qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_QUESTION,
            model_id=obj.id
        ).order_by("-id")
        if not qs.exists():
            return en_title
        if qs[0].en_content:
            return qs[0].en_content
        else:
            return qs[0].content

    def get_en_force_titles(self, obj):
        return SurveyQuestionResult.get_en_force_titles(obj.custom_config)

    def get_options(self, obj):
        return SurveyQuestionResult.get_force_options(obj.custom_config, context=self.context)