from eav.admin import BaseEntityAdmin, BaseSchemaAdmin
from django.contrib import admin
from sales import models
from forms import Product_SpecificationForm
 

class Product_SpecificationAdmin(BaseEntityAdmin):
    form = Product_SpecificationForm

# Register your models here.
admin.site.register(models.Category)
admin.site.register(models.Schema)
admin.site.register(models.Attr)
admin.site.register(models.Consume)
admin.site.register(models.Balance)
admin.site.register(models.Product_Specification,Product_SpecificationAdmin)
admin.site.register(models.Order)
admin.site.register(models.OrderDetail)