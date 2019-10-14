# -*- coding:utf-8 -*-
from __future__ import unicode_literals
import datetime
from rest_framework import serializers
from sales.serializers import Product_SpecificationSerializer
from sales.models import Product_Specification,Schema
from assessment.models import AssessProject,AssessSurveyRelation,AssessJoinedOrganization
from front.models import PeopleSurveyRelation
from useroperate import models
from workspace.models import AssessProgress

class Product_AssessDetailSerializer(serializers.Serializer):

    # key_spec = serializers.SerializerMethodField

    class Meta:
        model = Product_Specification
        fields = '__all__'

    # def get_key_spec(self, obj):
    #     attrlist =  Schema.objects.filter(category_id=obj.category_id).values()
    #     attrvalues={}
    #     for attr in attrlist:
    #         attrvalues[attr]=obj.getattr(attr)
    #     return attrvalues

class TrialAssessListSerializer(serializers.ModelSerializer):

    organizations = serializers.SerializerMethodField()
    joined = serializers.SerializerMethodField()
    survey_id = serializers.SerializerMethodField()
    progress = serializers.SlugRelatedField(
        source='assess_progress',
        slug_field='status',
        read_only=True,    
    )
    eoisurveys = [132,147,172]

    class Meta:
        model = AssessProject
        fields = ('id','name','begin_time','end_time','organizations','joined','has_distributed','progress','survey_id','distribute_type')
    
    def get_organizations(self, obj):
        organizations = AssessJoinedOrganization.objects.filter(assess_id=obj.id,organization__parent_id__gt=0).values_list('organization__name', flat=True)
        return ','.join(str(n) for n in organizations)

    def get_joined(self, obj):
        surveys = AssessSurveyRelation.objects.filter(assess_id=obj.id,is_active=True).values_list('survey_id', flat=True)
        psurvey_id=147
        for survey in surveys:
            if survey in self.eoisurveys:
                psurvey_id = survey
                break
        return PeopleSurveyRelation.objects.filter(project_id=obj.id,is_active=True,survey_id=psurvey_id).count()
    
    def get_survey_id(self,obj):
        surveys = AssessSurveyRelation.objects.filter(assess_id=obj.id,is_active=True).values_list('survey_id', flat=True)
        for survey in surveys:
            if survey in self.eoisurveys:
                return survey
        return 147
    
    # def get_progress(self,obj):        
    #     progress = AssessProgress.objects.filter(assess_id=obj.id).first()
    #     if not progress:
    #         return 1
    #     else:
    #         return progress.status
          

class TrialAssessDetailSerializer(serializers.ModelSerializer):

    joined = serializers.SerializerMethodField()
    complete = serializers.SerializerMethodField()
    total_days = serializers.SerializerMethodField()
    remain_days = serializers.SerializerMethodField()

    class Meta:
        model = AssessProject
        fields = ('id','name','begin_time','end_time','joined','complete','total_days','remain_days')

    def get_joined(self, obj):
        return PeopleSurveyRelation.objects.filter(project_id=obj.id,is_active=True).count()

    def get_complete(self, obj):
        return PeopleSurveyRelation.objects.filter(project_id=obj.id,is_active=True,status=20).count()

    def get_total_days(self, obj):
        return (obj.end_time-obj.begin_time).days

    def get_remain_days(self, obj):
        return min(max(0,(obj.end_time-datetime.datetime.now()).days),(obj.end_time-obj.begin_time).days)

class MessageSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Message
        fields = '__all__'

class MessagePushSerializer(serializers.ModelSerializer):

    content = serializers.SerializerMethodField()

    class Meta:
        model = models.MessagePush
        fields = '__all__'

    def get_content(self, obj):
        message = models.Message.objects.get(id=obj.message_id)
        return message.content