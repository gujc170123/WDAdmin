# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from wduser.models import AuthUser, EnterpriseAccount, People, BaseOrganization,BaseOrganizationPaths
from assessment.models import AssessProject
from survey.models import Survey
import json
from collections import OrderedDict

class ChoicesField(serializers.Field):
    """Custom ChoiceField serializer field."""

    def __init__(self, choices, **kwargs):
        """init."""
        self._choices = OrderedDict(choices)
        super(ChoicesField, self).__init__(**kwargs)

    def to_representation(self, obj):
        """Used while retrieving value for the field."""
        return self._choices[obj]

    def to_internal_value(self, data):
        """Used while storing value for the field."""
        for i in self._choices:
            if self._choices[i] == data:
                return i
        raise serializers.ValidationError("Acceptable values are {0}.".format(list(self._choices.values()))) 

class BaseOrganizationSerializer(serializers.ModelSerializer):
    """organization information serializer"""

    enterprise_id = serializers.IntegerField()

    class Meta:
        model = BaseOrganization
        fields = ('id', 'enterprise_id', 'parent_id', 'name')

class UserSerializer(serializers.ModelSerializer):
    """user serializer"""
    sequence_name = serializers.CharField(source='sequence.value', read_only=True)
    gender_name = serializers.CharField(source='gender.value', read_only=True)
    rank_name = serializers.CharField(source='rank.value', read_only=True)
    marriage_name = serializers.CharField(source='marriage.value', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    age_name = serializers.CharField(source='age.value', read_only=True)
    seniority_name = serializers.CharField(source='seniority.value', read_only=True)
    politics_name = serializers.CharField(source='politics.value', read_only=True)
    education_name = serializers.CharField(source='education.value', read_only=True)
    enteprise = serializers.IntegerField(source='organization.enterprise_id', read_only=True)

    class Meta:
        model = AuthUser
        fields = ('id', 'nickname','role_type','phone','email','sequence',
                  'gender','rank','marriage','organization','enteprise',
                  'sequence_name','gender_name','rank_name','marriage_name',
                  'organization_name','age_name','seniority_name','account_name',
                  'politics_name','education_name')

class UserDetailSerializer(serializers.ModelSerializer):
    """user serializer"""
    sequence_name = serializers.CharField(source='sequence.value', read_only=True)
    gender_name = serializers.CharField(source='gender.value', read_only=True)
    rank_name = serializers.CharField(source='rank.value', read_only=True)
    marriage_name = serializers.CharField(source='marriage.value', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    age_name = serializers.CharField(source='age.value', read_only=True)
    seniority_name = serializers.CharField(source='seniority.value', read_only=True)
    politics_name = serializers.CharField(source='politics.value', read_only=True)
    education_name = serializers.CharField(source='education.value', read_only=True)    
    enteprise = serializers.IntegerField(source='organization.enterprise_id', read_only=True)
    fullorg = serializers.SerializerMethodField()

    class Meta:
        model = AuthUser
        fields = ('id', 'nickname','role_type','phone','email','sequence',
                  'gender','rank','marriage','organization','enteprise',
                  'sequence_name','gender_name','rank_name','marriage_name',
                  'organization_name','age_name','seniority_name','account_name',
                  'fullorg','politics_name','education_name')

    def get_fullorg(self, obj):        
        return BaseOrganizationPaths.objects.filter(child_id=obj.organization).order_by('depth').values_list('parent_id',flat=True)        

class AssessSerializer(serializers.ModelSerializer):
    '''Assessment Serializer'''
    distribute_type = ChoicesField(choices=AssessProject.DISTRIBUTE_CHOICES)
    assess_type =  ChoicesField(choices=AssessProject.TYPE_CHOICES)
    finish_choices =  ChoicesField(choices=AssessProject.FINISH_CHOICES)

    class Meta:
        model = AssessProject
        fields = ('id', 'name', 'en_name', 'enterprise_id', 'begin_time', 'end_time', 'advert_url', 'assess_type',
                  'project_status', 'finish_choices', 'finish_redirect', 'finish_txt', 'assess_logo', 'org_infos',
                  "user_count", "distribute_type", "has_distributed", 'is_answer_survey_by_order', 'has_survey_random',
                  'survey_random_number', 'show_people_info')

class AssessListSerializer(serializers.ModelSerializer):
    '''Assessment List Serializer'''

    class Meta:
        model = AssessProject
        fields = ('id', 'name', 'en_name', 'begin_time', 'end_time', 'project_status')                  

class SurveyListSerializer(serializers.ModelSerializer):
    '''Assessment List Serializer'''

    class Meta:
        model = Survey
        fields = ('id', 'title')   