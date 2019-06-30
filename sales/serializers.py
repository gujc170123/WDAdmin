# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from sales import models
from datetime import date

class Product_SpecificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Product_Specification
        fields = ('id','price','title','menu','category_id','is_platform')

class BalanceSerializer(serializers.ModelSerializer):

    remaindays = serializers.SerializerMethodField('get_days_remain')    

    class Meta:
        model = models.Balance
        fields = ('enterprise_id','sku','number','validfrom','validto','remaindays')
    
    def get_days_remain(self, obj):
        dayCount = (obj.validto - date.today()).days
        if dayCount<0:
            return 0
        return dayCount

class OrderDetailSerializer(serializers.ModelSerializer):   

    class Meta:
        model = models.OrderDetail
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):

    details = OrderDetailSerializer(many=True, read_only=True)

    class Meta:
        model = models.Order
        fields = '__all__'

class ConsumeSerializer(serializers.ModelSerializer):   

    class Meta:
        model = models.Consume
        fields = '__all__'