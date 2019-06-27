from django.contrib import admin
from application import models

admin.site.register(models.Application)
admin.site.register(models.Applier)
admin.site.register(models.Event)