from celery import shared_task
from celery_progress.backend import ProgressRecorder
from workspace.helper import write_file,read_file
from django.db import connection
import datetime
import pandas

@shared_task(bind=True)
def userimport_task(self,file_data, file_name, enterprise_id ,total,delimiter):
    progress_recorder = ProgressRecorder(self)
    str_now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    filepath = write_file("assess",file_data, file_name, assess_id,str_now)
    if not filepath:
        return False
    progress_recorder.set_progress(1, 6)
    targetcols=[]
    mustcols=[]
    keycols=[]
    codedict={'':[],'':[]}
    data = read_file(filepath,targetcols,mustcols,keycols,codedict)
    if not data:
        return False
    progress_recorder.set_progress(2,6)
    importdata(data,enterprise_id,delimiter)
    return True

def importdata(data,enterprise_id,delimiter):
    dataorganizations = pandas.read_sql("Call GetOrganization(%s,%s)",connection)    
    datausers = pandas.read_sql("select * from wduser_authuser a, wduser_organization where ",connection)    