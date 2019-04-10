# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from .models import BaseOrganization
from .serializers import BaseOrganizationSerializer

class OrganizationHelper(object):

    @classmethod
    def get_child_orgs(self, parent):

        result_data = []

        organizations = BaseOrganization.objects.filter_active(parent_id=parent)

        for organization in organizations:
            child_org_data = OrganizationHelper.get_child_orgs(organization.id)
            org_info = BaseOrganizationSerializer(instance=organization).data
            org_info["children"] = child_org_data
            result_data.append(org_info)

        return result_data

    @classmethod
    def get_tree_orgs(self, org):

        result_data={}

        organization = BaseOrganization.objects.get(id=org)
        result_data = BaseOrganizationSerializer(instance=org).data
        result_data["parent_id"] = 0
        result_data["children"] = OrganizationHelper.get_child_orgs(org)

        return result_data