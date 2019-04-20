# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from wduser.models import BaseOrganization
from workspace.serializers import BaseOrganizationSerializer
from WeiDuAdmin.settings import BASE_DIR
import os, pandas,numpy

def write_file(folder, file_data, file_name, assess_id,suffix):
    download_path = os.path.join(BASE_DIR, "download")
    assess_path = os.path.join(download_path, folder)        
    file_path = os.path.join(assess_path, assess_id, suffix)
    if not os.path.exists(file_path):
        os.makedirs(file_path)
    file_full_path = os.path.join(file_path, file_name)
    f = open(file_full_path, "wb+")
    if file_data.multiple_chunks():
        for chunk in file_data.chunks():
            f.write(chunk)
    else:
        f.write(file_data)
    f.close()
    return file_full_path

def read_file(filepath,targetcols,mustcols,keycols,codedict):
    data = pandas.read_csv(filepath,encoding='gbk')
    #check header integration
    if data.columns.values!=targetcols:
        return False
    #check mustinput data
    data['indice'] = data.index+1
    for col in mustcols:
        nulldata = data[data[col].isnull()]['indice'].tolist(0)
        if not nulldata:
            return False
    #check duplicated key value(skip empty)
    for col in keycols:
        duplicated = data[data[col].notnull() & data[col].duplicated(keep=False)]['indice'].tolist(0)
        if not duplicated:
            return False
    #dict fields validation(skip empty)
    for key in codedict:
        invalid = data[data[key].notnull() & ~data.key.str.contains('|'.join(codedict[key]))]['indice'].tolist(0)
        if not invalid:
            return False    
    return data

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