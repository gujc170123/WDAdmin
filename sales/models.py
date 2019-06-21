from __future__ import unicode_literals

from django.db import models
from eav.models import BaseEntity, BaseSchema, BaseAttribute
from wduser.models import EnterpriseInfo

class Category(models):

    name = models.CharField(maxlength=100)

class Schema(BaseSchema):

    category = models.ForeignKey(Category)
    addable = models.BooleanField(default=True)

class Product(models):

    category = models.ForeignKey(Category)
    name = models.CharField(maxlength=100)

class Product_Specification(BaseEntity):

    product = models.ForeignKey(Product)
    price = models.DecimalField(max_digits=8,decimal_places=2)

class Attr(BaseAttribute):

    schema = models.ForeignKey(Schema, related_name='attrs')

class Order(models):

    UNIT_CHOICES=(
            (1,'Time'),
            (2,'Piece'))
    
    STATUS_CHOICES=(
            (1,'NotPaid'),
            (2,'Paid'),
            (3,'Delivered'),
            (4,'Cancelled'))

    order_no = models.CharField(max_length=18, db_index=True)
    order_status = models.IntegerField(choices=STATUS_CHOICES, default=1, db_index=True)
    enterprise = models.ForeignKey(EnterpriseInfo, on_delete=models.CASCADE)
    product_amount = models.DecimalField(max_digits=12,decimal_places=2, default=0)
    order_amount = models.DecimalField(max_digits=12,decimal_places=2, default=0)
    order_date = models.DateTimeField()
    paid_date = models.DateTimeField()
    delivered_date = models.DateTimeField()

class OrderDetail(models):

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    sku = models.ForeignKey(Product_Specification)
    sku_name = models.CharField(max_length=150)
    discount_rate = models.DecimalField(max_digits=5,decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=8,decimal_places=2, default=0)
    number = models.IntegerField(default=0)
    subtotal = models.DecimalField(max_digits=12,decimal_places=2, default=0)
    remark = models.CharField(max_length=200, null=True)

class Consume(models):

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    enterprise = models.ForeignKey(EnterpriseInfo, on_delete=models.CASCADE)
    num = models.IntegerField()
    consume_date = models.DateTimeField()

class Balance(BaseEntity):

    product = models.ForeignKey(Product, on_delete=models.CASCADE)