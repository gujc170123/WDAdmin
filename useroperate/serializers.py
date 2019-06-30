# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from sales.serializers import Product_SpecificationSerializer
from sales.models import Product_Specification,Schema
from useroperate import models

class Product_AssessDetailSerializer(serializers.Serializer):

    # key_spec = serializers.SerializerMethodField

    class Meta:
        model = Product_Specification
        fields = '__all__'

    # def get_key_spec(self, obj):
    #     attrlist =  Schema.objects.filter(category_id=obj.category_id).values()
    #     attrvalues={}
    #     for attr in attrlist:
    #         attrvalues[attr]=obj.getattr(attr)
    #     return attrvalues

class MessageSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Message
        fields = '__all__'

class MessagePushSerializer(serializers.ModelSerializer):

    content = serializers.SerializerMethodField()

    class Meta:
        model = models.MessagePush
        fields = '__all__'

    def get_content(self, obj):
        message = models.Message.objects.get(id=obj.message_id)
        return message.content