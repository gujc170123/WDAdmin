# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from sales import models
from datetime import date

class AttrSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Attr
        fields = '__all__'

class SchemaSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Schema
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Category
        fields = '__all__'


class Product_SpecificationSerializer(serializers.ModelSerializer):

    survey_id = serializers.SerializerMethodField()
    category = CategorySerializer    
    attrs = serializers.SerializerMethodField()

    class Meta:
        depth = 1
        model = models.Product_Specification        
        fields = ('id','category_id','menu','price','title','survey_id','category','attrs','is_platform')

    def get_survey_id(self, obj):
        return obj.assess_surveys
    
    def get_attrs(self,obj):
        data = []
        for k,v in obj._schemata_cache_dict.items():
            if v.category_id==obj.category_id:
                data.append({"id":v.pk,"name":k,"title":v.title,"value":obj.__getattr__(k)})
        return data

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

    sku = Product_SpecificationSerializer

    class Meta:
        model = models.OrderDetail
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):

    products = OrderDetailSerializer(many=True)

    class Meta:
        depth = 1
        model = models.Order
        fields = '__all__'
        # fields = ('id','order_no','order_status','enterprise_id','product_amount','order_amount','order_date','paid_date','delivered_date','enterprise','orderdetails')

class ConsumeSerializer(serializers.ModelSerializer):   

    class Meta:
        model = models.Consume
        fields = '__all__'