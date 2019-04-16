# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from rest_framework import serializers

from question.models import QuestionBank, QuestionFolder, QuestionFacet, Question, QuestionOption, \
    QuestionPassageRelation, QuestionPassage
from utils.serializers import WdTagListSerializer


class QuestionBankSerializer(WdTagListSerializer, serializers.ModelSerializer):

    folder_count = serializers.SerializerMethodField()

    class Meta:
        model = QuestionBank
        fields = ('id', 'name', 'en_name', 'desc', "en_desc", 'code', 'folder_count')

    def get_folder_count(self, obj):
        return QuestionFolder.objects.filter_active(question_bank_id=obj.id, parent_id=0).count()


class QuestionFolderSerializer(WdTagListSerializer, serializers.ModelSerializer):

    sub_folder_count = serializers.SerializerMethodField()
    facet_count = serializers.SerializerMethodField()

    class Meta:
        model = QuestionFolder
        fields = ('id', 'question_bank_id', 'name', "en_name", "en_desc", 'desc', 'code', 'parent_id', 'sub_folder_count', 'facet_count')

    def get_sub_folder_count(self, obj):
        if obj.parent_id == 0:
            return QuestionFolder.objects.filter_active(parent_id=obj.id).count()
        else:
            return 0

    def get_facet_count(self, obj):
        if obj.parent_id == 0:
            return 0
        else:
            return QuestionFacet.objects.filter_active(question_folder_id=obj.id).count()


class QuestionFacetSerializer(WdTagListSerializer, serializers.ModelSerializer):

    question_count = serializers.SerializerMethodField()
    question_bank_name = serializers.SerializerMethodField()
    question_folder_parent_id = serializers.SerializerMethodField()

    class Meta:
        model = QuestionFacet
        fields = ('id', 'question_bank_id', 'question_folder_id', 'default_question_type', 'default_options',
                  'name', "en_name", "en_desc", 'desc', 'code', 'weight', 'question_count', 'question_bank_name',
                  "facet_type", 'question_folder_parent_id')

    def get_question_count(self, obj):
        return Question.objects.filter_active(question_facet_id=obj.id).count()

    def get_question_bank_name(self, obj):
        return QuestionBank.objects.get(id=obj.question_bank_id).name

    def get_question_folder_parent_id(self, obj):
        return QuestionFolder.objects.get(id=obj.question_folder_id).parent_id


class QuestionBasicSerializer(serializers.ModelSerializer):

    class Meta:
        model = Question
        fields = ('id', 'question_bank_id', 'question_folder_id', 'question_facet_id', 'title',
                  'en_title', 'code', 'question_type', 'question_category', 'uniformity_question_id',
                  'use_count', 'average_score', 'standard_deviation')


class QuestionSerializer(WdTagListSerializer, serializers.ModelSerializer):

    facet_name = serializers.SerializerMethodField()
    use_count = serializers.SerializerMethodField()
    question_folder_parent_id = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ('id', 'question_bank_id', 'question_folder_id', 'question_facet_id', 'question_passage_id', 'title',
                  'en_title', 'code', 'question_type', 'question_category', 'uniformity_question_id',
                  'use_count', 'average_score', 'standard_deviation', 'facet_name', "question_folder_parent_id")

    def get_use_count(self, obj):
        u"""题目录入字体太小，需要调整"""
        try:
            a = int(obj.use_count)
            if a:
                return a
            else:
                return 0
        except:
            return 0

    def get_facet_name(self, obj):
        try:
            return QuestionFacet.objects.get(id=obj.question_facet_id).name
        except Exception, e:
            return ""

    def get_question_folder_parent_id(self, obj):
        return QuestionFolder.objects.get(id=obj.question_folder_id).parent_id


class QuestionListSerializer(QuestionSerializer):
    title = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = QuestionSerializer.Meta.fields

    def get_title(self, obj):
        try:
            return "%s: %s" %(obj.code[-3:], obj.title)
        except:
            return obj.title


class QuestionListDetailSerializer(QuestionSerializer):

    question_bank_name = serializers.SerializerMethodField()
    question_folder_name = serializers.SerializerMethodField()
    question_sub_folder_name = serializers.SerializerMethodField()
    question_facet_name = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = QuestionSerializer.Meta.fields + (
            'question_bank_name', 'question_folder_name', 'question_sub_folder_name', 'question_facet_name')

    def get_question_bank_name(self, obj):
        return QuestionBank.objects.get(id=obj.question_bank_id).name

    def get_question_sub_folder_name(self, obj):
        return QuestionFolder.objects.get(id=obj.question_folder_id).name

    def get_question_folder_name(self, obj):
        folder = QuestionFolder.objects.get(id=obj.question_folder_id)
        return QuestionFolder.objects.get(id=folder.parent_id).name

    def get_question_facet_name(self, obj):
        return QuestionFacet.objects.get(id=obj.question_facet_id).name


class QuestionDetailSerializer(QuestionSerializer):

    title = serializers.SerializerMethodField()
    passage = serializers.SerializerMethodField()
    en_passage = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    uniformity_question_info = serializers.SerializerMethodField()
    question_folder_parent_id = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = QuestionSerializer.Meta.fields + ("en_passage",
            'passage', "options", "uniformity_question_info", "question_folder_parent_id")

    def get_title(self, obj):
        from assessment.models import AssessProjectSurveyConfig
        request = self.context.get("request", None)
        is_test = self.context.get("is_test", False)
        if not is_test and (not request or request.GET.get("with_custom_config", None) != "1"):
            return obj.title
        if is_test:
            assess_id = self.context.get("assess_id", None)
            survey_id = self.context.get("survey_id", None)
        else:
            assess_id = request.GET.get("assess_id", 0)
            survey_id = request.GET.get("survey_id", 0)
        if not assess_id or not survey_id:
            return obj.title
        qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id,
            model_type=AssessProjectSurveyConfig.MODEL_TYPE_QUESTION,
            model_id=obj.id
        ).order_by("-id")
        if not qs.exists():
            return obj.title
        # @version: 20180725 @summary: 自定义题干设置，支持单选 单选填空 多选 多选填空 滑块，互斥题
        return qs[0].content

    def get_passage(self, obj):
        if obj.question_passage_id:
            return QuestionPassage.objects.get(id=obj.question_passage_id).passage
        else:
            # return None
            # 兼容老数据
            qp_qs = QuestionPassageRelation.objects.filter_active(question_id=obj.id)
            if not qp_qs.exists():
                return None
            passage_id = qp_qs[0].passage_id
            return QuestionPassage.objects.get(id=passage_id).passage

    def get_en_passage(self, obj):
        if obj.question_passage_id:
            return QuestionPassage.objects.get(id=obj.question_passage_id).en_passage
        else:
            # 兼容老数据
            qp_qs = QuestionPassageRelation.objects.filter_active(question_id=obj.id)
            if not qp_qs.exists():
                return None
            passage_id = qp_qs[0].passage_id
            return QuestionPassage.objects.get(id=passage_id).en_passage

    # def get_en_passage(self, obj):
    #     qp_qs = QuestionPassageRelation.objects.filter_active(question_id=obj.id)
    #     if not qp_qs.exists():
    #         return None
    #     passage_id = qp_qs[0].passage_id
    #     return QuestionPassage.objects.get(id=passage_id).en_passage

    def get_options(self, obj):
        from question.question_utils import QuestionUtils
        return QuestionUtils(obj.id).get_options(self.context)

    def get_uniformity_question_info(self, obj):
        if obj.question_category != Question.CATEGORY_UNIFORMITY:
            return {}
        elif obj.uniformity_question_id == 0:
            return {}
        else:
            uniformity_question = Question.objects.get(id=obj.uniformity_question_id)
            return {
                "id": uniformity_question.id,
                "title": uniformity_question.title,
                "question_type": uniformity_question.question_type
            }

    def get_question_folder_parent_id(self, obj):
        return QuestionFolder.objects.get(id=obj.question_folder_id).parent_id


class QuestionOptionSerializer(serializers.ModelSerializer):
    u"""
    @version: 2018/7/1
    @summary：目前仅GET使用
    """

    content = serializers.SerializerMethodField()
    question_bank_id = serializers.SerializerMethodField()
    question_facet_id = serializers.SerializerMethodField()
    question_folder_id = serializers.SerializerMethodField()
    parent_folder_id = serializers.SerializerMethodField()
    option_type = serializers.SerializerMethodField()

    class Meta:
        model = QuestionOption
        fields = (
                    'id',
                    'question_id',
                    'parent_id',
                    'content',
                    'en_content',
                    'order_number',
                    'is_blank',
                    'score',
                    "question_bank_id",
                    "question_facet_id",
                    "question_folder_id",
                    "parent_folder_id",
                    "option_type",
                  )

    def get_content(self, obj):
        from assessment.models import AssessProjectSurveyConfig
        request = self.context.get("request", None)
        is_test = self.context.get("is_test", False)
        if not is_test and (not request or request.GET.get("with_custom_config", None) != "1"):
            return obj.content
        if is_test:
            assess_id = self.context.get("assess_id", None)
            survey_id = self.context.get("survey_id", None)
        else:
            assess_id = request.GET.get("assess_id", 0)
            survey_id = request.GET.get("survey_id", 0)
        if not assess_id or not survey_id:
            return obj.content
        qs = AssessProjectSurveyConfig.objects.filter_active(
            assess_id=assess_id, survey_id=survey_id, model_type=AssessProjectSurveyConfig.MODEL_TYPE_OPTION,
            model_id=obj.id
        ).order_by("-id")
        if not qs.exists():
            return obj.content
        return qs[0].content

    def get_question_bank_id(self, obj):
        qs = Question.objects.filter_active(id=obj.question_id)
        if qs.exists():
            return qs[0].question_bank_id
        return None

    def get_question_folder_id(self, obj):
        qs = Question.objects.filter_active(id=obj.question_id)
        if qs.exists():
            return qs[0].question_folder_id
        return None

    def get_question_facet_id(self, obj):
        qs = Question.objects.filter_active(id=obj.question_id)
        if qs.exists():
            return qs[0].question_facet_id
        return None

    def get_parent_folder_id(self, obj):
        qs = Question.objects.filter_active(id=obj.question_id)
        if qs.exists():
            qs = QuestionFolder.objects.filter_active(id=qs[0].question_folder_id)
            if qs.exists():
                return qs[0].parent_id
        return None

    def get_option_type(self, obj):
        qs = Question.objects.filter_active(id=obj.question_id)
        if qs.exists():
            return qs[0].question_type
        return None


class QuestionOptionListSerializer(serializers.ModelSerializer):

    class Meta:
        model = QuestionOption
        fields = ('options', )


class QuestionPassageSerializer(serializers.ModelSerializer):

    use_count = serializers.SerializerMethodField()

    class Meta:
        model = QuestionPassage
        fields = ("id", 'question_facet_id', 'passage', 'en_passage', 'use_count')

    def get_use_count(self, obj):
        try:
            # 材料题使用次数，材料下用的最多的一题的次数
            count = int(max(Question.objects.filter_active(question_passage_id=obj.id).values_list('use_count', flat=True)))
            return count
        except:
            return 0
