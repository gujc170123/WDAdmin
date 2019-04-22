# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from wduser.models import BaseOrganization
from workspace.serializers import BaseOrganizationSerializer
from WeiDuAdmin.settings import BASE_DIR
import os, pandas,numpy,time

def write_file(folder, file_data, file_name, assess_id,suffix):
    download_path = os.path.join(BASE_DIR, "download")
    assess_path = os.path.join(download_path, folder)        
    file_path = os.path.join(assess_path, assess_id, suffix)
    if not os.path.exists(file_path):
        os.makedirs(file_path)
    file_full_path = os.path.join(file_path, file_name)
    f = open(file_full_path, "wb+")
    for chunk in file_data.chunks():
        f.write(chunk)
    f.close()
    return file_full_path

def read_file(filepath,targetcols,typedict,mustcolsset,mustcols,keycols,codedict):
    data = pandas.read_csv(filepath,encoding='utf-8',dtype = typedict)
    #check header integration
    if list(data.columns.values)!=targetcols:
        return False,[]
    data['indice'] = data.index+1

    #check mustinput data    
    for col in mustcols:
        nulldata = data[data[col].isnull()]['indice'].tolist()
        if len(nulldata):
            return False,[]
    nullset = set(data['indice'].tolist())
    for col in mustcolsset:
        nulldata = data[data[col].isnull()]['indice'].tolist()
        nullset = set(nulldata) & nullset
    if nullset!=set():
        return False,[]
    #check duplicated key value(skip empty)
    for col in keycols:
        duplicated = data[data[col].notnull() & data[col].duplicated(keep=False)]['indice'].tolist()
        if len(duplicated):
            return False,[]
    #dict fields validation(skip empty)
    for key in codedict:
        if data[key].isnull().sum() == len(data[key]):
            continue
        invalid = data[data[key].notnull() & ~data[key].str.contains('|'.join(codedict[key]), na=False)]['indice'].tolist()
        if len(invalid):
            return False,[]
    return True,data

def is_valid_date(str):
  try:
    time.strptime(str, "%Y-%m-%d")
    return True
  except:
    return False

def convertna2none(obj):
    if obj:
        if pandas.isnull(obj):
            return None
        else:
            return obj

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