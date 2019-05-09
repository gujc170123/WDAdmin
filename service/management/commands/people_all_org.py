# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.core.management import BaseCommand
from django.db import transaction

from utils.logger import info_logger, err_logger
from wduser.models import AuthUser, People, PeopleOrganization, Organization


def people_all_org(auth_obj, num):
    u"""处理原来的项目里面的人的组织"""
    user_id = auth_obj.id
    try:
        if int(user_id) % 100 == 0:
            print("%s of %s" % (user_id, num))
        peo_obj = People.objects.get(user_id=user_id)
    except:
        return None
    old_peo_org_qs = PeopleOrganization.objects.filter_active(people_id=peo_obj.id).values_list('org_code', flat=True)
    old_codes = list(old_peo_org_qs)
    if not old_peo_org_qs.exists():
        return None
    old_org_qs = Organization.objects.filter_active(identification_code__in=old_peo_org_qs)
    # 对每个已经加入的组织
    for org_obj in old_org_qs:
        if org_obj.parent_id == 0:
            continue
        else:
            while True:
                # 循环创建至父id=0的时候
                if org_obj.parent_id == 0:
                    break
                try:
                    may_new_obj = Organization.objects.get(id=org_obj.parent_id, assess_id=org_obj.assess_id)
                except:
                    err_logger.error('org_get_ERROR id %s assess_id %s' % (org_obj.parent_id, org_obj.assess_id))
                    break
                if may_new_obj.identification_code not in old_codes:
                    PeopleOrganization.objects.create(people_id=peo_obj.id, org_code=may_new_obj.identification_code)
                    info_logger.info('CREATE org_id %s org_name %s people_id %s' % (may_new_obj.id, may_new_obj.name, peo_obj.id))
                    old_codes.append(may_new_obj.identification_code)
                org_obj = may_new_obj
    return None


class Command(BaseCommand):
    help = "parse tag system excel"

    @transaction.atomic
    def handle(self, *args, **options):
        user_qs = AuthUser.objects.filter(is_active=True)
        for user_obj in user_qs:
            people_all_org(user_obj, len(user_qs))