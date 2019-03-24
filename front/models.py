# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

import datetime

from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
from assessment.models import AssessSurveyRelation
from question.models import Question
from survey.models import Survey
from utils.models import BaseModel


class SurveyInfo(BaseModel):
    u"""问卷的基本信息表"""
    survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
    project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
    survey_name = models.CharField(u"测验名称", max_length=200)
    en_survey_name = models.CharField(u"英文测验名称", max_length=200, default=u'', null=True, blank=True)
    survey_desc = models.CharField(u"测验问卷说明", max_length=2000, null=True, blank=True)
    en_survey_desc = models.CharField(u"英文测验问卷说明", max_length=2000, default=u'', null=True, blank=True)
    begin_time = models.DateTimeField(u"测验的开始时间", db_index=True)
    end_time = models.DateTimeField(u"测验的结束时间", db_index=True)
    project_name = models.CharField(u"项目名称", max_length=200)
    en_project_name = models.CharField(u"英文项目名称", max_length=200, default=u'', null=True, blank=True)
    SURVEY_TYPE_ORG = 10
    SURVEY_TYPE_PERSONAL = 20
    SURVEY_TYPE_360 = 30
    SURVEY_TYPE_CHOICES = (
        (SURVEY_TYPE_ORG, u"组织测评"),
        (SURVEY_TYPE_PERSONAL, u"个人测评"),
        (SURVEY_TYPE_360, u"360测评")
    )
    survey_type = models.PositiveSmallIntegerField(u"测验类型", choices=SURVEY_TYPE_CHOICES, db_index=True, default=SURVEY_TYPE_ORG)
    form_type = models.PositiveSmallIntegerField(u"组卷方式", choices=Survey.FORM_TYPE_CHOICES, default=Survey.FORM_TYPE_NORMAL)
    PROJECT_TYPE_ORG = 100
    PROJECT_TYPE_PERSONAL = 200
    PROJECT_TYPE_360 = 300
    PROJECT_TYPE_CHOICES = (
        (PROJECT_TYPE_ORG, u"组织测评项目"),
        (PROJECT_TYPE_PERSONAL, u"个人测评项目"),
        (PROJECT_TYPE_360, u"360测评项目")
    )
    project_type = models.PositiveSmallIntegerField(u"测验项目类型", choices=PROJECT_TYPE_CHOICES, db_index=True, default=PROJECT_TYPE_ORG)
    config_info = models.CharField(u"问卷配置信息", max_length=1024, null=True, blank=True)
    # [{"id":x,"name":x,"desc":x}]
    block_info = models.TextField(u"问卷的块信息", null=True, blank=True)
    time_limit = models.PositiveSmallIntegerField(u"问卷限时（分钟）", default=0)
    #
    STATUS_WAITING = 0     #  未开放
    STATUS_WORKING = 10    #  已开放
    STATUS_DOING = 15      #  答卷中     答卷中
    STATUS_END = 20        #  已结束
    # 按部分测试 逐题测试
    TEST_TYPE_BY_PART = 1
    TEST_TYPE_BY_QUESTION = 2
    #
    RANDOM_OPTION_DEFAULT = 0
    RANDOM_OPTION_RANDOM = 1
    RANDOM_OPTION_ORDER_RANDOM = 2
    #
    DEFAULT_CONFIG = {
        "test_type": TEST_TYPE_BY_PART,
        'random_options': RANDOM_OPTION_DEFAULT,
        'random_question': False,
        'goto_next_question': False,
        'unfinished_commit': False,
        'force_option_num': 0,
        "finish_redirect": "",
        "assess_logo": "",
        "advert_url": ""
    }

    @property
    def status(self):
        now = datetime.datetime.now()
        # now = now.replace(tzinfo=pytz.timezone(settings.TIME_ZONE))
        if self.begin_time is None or self.end_time is None:
            return self.STATUS_WAITING
        elif now < self.begin_time:
            return self.STATUS_WAITING
        elif now < self.end_time:
            return self.STATUS_WORKING
        else:
            return self.STATUS_END

    @property
    def test_type(self):
        if not self.config_info:
            return self.TEST_TYPE_BY_PART
        config = json.loads(self.config_info)
        test_type = config.get("test_type", self.TEST_TYPE_BY_PART)
        return test_type

    @property
    def random_question(self):
        if not self.config_info:
            return False
        config = json.loads(self.config_info)
        return config.get("random_question", False)

    @property
    def random_options(self):
        if not self.config_info:
            return False
        config = json.loads(self.config_info)
        value = config.get("random_options", self.RANDOM_OPTION_DEFAULT)
        # 兼容老数据 value == True or False
        if value == False:
            return self.RANDOM_OPTION_DEFAULT
        elif value == True:
            return self.RANDOM_OPTION_RANDOM
        else:
            return value

    def set_assess_log(self, logo):
        if not self.config_info:
            config_info = self.DEFAULT_CONFIG
        else:
            config_info = json.loads(self.config_info)
        config_info["assess_logo"] = logo
        self.config_info = json.dumps(config_info)
        self.save()


class PeopleSurveyRelation(BaseModel):
    u"""用户问卷的关联信息"""

    people_id = models.BigIntegerField(u"测验用户ID", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
    project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
    #
    ROLE_TYPE_NORMAL = 10
    ROLE_TYPE_SELF = 20
    ROLE_TYPE_HIGHER_LEVEL = 30
    ROLE_TYPE_LOWER_LEVEL = 40
    ROLE_TYPE_SAME_LEVEL = 50
    ROLE_TYPE_SUPPLIER_LEVEL = 60
    ROLE_CHOICES = (
        (ROLE_TYPE_NORMAL, u"普通"),
        (ROLE_TYPE_SELF, u"自评"),
        (ROLE_TYPE_HIGHER_LEVEL, u"上级"),
        (ROLE_TYPE_LOWER_LEVEL, u"下级"),
        (ROLE_TYPE_SAME_LEVEL, u"同级"),
        (ROLE_TYPE_SUPPLIER_LEVEL, u"供应商")
    )
    role_type = models.PositiveSmallIntegerField(u"测评角色", default=ROLE_TYPE_NORMAL, choices=ROLE_CHOICES, db_index=True)
    evaluated_people_id = models.BigIntegerField(u"被评价人员ID", db_index=True, default=0)
    # survey_name 有可能与人有关 例如360测评
    survey_name = models.CharField(u"测验名称", max_length=200)
    en_survey_name = models.CharField(u"英文测验名称", max_length=1000, null=True, blank=True, default=u'')
    STATUS_NOT_BEGIN = 0
    STATUS_DOING = 10
    STATUS_DOING_PART = 15
    STATUS_FINISH = 20
    STATUS_EXPIRED = 21
    STATUS_CHOICES = (
        (STATUS_NOT_BEGIN, u"未开始"),
        (STATUS_DOING, u"已开放"),     #  10.8 进行中 改成 已开放
        (STATUS_DOING_PART, u"答卷中"),
        (STATUS_FINISH, u"已完成"),
        (STATUS_EXPIRED, u"已过期/未完成")
    )
    # 用户提交状态
    status = models.PositiveSmallIntegerField(u"测评状态", db_index=True, default=STATUS_NOT_BEGIN, choices=STATUS_CHOICES)
    #
    begin_answer_time = models.DateTimeField(u"开始答卷时间", null=True, blank=True)
    finish_time = models.DateTimeField(u"完成时间", null=True, blank=True)
    is_overtime = models.BooleanField(u"是否超时", default=False)
    # 用户报告状态
    REPORT_INIT = 0
    REPORT_GENERATING = 10
    REPORT_SUCCESS = 20
    REPORT_FAILED = 30
    REPORT_STATUS_CHOICES = (
        (REPORT_INIT, u"问卷未完成"),
        (REPORT_GENERATING, u"报告生成中"),
        (REPORT_SUCCESS, u"报告生成成功"),
        (REPORT_FAILED, u"报告生成失败")
    )
    report_status = models.PositiveSmallIntegerField(u"报告状态", db_index=True, default=REPORT_INIT, choices=REPORT_STATUS_CHOICES)
    report_url = models.URLField(u"报告地址", null=True, blank=True)
    en_report_url = models.URLField(u"英文报告地址", null=True, blank=True)
    # 模型分
    model_score = models.FloatField(u"模型分", default=0, db_index=True)
    # 包含维度下的测谎称许得分，uniformity_score： {"qid": {"src_score":x, 'uniformity_q_score':x, 'uniformity_q_id':qid}, ...}
    # {"did":{"score":xx,"name":xx,"uniformity_score":{"qid":{"src_score":xxx,...}}}, }
    dimension_score = models.TextField(u"维度分", null=True, blank=True)
    substandard_score = models.TextField(u"指标分", null=True, blank=True)
    facet_score = models.TextField(u"构面分", null=True, blank=True)
    happy_score = models.FloatField(u"幸福指数分", default=0, db_index=True)
    happy_ability_score = models.FloatField(u"幸福能力分", default=0, db_index=True)
    happy_efficacy_score = models.FloatField(u"幸福效能分", default=0, db_index=True)
    # pressure_score = models.FloatField(u"压力分", default=0, db_index=True)
    praise_score = models.FloatField(u"社会称许得分", default=0, db_index=True)
    uniformity_score = models.TextField(u"一致性得分", null=True, blank=True)

    @property
    def used_time(self):
        if self.status != PeopleSurveyRelation.STATUS_FINISH:
            time = datetime.datetime.now()
        else:
            time = self.finish_time
        if not time:
            time = datetime.datetime.now()
        used_time = time - self.begin_answer_time
        return used_time.seconds

    @property
    def status_name(self):
        for info in self.STATUS_CHOICES:
            if info[0] == self.status:
                return info[1]
        return "未知"

    @property
    def dimension_score_map(self):
        if not self.dimension_score:
            return {}
        try:
            dimension_score_map = json.loads(self.dimension_score)
            return dimension_score_map
        except:
            return {}

    @property
    def substandard_score_map(self):
        # {'id':{'name'xx,'score':xx}}
        # {'like':{'d':x,'i':xx}}
        if not self.substandard_score:
            return {}
        try:
            substandard_score_map = json.loads(self.substandard_score)
            return substandard_score_map
        except:
            return {}

    def all_substandard_score_map(self):
        def get_score_map(substandards):
            for substandard_id in substandards:
                if type(substandards) == dict:
                    child_substandards = None
                    if type(substandards[substandard_id]) == dict and "child_substandard" in substandards[substandard_id]:
                        child_substandards = substandards[substandard_id].pop("child_substandard", None)
                    all_score_map[str(substandard_id)] = substandards[substandard_id]
                    if child_substandards:
                        get_score_map(child_substandards)
                elif type(substandards) == list:
                    all_score_map[str(substandard_id["id"])] = substandard_id
        score_map = self.substandard_score_map
        all_score_map = {}
        get_score_map(score_map)
        return all_score_map



# class SurveyBlockInfo(BaseModel):
#     u"""问卷的块信息"""


class SurveyQuestionInfo(BaseModel):
    u"""问卷的题目信息"""
    survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
    project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
    question_info = models.TextField(u"题目信息")
    en_question_info = models.TextField(u"英文题目信息", null=True, blank=True, default=u'')
    block_id = models.BigIntegerField(u"问卷块ID", default=0, db_index=True)
    config_info = models.CharField(u"问卷配置信息", max_length=1024, null=True, blank=True)

    @property
    def random_question(self):
        if not self.config_info:
            return False
        config = json.loads(self.config_info)
        return config.get("random_question", False)

    @property
    def random_options(self):
        if not self.config_info:
            return False
        config = json.loads(self.config_info)
        value =  config.get("random_options", SurveyInfo.RANDOM_OPTION_DEFAULT)
        # 兼容老数据 value == True or False
        if value == False:
            return SurveyInfo.RANDOM_OPTION_DEFAULT
        elif value == True:
            return SurveyInfo.RANDOM_OPTION_RANDOM
        else:
            return value


class UserSurveyBlockStatus(BaseModel):
    u"""用户问卷块状态
    1. 问卷是否读取过
    2. 块是否读取过
    3. 问卷或块的总的答题时间
    """
    people_id = models.BigIntegerField(u"测验用户ID", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
    project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
    # 逐题答题，block_id = 0， 部分答题 block_id = 维度ID，block_id=-1时，代表部分答题时问卷整体的状态
    BLOCK_BY_QUESTION = 0
    BLOCK_PART_ALL = -1
    block_id = models.BigIntegerField(u"问卷块ID", default=0, db_index=True)
    STATUS_UNREAD = 10
    STATUS_READ = 20
    STATUS_CHOICES = (
        (STATUS_UNREAD, u"未读"),
        (STATUS_READ, u"已读")
    )
    # {'survey_status': STATUS_UNREAD, 'block_status': {id1:STATUS_UNREAD, id2:STATUS_UNREAD}}
    status = models.PositiveIntegerField(u"状态", default=STATUS_UNREAD, db_index=True)
    answer_count_time = models.PositiveIntegerField(u"回答时间(秒)", default=0, db_index=True)
    is_finish = models.BooleanField(u"是否完成", default=False, db_index=True)
    role_type = models.PositiveSmallIntegerField(u"测评角色", default=PeopleSurveyRelation.ROLE_TYPE_NORMAL, choices=PeopleSurveyRelation.ROLE_CHOICES, db_index=True)
    evaluated_people_id = models.BigIntegerField(u"被评价人员ID", db_index=True, default=0)


class UserProjectSurveyGatherInfo(BaseModel):
    u"""信息采集"""
    people_id = models.BigIntegerField(u"测验用户ID", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
    project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
    info_id = models.BigIntegerField(u"信息收集ID", default=0, db_index=True)
    info_value = models.CharField(u"信息收集值", max_length=200, null=True, blank=True)
    en_info_value = models.CharField(u"英文信息收集值", max_length=1000, default=u'', null=True, blank=True)
    option_id = models.BigIntegerField(u"信息收集ID", default=0, db_index=True)


class UserQuestionInfo(BaseModel):
    u"""测评用户的问卷题目信息，顺序打乱，选项打乱
    """
    people_id = models.BigIntegerField(u"测验用户ID", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
    project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
    question_info = models.TextField(u"题目信息", null=True, blank=True)
    en_question_info = models.TextField(u"英文题目信息", default=u'', null=True, blank=True)
    block_id = models.BigIntegerField(u"问卷块ID", default=0, db_index=True)


class UserQuestionAnswerInfo(BaseModel):
    u"""单选 单选填空 多选  多选填空 互斥题 滑块题"""
    people_id = models.BigIntegerField(u"测验用户ID", default=0, db_index=True)
    survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
    project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
    block_id = models.BigIntegerField(u"问卷块ID", default=0, db_index=True)
    role_type = models.PositiveSmallIntegerField(u"测评角色", default=PeopleSurveyRelation.ROLE_TYPE_NORMAL,
                                                 choices=PeopleSurveyRelation.ROLE_CHOICES, db_index=True)
    evaluated_people_id = models.BigIntegerField(u"被评价人员ID", db_index=True, default=0)
    question_id = models.BigIntegerField(u"测验题目ID", default=0, db_index=True)
    order_num = models.PositiveIntegerField(u"题目序号", default=0, db_index=True)
    answer_content = models.CharField(u"回答内容", max_length=256, null=True, blank=True)
    answer_id = models.BigIntegerField(u"回答选项ID", default=0, db_index=True)
    answer_score = models.FloatField(u"回答分值", default=0, db_index=True)
    # 互斥题 重分问题
    answer_index = models.BigIntegerField(u"回答索引", default=0, db_index=True)
    answer_time = models.PositiveIntegerField(u"回答时间(秒)", default=0, db_index=True)


# class UserQuestionAnswerNewInfo(BaseModel):
#     u"""单选 单选填空 多选  多选填空 互斥题 滑块题"""
#     people_id = models.BigIntegerField(u"测验用户ID", default=0, db_index=True)
#     survey_id = models.BigIntegerField(u"测验问卷ID", default=0, db_index=True)
#     project_id = models.BigIntegerField(u"测验项目ID", default=0, db_index=True)
#     people_survey_relation_id = models.BigIntegerField(u"测验结果ID", default=0, db_index=True)
#     # {"block_%s": {"question_id_%s": [{"question_id", "order_num", "answer_content", "answer_id", "answer_score", "answer_index", "answer_time"}]}}
#     # {"block_0": {"question_id_%s": [{"question_id", "order_num", "answer_content", "answer_id", "answer_score", "answer_index", "answer_time"}]}}
#     answer_info = models.TextField(u"回答信息", null=True, blank=True)
