from wduser.models import AuthUser, EnterpriseAccount, PeopleOrganization
from .models import BaseOrganization, BasePeopleOrganization
from rest_framework import serializers

class UserInfoSerializer(serializers.ModelSerializer):

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

        class Meta:
            model = BaseOrganization
            fields = "__all__"