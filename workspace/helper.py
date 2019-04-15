# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from wduser.models import BaseOrganization
from workspace.serializers import BaseOrganizationSerializer

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

        organization = BaseOrganization.objects.filter_active(id=org).first()
        if organization is None:
            return result_data
        result_data = BaseOrganizationSerializer(instance=organization).data
        result_data["parent_id"] = 0
        result_data["children"] = OrganizationHelper.get_child_orgs(org)

        return result_data

    @classmethod
    def get_child_ids(self, parent):

        result_data = []

        organizations = BaseOrganization.objects.filter_active(parent_id=parent)
        
        for organization in organizations:
            result_data.append(organization.id)
            child_org_data = OrganizationHelper.get_child_ids(organization.id)
            result_data +=child_org_data

        return result_data