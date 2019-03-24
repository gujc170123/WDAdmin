# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from utils.models import BaseModel
from wduser.models import EnterpriseInfo
from survey.models import Survey
from assessment.models import AssessProject
import json
from django.utils import timezone
from survey.models import SurveyModelFacetRelation, SurveyQuestionRelation, SurveyQuestionResult
from question.models import QuestionFacet


class SurveyOverview(BaseModel):
    """总揽表"""
    # enterprise_id start_time end_time 冗余字段
    enterprise_id = models.BigIntegerField(u"企业名称id", default=0, db_index=True)
    enterprise_name = models.CharField(u"企业名称", max_length=256, default='', db_index=True)
    assess_id = models.BigIntegerField(u"测评项目id", default=0, db_index=True)
    assess_name = models.CharField(u"项目名称", max_length=256, default='', db_index=True)
    survey_id = models.BigIntegerField(u"问卷id", default=0, db_index=True)
    survey_name = models.CharField(u"问卷名称", max_length=256, default='', db_index=True)
    begin_time = models.DateTimeField(u"开始时间", db_index=True, blank=True, null=True)
    end_time = models.DateTimeField(u"结束时间", db_index=True, blank=True, null=True)
    total_num = models.BigIntegerField(u"总人数", default=0)
    effective_num = models.BigIntegerField(u"有效人数", default=0)
    CLEAN_STATUS_NOT_CLEANED = 10
    CLEAN_STATUS_TRIAL_CLEANING = 20
    CLEAN_STATUS_TRIAL_CLEANED = 30
    CLEAN_STATUS_CLEANING = 40
    CLEAN_STATUS_CLEANED = 50
    CLEAN_STATUS_CHOICES = (
        (CLEAN_STATUS_NOT_CLEANED, u"未清洗"),
        (CLEAN_STATUS_TRIAL_CLEANING, u"试清洗中"),
        (CLEAN_STATUS_TRIAL_CLEANED, u"已试清洗"),
        (CLEAN_STATUS_CLEANING, u"清洗中"),
        (CLEAN_STATUS_CLEANED, u"已清洗"),
    )
    clean_status = models.PositiveIntegerField(u"清洗状态", default=CLEAN_STATUS_NOT_CLEANED, db_index=True, choices=CLEAN_STATUS_CHOICES)
    ESCAPE_STATUS_NOT_ESCAPED = 10
    ESCAPE_STATUS_ESCAPING = 20
    ESCAPE_STATUS_ESCAPED = 30
    ESCAPE_STATUS_CHOICES = (
        (ESCAPE_STATUS_NOT_ESCAPED, u"未转义"),
        (ESCAPE_STATUS_ESCAPING, u"转义中"),
        (ESCAPE_STATUS_ESCAPED, u"已转义"),
    )
    escape_status = models.PositiveIntegerField(u"转义状态", default=ESCAPE_STATUS_NOT_ESCAPED, db_index=True, choices=ESCAPE_STATUS_CHOICES)
    ANALYSIS_STATUS_NOT_SET_UP = 10
    ANALYSIS_STATUS_SETTING_UP = 20
    ANALYSIS_STATUS_SET_UP = 30
    ANALYSIS_STATUS_CHOICES = (
        (ANALYSIS_STATUS_NOT_SET_UP, u"未解析"),
        (ANALYSIS_STATUS_SETTING_UP, u"解析中"),
        (ANALYSIS_STATUS_SET_UP, u"已解析"),
    )
    analysis_status = models.PositiveIntegerField(u"解析状态", default=ANALYSIS_STATUS_NOT_SET_UP, db_index=True, choices=ANALYSIS_STATUS_CHOICES)


class CleanTask(BaseModel):
    """清洗任务"""
    task_name = models.CharField(max_length=256, default="")
    parent_id = models.BigIntegerField(u"父id", default=0, db_index=True)
    survey_overview_ids = models.CharField(u"清洗任务对应的总揽表的id", default="", max_length=256, null=True, db_index=True)
    num_of_consistency_check = models.IntegerField(u"未通过一致性检验的题数", default=-1)
    min_time_of_answer = models.IntegerField(u"每道题的最低答题时间", default=-1)
    max_count_of_less_time = models.IntegerField(u"答题时间未满足要求的最多个数", default=-1)
    score_difference_of_each_group = models.IntegerField(u"一致性题目的分值差值", default=-1)
    social_desirability_score = models.IntegerField(u"社会称许题的最低总得分", default=-1)
    begin_time = models.DateTimeField(u"清洗开始时间", default=timezone.now, blank=True, null=True, db_index=True)
    end_time = models.DateTimeField(u"清洗结束时间", blank=True, null=True, db_index=True)
    schedule = models.FloatField(u"进度", default=0.0)
    CLEAN_STATUS_NOT_TRIAL = 10
    CLEAN_STATUS_TRIALING = 20
    CLEAN_STATUS_TRIAL_CLEANED = 30
    CLEAN_STATUS_NOT_CLEANED = 40
    CLEAN_STATUS_CLEANING = 50
    CLEAN_STATUS_CLEANED = 60
    CLEAN_STATUS_TERMINATION = 70
    CLEAN_STATUS_CHOICES = (
        (CLEAN_STATUS_NOT_TRIAL, u"试清洗等待中"),
        (CLEAN_STATUS_TRIALING, u'试清洗中'),
        (CLEAN_STATUS_TRIAL_CLEANED, u"试洗完毕"),
        (CLEAN_STATUS_NOT_CLEANED, u"清洗等待中"),
        (CLEAN_STATUS_CLEANING, u'清洗中'),
        (CLEAN_STATUS_CLEANED, u"清洗完毕"),
        (CLEAN_STATUS_TERMINATION, u"终止状态" )
    )
    clean_status = models.PositiveIntegerField(u"清洗状态", default=CLEAN_STATUS_NOT_TRIAL, db_index=True, choices=CLEAN_STATUS_CHOICES)


class SurveyOverviewCleanTask(BaseModel):
    """总表与试清洗/正式任务关联"""
    enterprise_id = models.BigIntegerField(u"企业id", default=0, db_index=True)
    assess_id = models.BigIntegerField(u"项目id", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"问卷id", default=0, db_index=True)
    survey_overview_id = models.BigIntegerField(u"总表", default=0, db_index=True)
    clean_task_id = models.BigIntegerField(u"清洗任务", default=0, db_index=True)


class EscapeTask(BaseModel):
    """创建转义任务"""
    task_name = models.CharField(max_length=256)
    begin_time = models.DateTimeField(u"清洗开始时间", default=timezone.now, blank=True, null=True, db_index=True)
    end_time = models.DateTimeField(u"清洗结束时间", blank=True, null=True, db_index=True)
    escape_model_id = models.BigIntegerField(u"转义模型id", default=0, db_index=True)
    escape_model_name = models.CharField(u"转义模型名称", max_length=256)
    clean_task_id = models.BigIntegerField(u"清洗任务id", default=0, db_index=True)
    # eg json "survey_overview_ids": [1,2,3]
    survey_overview_ids = models.CharField(u"转义任务对应的总揽表的id", default="[]", max_length=256, null=True, db_index=True)
    schedule = models.DecimalField(u"进度", default=0, max_digits=3, decimal_places=2)
    ESCAPE_STATUS_NOT_ESCAPED = 10
    ESCAPE_STATUS_ESCAPED = 20
    ESCAPE_STATUS_CHOICES = (
        (ESCAPE_STATUS_NOT_ESCAPED, u"等待中"),
        (ESCAPE_STATUS_ESCAPED, u"转义完毕"),
    )
    escape_status = models.PositiveIntegerField(u"转义状态", default=ESCAPE_STATUS_NOT_ESCAPED, db_index=True,
                                                choices=ESCAPE_STATUS_CHOICES)


class SurveyOverviewEscapeTask(BaseModel):
    """创建总表与转义任务的关联"""
    survey_overview_id = models.BigIntegerField(u"总表", default=0, db_index=True)
    escape_task_id = models.BigIntegerField(u"清洗任务", default=0, db_index=True)
    # enterprise_id assess_id survey_id model_id冗余字段
    assess_id = models.BigIntegerField(u"项目id", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"问卷id", default=0, db_index=True)
    enterprise_id = models.BigIntegerField(u"企业id", default=0, db_index=True)
    # model_id = models.BigIntegerField(u"转义模型id", default=0, db_index=True)


class AnalysisTask(BaseModel):
    """创建解析任务"""
    # survey_overview_id assess_id survey_id 冗余字段
    task_name = models.CharField(max_length=250)
    begin_time = models.DateTimeField(u"分析开始时间", default=timezone.now, blank=True, null=True, db_index=True)
    end_time = models.DateTimeField(u"分析结束时间", blank=True, null=True, db_index=True)
    escape_task_id = models.BigIntegerField(u"转义任务id", default=0, db_index=True)
    escape_model_id = models.BigIntegerField(u"转义模型id", default=0, db_index=True)
    schedule = models.DecimalField(u"进度", default=0, max_digits=3, decimal_places=2)
    score = models.IntegerField(u"分数", default=0)
    # survey_overview_ids = models.CharField(u"解析任务的ids", max_length=250, default="")
    survey_overview_ids = models.CharField(u"转义任务对应的总揽表的id", default="[]", max_length=256, null=True, db_index=True)
    # 分段
    CONFIG_TYPE_BY_FACET = 1
    CONFIG_TYPE_BY_DIMENSION = 2
    CONFIG_TYPE_BY_SUBSTANDARD = 3
    # TODO
    DEFAULT_CONFIG = {
        'config_type': CONFIG_TYPE_BY_FACET,
        'min': 0,
        'max': 40,
        'name': '',
        'color': ''
    }
    config_info = models.CharField(u"自定义配置", max_length=256, null=True, blank=True)
    ANALYSIS_STATUS_NOT_SET_UP = 10
    ANALYSIS_STATUS_SET_UP = 20
    ANALYSIS_STATUS_CHOICES = (
        (ANALYSIS_STATUS_NOT_SET_UP, u"等待中"),
        (ANALYSIS_STATUS_SET_UP, u"解析完毕"),
    )
    analysis_status = models.PositiveIntegerField(u"解析状态", default=ANALYSIS_STATUS_NOT_SET_UP, db_index=True,choices=ANALYSIS_STATUS_CHOICES)

    @property
    def custom_config(self):
        if not self.config_info:
            return self.DEFAULT_CONFIG
        config_info = json.loads(self.config_info)
        custom_config = {}
        for key in self.DEFAULT_CONFIG.keys():
            custom_config[key] = config_info.get(key, self.DEFAULT_CONFIG[key])
        return custom_config

    def set_custom_config(self, custom_config):
        set_custom_config = {}
        for key in self.DEFAULT_CONFIG:
            set_custom_config[key] = custom_config.get(key, self.DEFAULT_CONFIG[key])
        if not self.config_info:
            self.config_info = json.dumps(set_custom_config)
        else:
            config_info = json.loads(self.config_info)
            for key in set_custom_config:
                config_info[key] = set_custom_config[key]
            self.config_info = json.dumps(config_info)
        self.save()


class SurveyOverviewAnalysisTask(BaseModel):
    """创建总表与解析任务的关联"""
    survey_overview_id = models.BigIntegerField(u"总表", default=0, db_index=True)
    analysis_task_id = models.BigIntegerField(u"分析任务", default=0, db_index=True)
    # model_id = models.BigIntegerField(u"转义模型id", default=0, db_index=True)
    enterprise_id = models.BigIntegerField(u"企业id", default=0, db_index=True)
    assess_id = models.BigIntegerField(u"项目id", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"问卷id", default=0, db_index=True)


class ConsoleSurveyModelFacetRelation(BaseModel):
    escape_task_id = models.BigIntegerField(u"转义任务id", default=0, db_index=True)
    u"""问卷模型构面关联"""
    survey_id = models.BigIntegerField(u"问卷ID", default=0, db_index=True)
    # TODO：问卷变更模型时，需要把之前关联的模型题目关系去掉
    model_id = models.BigIntegerField(u"问卷关联的模型ID", default=0, db_index=True)
    RELATED_TYPE_AUTO = 10
    RELATED_TYPE_MANUAL = 20
    RELATED_TYPE_ESCAPE = 30
    RELATED_CHOICES = (
        (RELATED_TYPE_AUTO, u"自动关联"),
        (RELATED_TYPE_MANUAL, u"手动关联"),
        (RELATED_TYPE_ESCAPE, u"转义关联")
    )
    related_type = models.PositiveSmallIntegerField(u"问卷题目关联方式", default=RELATED_TYPE_ESCAPE, choices=RELATED_CHOICES)
    # 构面关联对象类型
    RELATED_DIMENSION = 1
    RELATED_SUBSTANDARD = 2
    RELATED_CHOICES = (
        (RELATED_DIMENSION, u"维度"),
        (RELATED_SUBSTANDARD, u"指标")
    )
    # 问卷关联的是 维度 或 指标??
    related_obj_type = models.BigIntegerField(u"问卷关联的模型ID", default=0, db_index=True)
    # 维度 或 指标 的id
    related_obj_id = models.BigIntegerField(u"问卷关联对象的ID", default=0, db_index=True)
    # 构面 [{"facet_id":xx,'weight':xxx}, {"facet_id":xx,'weight':xxx}]
    # version: 仅能选择一个构面[{"facet_id":xx,'weight':xxx}]，但是可以多次选择，生成多条记录
    facet_ids = models.CharField(u"构面ID", max_length=128)
    question_count = models.PositiveIntegerField(u"题目数量", default=0)

    def get_facet_infos(self):
        u"""兼容旧数据，facet_ids=[1,2,3]"""
        if not self.facet_ids:
            return [], []
        facet_info = json.loads(self.facet_ids)
        if type(facet_info) == list and len(facet_info) > 0 and type(facet_info[0]) != dict:
            ids = list(set(facet_info))
            weights = []
            for facet_id in ids:
                weights.append(QuestionFacet.objects.get(id=facet_id).weight)
            return ids, weights
        else:
            ids = []
            weights = []
            for facet in facet_info:
                ids.append(facet["id"])
                weights.append(facet["weight"])
            return ids, weights

    @classmethod
    def is_need_rebuild(cls, survey_id):
        u"""检查是否SurveyModelFacetRelation有变更，有变更后需要重新组卷"""
        try:
            smfr_qs = SurveyModelFacetRelation.objects.filter_active(
                survey_id=survey_id).order_by('-update_time')
            if not smfr_qs.exists():
                return True
            smfr_update_time = smfr_qs[0].update_time
            sqr_qs = SurveyQuestionResult.objects.filter_active(
                survey_id=survey_id).order_by('-update_time')
            if not sqr_qs.exists():
                return True
            sqr_update_time = sqr_qs[0].update_time
            if smfr_update_time > sqr_update_time:
                return True
            else:
                return False
        except Exception, e:
            print e
            return True


class ConsoleSurveyQuestionRelation(BaseModel):
    u"""问卷题目关联关系
    问卷关联模型，模型维度或指标关联题目，普通组卷或者迫选组卷，手动选题或者自动选题
    """
    survey_id = models.BigIntegerField(u"问卷ID", default=0, db_index=True)
    model_facet_relation_id = models.BigIntegerField(u"构面关联关系ID", default=0, db_index=True)
    question_id = models.BigIntegerField(u"关联的题目ID", default=0, db_index=True)
    escape_task_id = models.BigIntegerField(u"转义任务id", default=0, db_index=True)





