# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import time
from django.core.management import BaseCommand
from django.db import transaction

from assessment.models import AssessUser, AssessProject
from utils.logger import get_logger
from wduser.models import AuthUser, People, EnterpriseInfo, EnterpriseAccount

logger = get_logger("enterprise_account")

def enterprise_account(auth_obj):
    u"""处理原来的项目里面的人的账户"""
    # try:
    #     auth_obj = AuthUser.objects.get(id=user_id)
    # except:
    #     logger.info("user_id %s has error authuser" % user_id)   # 没有这个Authuser
    #     return None
    user_id = auth_obj.id
    if not auth_obj.account_name:
        logger.info("user_id %s has no account" % user_id)   # 用户没有账户名
        return None
    try:
        peo_obj = People.objects.get(user_id=user_id)
    except:
        logger.info("user_id %s has error People" % user_id)  # 用户没有 people
        return None
    # 可以参与多个项目
    if peo_obj:
        assuser_qs = AssessUser.objects.filter_active(people_id=peo_obj.id).values_list("assess_id", flat=True)
        if not assuser_qs:
            logger.info("user_id %s has error assess" % user_id)
            # 用户没有项目
            return None
        ass_enter_ids = AssessProject.objects.filter_active(id__in=assuser_qs).values_list("enterprise_id", flat=True).distinct()
        for ass_enter in ass_enter_ids:
            old_ea_qs_all = EnterpriseAccount.objects.filter_active(
                enterprise_id=ass_enter,
                account_name=auth_obj.account_name,
            )
            if old_ea_qs_all.count() > 1:
                logger.error('ERROR ea_id %s account %s double error' % (old_ea_qs_all[0].id, old_ea_qs_all[0].account_name))
                # 同一企业有2个账户
                return None
            elif old_ea_qs_all.count() == 1:
                if old_ea_qs_all[0].user_id != user_id:
                    logger.debug('user_id %s NEED DEBUG ea_id %s account %s has user_id %s error with new user_id' % (user_id, old_ea_qs_all[0].id, old_ea_qs_all[0].account_name, old_ea_qs_all[0].user_id))
                    # 企业账户名已被使用
                    return None
                else:
                    logger.info("user_id %s HAS EXISTS ea_id %s account %s has user_id" % (old_ea_qs_all[0].user_id, old_ea_qs_all[0].id, old_ea_qs_all[0].account_name))
                    # 你已经存在了
            elif old_ea_qs_all.count() == 0:
                ea = EnterpriseAccount.objects.create(
                    enterprise_id=ass_enter,
                    account_name=auth_obj.account_name,
                    user_id=user_id,
                    people_id=peo_obj.id
                )
                logger.info("user_id %s, success ea_id %s new " % (user_id, ea.id))
                # 成功


class Command(BaseCommand):
    help = "parse tag system excel"

    @transaction.atomic
    def handle(self, *args, **options):
        user_qs = AuthUser.objects.filter(is_active=True)
        for user in user_qs:
            enterprise_account(user)