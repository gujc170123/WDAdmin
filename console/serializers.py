# -*- coding:utf-8 -*-

from rest_framework import serializers
from console.models import SurveyOverview, CleanTask, EscapeTask, AnalysisTask, SurveyOverviewAnalysisTask
from research.models import ResearchDimension
from survey.models import Survey
from research.serializers import ResearchDimensionDetailSerializer


class SurveyOverviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyOverview
        fields = ("id", "enterprise_id", "assess_id", "survey_id", "begin_time", "end_time", "total_num",
                  "effective_num", "clean_status", "escape_status", "analysis_status", "enterprise_name",
                  "survey_name", "assess_name")


class CleanTaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = CleanTask


class CleanTaskListSerializer(CleanTaskSerializer):
    overview_info = serializers.SerializerMethodField()
    clean_result = serializers.SerializerMethodField()

    class Meta:
        model = CleanTask

        fields = ('id', 'task_name', 'begin_time', 'end_time', 'clean_status', 'schedule', 'survey_overview_ids',
                  'parent_id', 'overview_info', 'task_name', 'num_of_consistency_check', 'min_time_of_answer',
                  'max_count_of_less_time', 'score_difference_of_each_group', 'social_desirability_score',
                  'clean_result')

    def get_overview_info(self, obj):
        qs = SurveyOverview.objects.filter_active(id__in=eval(obj.survey_overview_ids))
        return SurveyOverviewSerializer(instance=qs, many=True, context=self.context).data

    def get_clean_result(self, obj):
        from console.etl import EtlTrialClean
        etl = EtlTrialClean(obj.id)
        happy_score, valid, dimension_score = etl.result
        result = {'happy_score': happy_score, 'valid': valid, 'dimension_score': dimension_score}
        return result


class EscapeTaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = EscapeTask


class EscapeTaskListSerializer(EscapeTaskSerializer):
    overview_info = serializers.SerializerMethodField()

    class Meta:
        model = EscapeTask
        fields = ('id', 'task_name', 'survey_overview_ids', 'escape_model_id', 'begin_time', 'end_time', 'schedule',
                  'escape_status', 'overview_info')

    def get_overview_info(self, obj):
        qs = SurveyOverview.objects.filter_active(id__in=eval(obj.survey_overview_ids))
        return SurveyOverviewSerializer(instance=qs, many=True, context=self.context).data


class AnalysisTaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = AnalysisTask


class AnalysisTaskListSerializer(AnalysisTaskSerializer):
    overview_info = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisTask
        fields = ('id', 'task_name', 'survey_overview_ids', 'escape_model_id', 'begin_time', 'end_time', 'schedule',
                  'analysis_status', 'score', 'escape_task_id', 'overview_info')

    def get_overview_info(self, obj):
        qs = SurveyOverview.objects.filter_active(id__in=eval(obj.survey_overview_ids))
        return SurveyOverviewSerializer(instance=qs, many=True, context=self.context).data









