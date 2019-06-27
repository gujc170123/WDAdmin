from __future__ import unicode_literals

from django.db import models
from wduser.models import EnterpriseInfo

class Message(models.Model):

    # todo message read record shoulb be logged with user
    enterprise = models.IntegerField(db_index=True)
    title = models.CharField(max_length=50)
    content = models.URLField()
    is_read = models.BooleanField(default=False)

    def __unicode__(self):
        return self.title
