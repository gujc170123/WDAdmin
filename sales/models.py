# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from eav.models import BaseChoice,BaseEntity, BaseSchema, BaseAttribute
from wduser.models import EnterpriseInfo
from django.db.models.signals import post_save,pre_save
from django.dispatch import receiver
import time

def get_order_code():
    order_no = str(time.strftime('%Y%m%d%H%M%S', time.localtime(time.time())))+ str(time.time()).replace('.', '')[-7:]
    return order_no

class Category(models.Model):

    name = models.CharField(max_length=100)

    def __unicode__(self):
        return self.name   

class Schema(BaseSchema):

    category = models.ForeignKey(Category)
    addable = models.BooleanField(default=True)

class Choice(BaseChoice):
    schema = models.ForeignKey(Schema, related_name='choices')

class Product_Specification(BaseEntity):

    price = models.DecimalField(max_digits=8,decimal_places=2,null=True)
    title = models.CharField(max_length=50)
    menu = models.CharField(max_length=50)
    category = models.ForeignKey(Category, db_constraint=False)
    is_platform = models.BooleanField(default=False)

    @classmethod
    def get_schemata_for_model(self):
        return Schema.objects.all()

    def __unicode__(self):
        return self.title

class Attr(BaseAttribute):

    schema = models.ForeignKey(Schema, related_name='attrs')
    choice = models.ForeignKey(Choice, blank=True, null=True)

class Order(models.Model):

    class Meta:
        verbose_name_plural=u'订单'
        verbose_name=u'订单'

    UNIT_CHOICES=(
            (1,'Time'),
            (2,'Piece'))
    
    STATUS_CHOICES=(
            (1,'NotPaid'),
            (2,'Paid'),
            (3,'Delivered'),
            (4,'Cancelled'))

    order_no = models.CharField(max_length=30, db_index=True,default=get_order_code)
    order_status = models.IntegerField(choices=STATUS_CHOICES, default=1, db_index=True)
    enterprise = models.ForeignKey(EnterpriseInfo, on_delete=models.CASCADE, db_constraint=False)
    product_amount = models.DecimalField(max_digits=12,decimal_places=2, default=0)
    order_amount = models.DecimalField(max_digits=12,decimal_places=2, default=0)
    order_date = models.DateTimeField()
    paid_date = models.DateTimeField(null=True)
    delivered_date = models.DateTimeField(null=True)

    def __unicode__(self):
        return self.order_no

class OrderDetail(models.Model):

    class Meta:
        verbose_name_plural=u'订单明细'
        verbose_name=u'订单明细'

    order = models.ForeignKey(Order, on_delete=models.CASCADE,related_name='products')
    sku = models.ForeignKey(Product_Specification, db_constraint=False)
    sku_name = models.CharField(max_length=150)
    price = models.DecimalField(max_digits=12,decimal_places=2)
    discount_rate = models.DecimalField(max_digits=5,decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=8,decimal_places=2, default=0)
    number = models.IntegerField(default=1)
    subtotal = models.DecimalField(max_digits=12,decimal_places=2, default=0)
    remark = models.CharField(max_length=200, null=True)

    def __unicode__(self):
        return self.sku_name

class Consume(models.Model):

    balance_id = models.IntegerField(db_index=True)
    number = models.IntegerField()
    consume_date = models.DateTimeField(auto_now_add=True)

class Balance(models.Model):

    class Meta:
        verbose_name_plural=u'财务余额'
        verbose_name=u'财务余额'

    enterprise = models.ForeignKey(EnterpriseInfo, db_constraint=False)
    sku = models.ForeignKey(Product_Specification, db_constraint=False)
    number = models.IntegerField()
    validfrom = models.DateField()
    validto = models.DateField()

    def __unicode__(self):
        return self.id

@receiver(post_save, sender=Consume, dispatch_uid="update_balance")
def update_balance(sender, instance, **kwargs):
     balance = Balance.objects.get(id=instance.balance_id)
     balance.number = balance.number - instance.number
     balance.save()