# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from wduser.models import AuthUser, EnterpriseAccount, People, BaseOrganization
import json

class BaseOrganizationSerializer(serializers.ModelSerializer):
    """organization information serializer"""

    enterprise_id = serializers.IntegerField()

    class Meta:
        model = BaseOrganization
        fields = ('id', 'enterprise_id', 'parent_id', 'name')

class UserSerializer(serializers.ModelSerializer):
    """user serializer"""
    sequence_name = serializers.CharField(source='sequence.name', read_only=True)
    gender_name = serializers.CharField(source='gender.name', read_only=True)
    rank_name = serializers.CharField(source='rank.name', read_only=True)
    marriage_name = serializers.CharField(source='marriage.name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    enteprise = serializers.IntegerField(source='organization.enterprise_id', read_only=True)

    class Meta:
        model = AuthUser
        fields = ('id', 'nickname','role_type','phone','email','sequence',
                  'gender','rank','marriage','organization','enteprise',
                  'sequence_name','gender_name','rank_name','marriage_name',
                  'organization_name')