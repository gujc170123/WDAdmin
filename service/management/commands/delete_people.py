# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import time
from django.core.management import BaseCommand
from django.db import transaction

from assessment.models import AssessUser, AssessProject
from utils.logger import get_logger
from wduser.models import AuthUser, People, EnterpriseInfo, EnterpriseAccount, PeopleOrganization

logger = get_logger("enterprise_account")

def delete_people_assess(assess_id):
    au_qs = AssessUser.objects.filter(assess_id=assess_id)
    print au_qs.count()
    people_ids = au_qs.values_list("people_id", flat=True)
    people_qs = People.objects.filter(id__in=people_ids)
    print people_qs.count()
    user_ids = people_qs.values_list("user_id", flat=True)
    user_qs = AuthUser.objects.filter(id__in=user_ids)
    print user_qs.count()
    ea_qs = EnterpriseAccount.objects.filter(people_id__in=people_ids)
    print ea_qs.count()
    po_qs = PeopleOrganization.objects.filter(people_id__in=people_ids)
    print po_qs.count()

    ea_qs.update(is_active=False)
    po_qs.update(is_active=False)
    au_qs.update(is_active=False)
    people_qs.update(is_active=False)
    user_qs.update(is_active=False)

class Command(BaseCommand):
    help = "parse tag system excel"

    @transaction.atomic
    def handle(self, *args, **options):
        # authuser_id_list = [x for x in range(15946, 93700)]
        assess_id = -1
        delete_people_assess(assess_id)