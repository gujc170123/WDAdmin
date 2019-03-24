# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Q

from assessment.models import AssessUser
from front.models import PeopleSurveyRelation
from wduser.models import AuthUser, People, PeopleOrganization


def clean_user(account):
    users = AuthUser.objects.filter(is_active=True).filter(
        Q(username=account) | Q(phone=account) | Q(email=account))
    uids = list(users.values_list("id", flat=True))
    peoples = People.objects.filter_active(Q(user_id__in=uids)|Q(phone=account)|Q(email=account))
    people_ids = list(peoples.values_list("id", flat=True))
    users.update(is_active=False)
    peoples.update(is_active=False)
    AssessUser.objects.filter_active(people_id__in=people_ids).update(is_active=False)
    PeopleOrganization.objects.filter_active(people_id__in=people_ids).update(is_active=False)
    PeopleSurveyRelation.objects.filter_active(people_id__in=people_ids).update(is_active=False)
    PeopleSurveyRelation.objects.filter_active(evaluated_people_id__in=people_ids).update(is_active=False)
    print "clean user: %s" % account


class Command(BaseCommand):
    help = "parse tag system excel"

    def add_arguments(self, parser):
        parser.add_argument("--process_users", dest="process_users", action="store", type=str,
                            help="process user to deactive, user join with',', like: account1,account2")

    @transaction.atomic
    def handle(self, *args, **options):
        process_users = options["process_users"]
        accounts = process_users.split(",")
        for account in accounts:
            clean_user(account)