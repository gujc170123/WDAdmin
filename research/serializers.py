# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from rest_framework import serializers

from assessment.models import AssessProjectSurveyConfig, AssessSurveyRelation
from research.models import ResearchModel, ResearchDimension, ResearchSubstandard, Tag, GeneralTagRelation, \
    Report, ReportSurveyAssessmentProjectRelation
from survey.models import SurveyModelFacetRelation, SurveyQuestionRelation
from question.models import Question
from utils.serializers import WdTagListSerializer


class ResearchModelBasicSerializer(WdTagListSerializer, serializers.ModelSerializer):
    u"""模型新建与列表"""

    is_dimension_by_order = serializers.SerializerMethodField()

    class Meta:
        model = ResearchModel
        fields = ('id', 'root_model_id', 'name', 'en_name', 'model_type', 'model_category',
                  'status', 'desc', 'en_desc', 'inherit_count', 'used_count', 'root_model_name',
                  'algorithm_id', "is_dimension_by_order")

    def get_is_dimension_by_order(self, obj):
        qs = ResearchDimension.objects.filter_active(model_id=obj.id)
        if not qs.exists():
            return False
        elif qs.exists():
            o_n = qs.values_list("order_number", flat=True)
            if min(o_n) > 0:
                return True
            else:
                return False
        else:
            return False


class ResearchModelDetailSerializer(ResearchModelBasicSerializer):

    dimension = serializers.SerializerMethodField()


    class Meta:
        model = ResearchModel
        fields = ResearchModelBasicSerializer.Meta.fields + (
            'dimension',
        )

    def get_dimension(self, obj):
        qs = ResearchDimension.objects.filter_active(model_id=obj.id).order_by('order_number')
        return ResearchDimensionDetailSerializer(instance=qs, many=True, context=self.context).data


class ResearchDimensionBasicSerializer(WdTagListSerializer, serializers.ModelSerializer):
    u"""维度基础序列化"""

    class Meta:
        model = ResearchDimension
        fields = ("id", "model_id", "name", "en_name", "weight", "model_type", "model_name", 'model_category', 'order_number')


class ResearchDimensionDetailSerializer(ResearchDimensionBasicSerializer):
    u"""维度详情序列化"""

    substandards = serializers.SerializerMethodField()
    lie_question_count = serializers.SerializerMethodField()
    custom_config = serializers.SerializerMethodField()

    class Meta:
        model = ResearchDimension
        fields = ResearchDimensionBasicSerializer.Meta.fields + ('substandards', 'lie_question_count', 'custom_config')

    def get_substandards(self, obj):
        qs = ResearchSubstandard.objects.filter_active(dimension_id=obj.id, parent_id=0)
        return ResearchSubstandardDetailSerializer(instance=qs, many=True, context=self.context).data

    def get_custom_config(self, obj):
        request = self.context.get("request", None)
        if request is None:
            return 0
        with_model_custom_config = int(request.GET.get("with_model_custom_config", 0))
        survey_id = request.GET.get("survey_id", None)
        assess_id = request.GET.get("assess_id", None)
        if not with_model_custom_config or not survey_id or not assess_id:
            return {}
        config_qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_DIMENSION, model_id=obj.id
        ).order_by("-id")
        name = obj.name
        en_name = obj.en_name
        description = ""
        en_description = ""
        if config_qs.exists():
            name = config_qs[0].content
            en_name = config_qs[0].en_content
        config_qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_DIMENSION_DESC, model_id=obj.id
        ).order_by("-id")
        if config_qs.exists():
            description = config_qs[0].content
            en_description = config_qs[0].en_content
        return {
            "name": name,
            "en_name": en_name,
            "description": description,
            "en_description": en_description
        }

    def get_lie_question_count(self, obj):
        request = self.context.get("request", None)
        if request is None:
            return 0
        lie_detail = request.GET.get("lie_detail", 0)
        survey_id = request.GET.get("survey_id", None)
        if not lie_detail or not int(lie_detail) or not survey_id:
            return 0
        try:
            smfr_qs = SurveyModelFacetRelation.objects.filter_active(
                survey_id=survey_id,
                related_obj_type=SurveyModelFacetRelation.RELATED_DIMENSION, related_obj_id=obj.id).values_list(
                "id", flat=True
            )
            question_ids_1 = SurveyQuestionRelation.objects.filter_active(
                survey_id=survey_id, model_facet_relation_id__in=smfr_qs).values_list("question_id", flat=True)
            uniformity_count1 = Question.objects.filter_active(
                id__in=question_ids_1,
                question_category=Question.CATEGORY_UNIFORMITY).count()
            praise_count1 = Question.objects.filter_active(
                id__in=question_ids_1,
                question_category=Question.CATEGORY_PRAISE).count()
            substandard_ids = ResearchSubstandard.objects.filter_active(
                dimension_id=obj.id).values_list("id", flat=True)
            smfr_qs = SurveyModelFacetRelation.objects.filter_active(
                survey_id=survey_id,
                related_obj_type=SurveyModelFacetRelation.RELATED_SUBSTANDARD, related_obj_id__in=substandard_ids).values_list(
                "id", flat=True
            )
            question_ids_2 = SurveyQuestionRelation.objects.filter_active(
                survey_id=survey_id, model_facet_relation_id__in=smfr_qs).values_list("question_id", flat=True)
            uniformity_count2 = Question.objects.filter_active(
                id__in=question_ids_2,
                question_category=Question.CATEGORY_UNIFORMITY).count()
            praise_count2 = Question.objects.filter_active(
                id__in=question_ids_2,
                question_category=Question.CATEGORY_PRAISE).count()
            return [uniformity_count1+uniformity_count2, praise_count1+praise_count2]
        except Exception, e:
            print e
            return 0


class ResearchSubstandardBasicSerializer(WdTagListSerializer, serializers.ModelSerializer):
    u"""指标基础序列化"""

    class Meta:
        model = ResearchSubstandard
        fields = ("id", "model_id", "dimension_id", "parent_id", "name", 'model_category',
                  "en_name", "weight", "model_type", "model_name", "dimension_name")


class ResearchSubstandardDetailSerializer(ResearchSubstandardBasicSerializer):
    u"""指标基础序列化"""

    substandards = serializers.SerializerMethodField()
    custom_config = serializers.SerializerMethodField()

    class Meta:
        model = ResearchSubstandard
        fields = ResearchSubstandardBasicSerializer.Meta.fields + ('substandards', 'custom_config')

    def get_substandards(self, obj):
        # TODO：性能优化，model_name， dimension_name 会重复获取很多次
        qs = ResearchSubstandard.objects.filter_active(parent_id=obj.id)
        return ResearchSubstandardDetailSerializer(instance=qs, many=True, context=self.context).data

    def get_custom_config(self, obj):
        request = self.context.get("request", None)
        if request is None:
            return 0
        with_model_custom_config = int(request.GET.get("with_model_custom_config", 0))
        survey_id = request.GET.get("survey_id", None)
        assess_id = request.GET.get("assess_id", None)
        if not with_model_custom_config or not survey_id or not assess_id:
            return {}
        config_qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_SUBSTANDARD, model_id=obj.id
        ).order_by("-id")
        name = obj.name
        en_name = obj.en_name
        description = ""
        en_description = ""
        if config_qs.exists():
            name = config_qs[0].content
            en_name = config_qs[0].en_content
        config_qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_SUBSTANDARD_DESC, model_id=obj.id
        ).order_by("-id")
        if config_qs.exists():
            description = config_qs[0].content
            en_description = config_qs[0].en_content
        return {
            "name": name,
            "en_name": en_name,
            "description": description,
            "en_description": en_description
        }


class TagBasicSerializer(serializers.ModelSerializer):
    u"""标签序列化"""

    class Meta:
        model = Tag
        fields = ("id", "tag_type", "business_model", "tag_name", "is_required",
                  "is_system", "enterprise_id", "tag_config", "tag_config_data")


class TagRelationSerializer(serializers.ModelSerializer):
    u"""标签 业务模型序列化"""

    class Meta:
        model = GeneralTagRelation
        fields = ("id", "tag_id", "object_id", "tag_value")


class ReportBasicSerializer(serializers.ModelSerializer):
    u"""报告模板序列化"""
    survey_info = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = ('id', 'report_name', 'desc', 'survey_info', 'report_url',  'report_type_id',)

    def get_survey_info(self, obj):
        qs = ReportSurveyAssessmentProjectRelation.objects.filter_active(report_id=obj.id).order_by('-id')
        if not qs.exists():
            return []
        else:
            data = []
            for o in qs[:3]:
                try:
                    asr_qs = AssessSurveyRelation.objects.filter_active(assess_id=o.assessment_project_id, survey_id=o.survey_id)
                    if asr_qs.exists():
                        a = json.loads(asr_qs[0].custom_config)
                        survey_name = a.get("survey_name", None)
                        if not survey_name:
                            survey_name = o.survey_name
                    else:
                        survey_name = o.survey_name
                except:
                    survey_name = o.survey_name
                survey_info = {
                    "survey_id": o.survey_id,
                    "survey_name": survey_name,
                    # "survey_name": o.survey_name,
                    "assess_name": o.assessment_project_name
                }
                data.append(survey_info)
        return data


class ReportSurveyAssessmentProjectSerializer(serializers.ModelSerializer):
    u"""报告 问卷 项目 创建关联关系序列化"""

    survey_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportSurveyAssessmentProjectRelation
        fields = ('id', 'survey_id', 'assessment_project_id', 'report_id',
                  'survey_name', 'assessment_project_name', )

    def get_survey_name(self, obj):
        asr_qs = AssessSurveyRelation.objects.filter_active(assess_id=obj.assessment_project_id,
                                                            survey_id=obj.survey_id)
        survey_name = obj.survey_name
        try:
            if asr_qs.exists():
                a = json.loads(asr_qs[0].custom_config)
                survey_name = a.get("survey_name", None)
                if not survey_name:
                    survey_name = obj.survey_name
        except:
            return survey_name
        return survey_name

