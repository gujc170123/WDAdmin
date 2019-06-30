from __future__ import unicode_literals

from django.db import models
from wduser.models import EnterpriseInfo

class Message(models.Model):

    title = models.CharField(max_length=50)
    content = models.URLField()
    cancel = models.BooleanField(default=False,db_index=True)

    def __unicode__(self):
        return self.title

class MessagePush(models.Model):

    message_id = models.IntegerField(db_index=True)
    enterprise_id = models.IntegerField(db_index=True)
    pushdate = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __unicode__(self):
        return self.pushdate



