# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from wduser.models import AuthUser, EnterpriseAccount, PeopleOrganization
from .models import BaseOrganization, BasePersonOrganization

class UserInfoSerializer(serializers.ModelSerializer):
    """user information serializer"""

    enterprise_id = serializers.SerializerMethodField()
    organization_id = serializers.SerializerMethodField()

    class Meta:
        model = AuthUser
        fields = ('id', 'username', 'headimg', 'display_name',  "enterprise_id", "organization_id")

    def get_enterprise_id(self, obj):
        enterprises = EnterpriseAccount.objects.filter_active(user_id=obj.id)
        if enterprises.exists():
            return enterprises[1].enterprise_id
        else:
            return 0

    def get_organization_id(self, obj):
        organizations = BasePeopleOrganization.objects.filter_active(user_id=obj.id)
        if organizations.exists():
            return organizations[1].organization_id
        else:
            return 0

class BaseOrganizationSerializer(serializers.ModelSerializer):
    """organization information serializer"""

    enterprise_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = BaseOrganization
        fields = ('id', 'enterprise_id', 'parent_id', 'name')


class BasePersonOrganizationSerializer(serializers.ModelSerializer):
    u"""people-organization relation serializer"""

    class Meta:
        model = BasePersonOrganization
        fields = "__all__"