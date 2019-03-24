# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from assessment.models import AssessProjectSurveyConfig
from question.models import Question, QuestionOption
from question.serializers import QuestionOptionSerializer
from utils.response import ErrorCode


class QuestionUtils(object):

    def __init__(self, question):
        if type(question) == int or type(question) == long:
            self.question = Question.objects.get(id=question)
        else:
            self.question = question
        self.question_id = self.question.id

    def set_choice_question(self, **data):
        u"""单选，多选，单选填空，多选填空"""
        options = data.get("options", None)
        max_choose = data.get("max_choose", None)
        min_choose = data.get("min_choose", 0)
        if options is None:
            return ErrorCode.INVALID_INPUT
        exits_ids = []
        for index, option in enumerate(options):
            id = option.get("id", 0)
            if int(id) == 0:
                option = QuestionOption.objects.create(
                    question_id=self.question_id,
                    content=option.get("content", ""),
                    en_content=option.get("en_content", ""),
                    order_number=index,
                    score=option.get("score", 0),
                    is_blank=int(option.get("is_blank", 0))
                )
                exits_ids.append(option.id)
            else:
                exits_ids.append(int(id))
                QuestionOption.objects.filter(id=id).update(
                    content=option.get("content", ""),
                    en_content=option.get("en_content", ""),
                    order_number=index,
                    score=option.get("score", 0),
                    is_blank=int(option.get("is_blank", 0))
                )
        QuestionOption.objects.filter_active(question_id=self.question_id).exclude(
            id__in=exits_ids).update(is_active=False)
        if max_choose is not None:
            Question.objects.filter(id=self.question_id).update(config_info=json.dumps({
                "max_choose": int(max_choose), "min_choose": int(min_choose)
            }))
        return ErrorCode.SUCCESS

    def get_choice_question(self, context=None):
        u"""获取单选 多选 单选填空 多选填空 的内容"""
        options = QuestionOption.objects.filter_active(
            question_id=self.question_id).order_by('order_number')
        option_data = QuestionOptionSerializer(instance=options, many=True, context=context).data
        config_info = {'max_choose': None, 'min_choose': 0}
        if self.question.question_type in [Question.QUESTION_TYPE_MULTI, Question.QUESTION_TYPE_MULTI_FILLIN]:
            if self.question.config_info:
                config_info['max_choose'] = json.loads(self.question.config_info).get("max_choose", None)
                config_info['min_choose'] = json.loads(self.question.config_info).get("min_choose", 0)
        return {'option_data': option_data, 'config_info': config_info}

    def set_slide_question(self, **data):
        u"""滑块题"""
        max_value = data.get('max_value', None)
        min_value = data.get('min_value', None)
        step_value = data.get('step_value', None)
        default_value = data.get('default_value', None)
        max_desc = data.get('max_desc', None)
        max_desc_en = data.get('max_desc_en', None)
        min_desc = data.get('min_desc', None)
        min_desc_en = data.get('min_desc_en', None)
        default_desc = data.get('default_desc', "")
        if max_value is None or min_value is None or not step_value or \
                not max_desc or not min_desc:
            return ErrorCode.INVALID_INPUT
        Question.objects.filter(id=self.question_id).update(config_info=json.dumps({
            "max_value": max_value,
            "min_value": min_value,
            "step_value": step_value,
            "default_value": default_value,
            "max_desc": max_desc,
            "max_desc_en": max_desc_en,
            "min_desc": min_desc,
            "min_desc_en": min_desc_en,
            "default_desc": default_desc
        }))
        return ErrorCode.SUCCESS

    def get_slide_question(self, context=None):
        u"""
        @version: 20180725 @summary:支持滑块题配置，在项目分发时修改
        """
        if not self.question.config_info:
            data = {}
        else:
            try:
                data = json.loads(self.question.config_info)
            except:
                data = {}
        config_info = {
            "max_value": data.get("max_value", 0),
            "min_value": data.get("min_value", 0),
            "step_value": data.get("step_value", 0),
            "default_value": data.get("default_value", 0),
            "max_desc": data.get("max_desc", ""),
            "min_desc": data.get("min_desc", ""),
            "max_desc_en": data.get("max_desc_en", ""),
            "min_desc_en": data.get("min_desc_en", ""),
            "en_max_desc": data.get("max_desc_en", ""),
            "en_min_desc": data.get("min_desc_en", ""),
            "default_desc": data.get("default_desc", "")
        }

        request = context.get("request", None)
        is_test = context.get("is_test", False)
        if not is_test and (not request or request.GET.get("with_custom_config", None) != "1"):
            return config_info
        if is_test:
            assess_id = context.get("assess_id", None)
            survey_id = context.get("survey_id", None)
        else:
            assess_id = request.GET.get("assess_id", None)
            survey_id = request.GET.get("survey_id", None)
        if not assess_id or not survey_id:
            return config_info
        test_config_qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id,
            survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_SLIDE_OPTION,
            model_id=self.question_id
        )
        if not test_config_qs.exists():
            return config_info
        config_content = test_config_qs[0].content
        if not config_content:
            return config_info
        test_config = json.loads(config_content)
        for key in config_info:
            if key in test_config:
                config_info[key] = test_config[key]
        return config_info

    def set_nine_slide_question(self, **data):
        u"""九点量表题"""
        u"""滑块题"""
        max_value = data.get('max_value', None)
        min_value = data.get('min_value', None)
        step_value = data.get('step_value', None)
        default_value = data.get('default_value', None)
        max_desc = data.get('max_desc', None)
        max_desc_en = data.get('max_desc_en', None)
        min_desc = data.get('min_desc', None)
        min_desc_en = data.get('min_desc_en', None)
        default_desc = data.get('default_desc', "")
        if max_value is None or min_value is None or not step_value or \
                not max_desc or not min_desc:
            return ErrorCode.INVALID_INPUT
        Question.objects.filter(id=self.question_id).update(config_info=json.dumps({
            "max_value": max_value,
            "min_value": min_value,
            "step_value": step_value,
            "default_value": default_value,
            "max_desc": max_desc,
            "max_desc_en": max_desc_en,
            "min_desc": min_desc,
            "min_desc_en": min_desc_en,
            "default_desc": default_desc
        }))
        return ErrorCode.SUCCESS

    def get_nine_slide_question(self, context=None):
        u"""
              @version: 20180725 @summary:支持滑块题配置，在项目分发时修改
              """
        if not self.question.config_info:
            data = {}
        else:
            try:
                data = json.loads(self.question.config_info)
            except:
                data = {}
        config_info = {
            "max_value": data.get("max_value", 0),
            "min_value": data.get("min_value", 0),
            "step_value": data.get("step_value", 0),
            "default_value": data.get("default_value", 0),
            "max_desc": data.get("max_desc", ""),
            "min_desc": data.get("min_desc", ""),
            "max_desc_en": data.get("max_desc_en", ""),
            "min_desc_en": data.get("min_desc_en", ""),
            "en_max_desc": data.get("max_desc_en", ""),
            "en_min_desc": data.get("min_desc_en", ""),
            "default_desc": data.get("default_desc", "")
        }

        request = context.get("request", None)
        is_test = context.get("is_test", False)
        if not is_test and (not request or request.GET.get("with_custom_config", None) != "1"):
            return config_info
        if is_test:
            assess_id = context.get("assess_id", None)
            survey_id = context.get("survey_id", None)
        else:
            assess_id = request.GET.get("assess_id", None)
            survey_id = request.GET.get("survey_id", None)
        if not assess_id or not survey_id:
            return config_info
        test_config_qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id,
            survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_SLIDE_OPTION,
            model_id=self.question_id
        )
        if not test_config_qs.exists():
            return config_info
        config_content = test_config_qs[0].content
        if not config_content:
            return config_info
        test_config = json.loads(config_content)
        for key in config_info:
            if key in test_config:
                config_info[key] = test_config[key]
        return config_info

    def set_mutex_question(self, **data):
        u"""互斥题
        {
        options:[{}],
        option_titles:[]
        }
        """
        options = data.get("options", None)
        option_titles = data.get("option_titles", Question.DEFAULT_MUTEX_TITLE)
        en_option_titles = data.get("en_option_titles", Question.EN_DEFAULT_MUTEX_TITLE)
        if options is None or option_titles is None:
            return ErrorCode.INVALID_INPUT
        exits_ids = []
        for index, option in enumerate(options):
            id = option.get("id", 0)
            scores = option.get("scores", 0)
            if len(scores) != len(option_titles):
                return ErrorCode.INVALID_INPUT
            if int(id) == 0:
                option_obj = QuestionOption.objects.create(
                    question_id=self.question_id,
                    content=option.get("content", ""),
                    en_content=option.get("en_content", ""),
                    order_number=index,
                )
                exits_ids.append(option_obj.id)
                for cindex, score in enumerate(scores):
                    QuestionOption.objects.create(
                        question_id=option_obj.question_id,
                        parent_id=option_obj.id,
                        order_number=cindex,
                        content=option_titles[cindex],
                        en_content=en_option_titles[cindex],
                        score=score
                    )
            else:
                QuestionOption.objects.filter(id=id).update(
                    content=option.get("content", ""),
                    en_content=option.get("en_content", ""),
                    order_number=index,
                )
                exits_ids.append(int(id))
                cexits_ids = []
                for cindex, score in enumerate(scores):
                    child_option, is_created = QuestionOption.objects.get_or_create(
                        question_id=self.question_id,
                        parent_id=id,
                        order_number=cindex,
                    )
                    cexits_ids.append(child_option.id)
                    child_option.content = option_titles[cindex],
                    child_option.score = score
                    child_option.save()
                QuestionOption.objects.filter_active(parent_id=id).exclude(
                    id__in=cexits_ids).update(is_active=False)
        QuestionOption.objects.filter_active(question_id=self.question_id, parent_id=0).exclude(
            id__in=exits_ids
        ).update(is_active=False)
        self.question.config_info = json.dumps({"option_titles": option_titles, "en_option_titles": en_option_titles})
        self.question.save()
        return ErrorCode.SUCCESS

    def get_mutex_question(self, context=None):
        u"""
        @version: 20180725 @summary:支持互斥题选项在项目中设置
        """
        options = QuestionOption.objects.filter_active(
            question_id=self.question_id, parent_id=0).order_by('order_number')
        option_datas = QuestionOptionSerializer(
            instance=options, many=True, context=context).data
        for option_data in option_datas:
            scores = list(QuestionOption.objects.filter_active(
                parent_id=option_data["id"]).order_by('order_number').values_list("score", flat=True))
            option_data['scores'] = scores
        if not self.question.config_info:
            options_titles = Question.DEFAULT_MUTEX_TITLE
            en_options_titles = Question.EN_DEFAULT_MUTEX_TITLE
        else:
            config_data = json.loads(self.question.config_info)
            if type(config_data) != dict:
                options_titles = Question.DEFAULT_MUTEX_TITLE
                en_options_titles = Question.EN_DEFAULT_MUTEX_TITLE
            else:
                options_titles = config_data.get("option_titles", Question.DEFAULT_MUTEX_TITLE)
                en_options_titles = config_data.get("en_option_titles", Question.EN_DEFAULT_MUTEX_TITLE)
        data = {
            'options_titles': options_titles,
            'en_options_titles': en_options_titles,
            'options': option_datas
        }
        return data

    def create_option(self, **data):
        # self.question = Question.objects.get(id=self.question_id)
        rst_code = ErrorCode.SUCCESS
        if self.question.question_type in [
            Question.QUESTION_TYPE_MULTI,
            Question.QUESTION_TYPE_SINGLE,
            Question.QUESTION_TYPE_MULTI_FILLIN,
            Question.QUESTION_TYPE_SINGLE_FILLIN
        ]:
            # 单选 多选 单选填空 多选填空
            rst_code = self.set_choice_question(**data)
        elif self.question.question_type == Question.QUESTION_TYPE_SLIDE:
            # 滑块题
            rst_code = self.set_slide_question(**data)
        elif self.question.question_type == Question.QUESTION_TYPE_NINE_SLIDE:
            # 9点题
            rst_code = self.set_nine_slide_question(**data)
        elif self.question.question_type == Question.QUESTION_TYPE_MUTEXT:
            # 互斥题
            rst_code = self.set_mutex_question(**data)
        elif self.question.question_type == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
            # 迫选排序题
            rst_code = self.set_mutex_order_question(**data)
        return rst_code

    def get_options(self, context=None):
        # self.question = Question.objects.get(id=self.question_id)
        data = {}
        if self.question.question_type in [
            Question.QUESTION_TYPE_MULTI,
            Question.QUESTION_TYPE_SINGLE,
            Question.QUESTION_TYPE_MULTI_FILLIN,
            Question.QUESTION_TYPE_SINGLE_FILLIN
        ]:
            # 单选 多选 单选填空 多选填空
            data = self.get_choice_question(context)
        elif self.question.question_type == Question.QUESTION_TYPE_SLIDE:
            # 滑块题
            data = self.get_slide_question(context)
        elif self.question.question_type == Question.QUESTION_TYPE_NINE_SLIDE:
            # 滑块题
            data = self.get_nine_slide_question(context)
        elif self.question.question_type == Question.QUESTION_TYPE_MUTEXT:
            # 互斥题
            data = self.get_mutex_question(context)
        elif self.question.question_type == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
            # 迫选排序
            data = self.get_mutex_order_question(context)
        return data

    def set_mutex_order_question(self, **data):
        u"""迫选排序题"""
        options = data.get("options", None)
        option_titles = data.get("option_titles", Question.DEFAULT_MUTEX_ORDER_TITLE)   # 结果项
        en_option_titles = data.get("en_option_titles", Question.EN_DEFAULT_MUTEX_ORDER_TITLE)
        scores = data.get("scores", Question.DEFAULT_SCORES)
        if options is None or option_titles is None or len(options) != 5 or len(scores) != 5:
            return ErrorCode.QUESTION_OPTION_NUMBER_ERROR
        exits_ids = []
        for index, option in enumerate(options):
            id = option.get("id", 0)
            # 新建选项
            if int(id) == 0:
                option_obj = QuestionOption.objects.create(
                    question_id=self.question_id,
                    content=option.get("content", ""),
                    en_content=option.get("en_content", ""),
                    order_number=index,
                )
                exits_ids.append(option_obj.id)
            else:
                QuestionOption.objects.filter(id=id).update(
                    content=option.get("content", ""),
                    en_content=option.get("en_content", ""),
                    order_number=index,
                )
                exits_ids.append(int(id))
        QuestionOption.objects.filter_active(question_id=self.question_id, parent_id=0).exclude(
            id__in=exits_ids
        ).update(is_active=False)
        self.question.config_info = json.dumps(
            {
                "option_titles": option_titles,
                "en_option_titles": en_option_titles,
                "scores": scores
            }
        )
        self.question.save()
        return ErrorCode.SUCCESS

    def get_mutex_order_question(self, context=None):
        options = QuestionOption.objects.filter_active(
            question_id=self.question_id, parent_id=0).order_by('order_number')
        option_datas = QuestionOptionSerializer(
            instance=options, many=True, context=context).data
        if not self.question.config_info:
            options_titles = Question.DEFAULT_MUTEX_ORDER_TITLE
            en_options_titles = Question.EN_DEFAULT_MUTEX_ORDER_TITLE
            scores = Question.DEFAULT_SCORES
        else:
            config_data = json.loads(self.question.config_info)
            if type(config_data) != dict:
                options_titles = Question.DEFAULT_MUTEX_ORDER_TITLE
                en_options_titles = Question.EN_DEFAULT_MUTEX_ORDER_TITLE
                scores = Question.DEFAULT_SCORES
            else:
                options_titles = config_data.get("option_titles", Question.DEFAULT_MUTEX_ORDER_TITLE)
                en_options_titles = config_data.get("en_option_titles", Question.EN_DEFAULT_MUTEX_ORDER_TITLE)
                scores = config_data.get("scores", Question.DEFAULT_SCORES)
        data = {
            'options_titles': options_titles,
            'en_options_titles': en_options_titles,
            'options': option_datas,  # 10.7 预览出没有选项
            # 'option_data': option_datas,
            "scores": scores
        }
        return data

