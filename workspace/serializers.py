# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from wduser.models import AuthUser, EnterpriseAccount, PeopleOrganization, People
from workspace.models import BaseOrganization, BaseUserOrganization
import json

class UserInfoSerializer(serializers.ModelSerializer):
    """user information serializer"""

    enterprise_id = serializers.SerializerMethodField()
    organization_id = serializers.SerializerMethodField()

    class Meta:
        model = AuthUser
        fields = ('id', 'username', 'headimg', 'display_name',  "enterprise_id", "organization_id")

    def get_enterprise_id(self, obj):
        enterprise = EnterpriseAccount.objects.filter_active(user_id=obj.id).first()
        if enterprise:
            return enterprise.enterprise_id
        else:
            return 0

    def get_organization_id(self, obj):
        organization = BasePeopleOrganization.objects.filter_active(user_id=obj.id).first()
        if organization:
            return organization.organization_id
        else:
            return 0

class BaseOrganizationSerializer(serializers.ModelSerializer):
    """organization information serializer"""

    enterprise_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = BaseOrganization
        fields = ('id', 'enterprise_id', 'parent_id', 'name')

class PeopleSerializer(serializers.ModelSerializer):
    """People Serializer"""

    organization_id = serializers.SerializerMethodField()
    infos = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    enterprise_id = serializers.SerializerMethodField()
    
    class Meta:
        model = People
        fields = ('id', 'username', 'user_id', 'phone', 'email', 
                  'infos','account_name','organization_id','enterprise_id')

    def get_infos(self, obj):
        '''get profile information'''
        if obj.more_info:
            return json.loads(obj.more_info)
        else:
            return []

    def get_organization_id(self, obj):
        '''get organiztion id'''
        userorganization = BaseUserOrganization.objects.filter_active(id=obj.user_id).first()
        if userorganization:
            return userorganization.organization_id
        else:
            return None

    def get_account_name(self, obj):
        '''get account name'''
        user = AuthUser.objects.filter_active(id=obj.user_id).first()
        if user:
            return user.account_name
        else:
            return None

    def get_enterprise_id(self, obj):
        '''get enterprise id'''
        userorganization = BaseUserOrganization.objects.filter_active(id=obj.user_id).first()
        if userorganization:
            return userorganization.enterprise_id
        else:
            return None