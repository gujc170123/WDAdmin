# -*- coding:utf-8 -*-
from celery import shared_task
from workspace.helper import write_file,read_file,is_valid_date,convertna2none
from django.db import connection
from WeiDuAdmin import settings
from wduser.models import AuthUser,People,EnterpriseAccount
from utils.regular import RegularUtils
from assessment.views import get_mima
import datetime,json,re,pandas as pd,numpy as np
from .util.etl_transfer import main
from pymysql import connect

class UserImport:

    errorlogs = []

    def __init__(self, hostname, port, user, passwd, db):
        self.conn = connect(host=hostname, port=port, user=user, passwd=passwd, db=db, use_unicode=True,charset='utf8')
        self.cursor = self.conn.cursor()   

    def validateEmail(self,email):
        if len(email) > 7:
            if re.match("^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$", email) != None:
                return True
        return False

    def validatePhone(self,phone):
        if re.match(r"^1[35678]\d{9}$", phone):
            return True
        return False

    def readfile(self,file,usecols):
        sheet = None
        err = []
        try:
            sheet = pd.read_excel(file,usecols="A:J",dtype=str ,encoding='utf-8')
            sheet.columns = usecols
            # sheet = pd.read_excel(book,engine='xlrd',dtype=str)
        except Exception as e:
            err.append(str(e))
        return sheet,err

    def importusers(self,file,usecols,parseevalues,enterprise):
        # read excel into dataframe
        sheet,err = self.readfile(file,usecols)
        if err:
            self.errorlogs.extend(err)
            return False,self.errorlogs
        # merge dataframe with parservalues
        for key in parseevalues.keys():
            sheet = sheet.merge(parseevalues[key],how="left")
        # merge dataframe with enterpriseuser-authusers
        sqlaccount= "select a.account_name as 工号,a.id as acid from wduser_authuser a,wduser_enterpriseaccount b \
                    where a.id=b.user_id and b.enterprise_id=%s and a.is_active=true and b.is_active=true and a.account_name is not null"
        sqlmail= "select a.email as 邮箱,a.id as mailid from wduser_authuser a,wduser_enterpriseaccount b \
                    where a.id=b.user_id and b.enterprise_id=%s and a.is_active=true and b.is_active=true and a.email is not null"
        sqlphone= "select a.phone as 手机号,a.id as phoneid from wduser_authuser a,wduser_enterpriseaccount b \
                    where a.id=b.user_id and b.enterprise_id=%s and a.is_active=true and b.is_active=true and a.phone is not null"

        sqlorgs = "Call GetOrganization(%s,%s)"

        orgsindb =  pd.read_sql_query(sql=sqlorgs,con=connection,params=(enterprise,',',))
        orgsindb.orgname = orgsindb.orgname.str.encode('utf-8')
        # orgsindb.columns = ['organization_id','所属部门']
        accountindb =  pd.read_sql_query(sql=sqlaccount,con=connection,params=(enterprise,))
        mailindb = pd.read_sql_query(sql=sqlmail,con=connection,params=(enterprise,))
        phonedb = pd.read_sql_query(sql=sqlphone,con=connection,params=(enterprise,))
        sheet = sheet.merge(accountindb,how='left')
        sheet = sheet.merge(mailindb,how='left')
        sheet = sheet.merge(phonedb,how='left')
        sheet = sheet.merge(orgsindb,how='left')
        # interate dataframe
        i = 1
        idxaccount = {}
        idxphone = {}
        idxmail = {}
        userstoadd = []
        userstoupdate = []

        importlot = int((datetime.datetime.now()-datetime.datetime(1970,1,1)).total_seconds())
        for index, row in sheet.iterrows():
            if len(self.errorlogs)>100:
                self.errorlogs.append('错误超过100条，之后不再显示')
                break
            # A.check identification fields
            isempty = True
            append = True
            tmpuserid = 0
            dictrow = {'account_name':None,'email':None,'phone':None,'nickname':None,
                        'organization_id':None,'age_id':None,'seniority_id':None,
                        'education_id':None,'politics_id':None,'role_type':100}
            importinfo = {}
            # mail validation
            if not pd.isna(row['邮箱']):
                isempty= False
                if not self.validateEmail(row['邮箱']):
                    self.errorlogs.append('无效的邮箱。行%s' % (i))
                else:
                    if row['邮箱'] in idxmail:
                        self.errorlogs.append('邮箱重复。行%svs行%s' % (i,idxmail[row['邮箱']]))
                    else:
                        # push identification fields into keylist
                        idxmail[row['邮箱']] = i
                dictrow['email'] = row['邮箱']
            # phone validation
            if not pd.isna(row['手机号']):
                isempty= False
                if not self.validatePhone(row['手机号']):
                    self.errorlogs.append('无效的手机号。行%s' % (i))
                else:                    
                    if row['手机号'] in idxphone:
                        self.errorlogs.append('手机号重复。行%svs行%s' % (i,idxphone[row['手机号']]))
                    else:
                        # push identification fields into keylist
                        idxphone[row['手机号']] = i
                dictrow['phone'] = row['手机号']
            if not pd.isna(row['工号']):
                isempty= False
                if row['工号'] in idxaccount:
                    self.errorlogs.append('工号重复。行%svs行%s' % (i,idxaccount[row['工号']]))
                else:
                    # push identification fields into keylist
                    idxaccount[row['工号']] = i
                dictrow['account_name'] = row['工号']
            # not null index
            if isempty:
                if pd.isna(row['姓名']) and pd.isna(row['orgname']):
                    #exit from empty row
                    break
                else:
                    self.errorlogs.append('邮箱，工号，手机号至少填写一项。行%s' % (i))            

            # B.check other required fields
            if pd.isna(row['姓名']):
                self.errorlogs.append('姓名不可为空白。行%s' % (i))
            else:
                dictrow['nickname'] = row['姓名']
            if row['orgname']=='nan':
                self.errorlogs.append('所属部门不可为空白。行%s' % (i))
            elif pd.isna(row['organization_id']):
                self.errorlogs.append('所属机构不存在。行%s' % (i))
            else:
                dictrow['organization_id'] = row['organization_id']
            # C.check parser values
            if not pd.isna(row['部门主管']):
                dictrow['role_type'] = row['role_type']
            if not pd.isna(row['学历']):
                if pd.isna(row['education']):
                    self.errorlogs.append('学历填写不正确。行%s' % (i))
                else:
                    dictrow['education_id'] = row['education']
                importinfo['学历']=row['学历']
            if not pd.isna(row['年龄']):
                if pd.isna(row['age']):
                    self.errorlogs.append('年龄填写不正确。行%s' % (i))
                else:
                    dictrow['age_id'] = row['age']
                importinfo['年龄']=row['年龄']                
            if not pd.isna(row['政治面貌']):
                if pd.isna(row['politics']):
                    self.errorlogs.append('政治面貌填写不正确。行%s' % (i))
                else:
                    dictrow['politics_id'] = row['politics']
                importinfo['政治面貌']=row['政治面貌']
            if not pd.isna(row['司龄']):
                if pd.isna(row['seniority']):
                    self.errorlogs.append('司龄填写不正确。行%s' % (i))
                else:
                    dictrow['seniority_id'] = row['seniority']
                importinfo['司龄']=row['司龄']
            # D.match index keys with db
            if not pd.isna(row['acid']):
                append = False
                tmpuserid = row['acid']
            if not pd.isna(row['mailid']):
                append = False
                if tmpuserid>0 and tmpuserid!=row['mailid']:
                    self.errorlogs.append('工号/手机/邮箱已分别为2名以上用户注册。行%s' % (i))
            if not pd.isna(row['phoneid']):
                append = False
                if tmpuserid>0 and tmpuserid!=row['phoneid']:
                    self.errorlogs.append('工号/手机/邮箱已分别为2名以上用户注册。行%s' % (i))
            dictrow['profile'] = json.dumps(importinfo, ensure_ascii=False)
            if append:                
                dictrow['username'] = ''
                dictrow['first_name'] = ''
                dictrow['last_name'] = ''
                dictrow['is_staff'] = True
                dictrow['is_superuser'] = False
                dictrow['date_joined'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                dictrow['is_active'] = True
                dictrow['active_code_valid'] = False
                dictrow['importlot'] = importlot
                dictrow['password'] = 'pbkdf2_sha256$36000$UVBQYHUroCQ2$oK1N/h0YLveYFWYGuyZrbZKzc7z0yyImlU9u/IUA8Qc='
                userstoadd.append(dictrow)
            else:
                dictrow['user_id'] = tmpuserid                
                userstoupdate.append(dictrow)
            i += 1

        if len(self.errorlogs) > 0:
            return False,self.errorlogs

        try:
            if userstoadd:
                mydf = pd.DataFrame(userstoadd,columns=userstoadd[0].keys())
                strupdateusersql = "update wduser_authuser set dedicated_link=SHA(lpad(id,10,' '))  where importlot=" + str(importlot)
                authuserfields = ','.join(mydf.columns.values.tolist())
                s = ','.join(['%s' for _ in range(len(mydf.columns))])
                values = mydf.values.tolist()
                straddusersql = "insert into wduser_authuser ({})values ({})".format(authuserfields,s)
                print(straddusersql, values[0])
                self.cursor.executemany(straddusersql, values)
                straddpeoplesql = "insert into wduser_people (create_time,is_active,update_time,\
                                    creator_id,last_modify_user_id,user_id,username,phone,email,active_code_valid,more_info,importlot)\
                                    select sysdate(),true,sysdate(),1,1,id,account_name,phone,email,false,profile,importlot\
                                    from wduser_authuser where importlot={}".format(importlot)
                straddenterprisesql = "insert into wduser_enterpriseaccount (create_time,is_active,update_time,\
                                    creator_id,last_modify_user_id,enterprise_id,account_name,user_id,people_id)\
                                    select sysdate(),true,sysdate(),1,1,{},username,user_id,id\
                                    from wduser_people where importlot={}".format(enterprise,importlot)
                self.cursor.execute(strupdateusersql)
                self.cursor.execute(straddpeoplesql)
                self.cursor.execute(straddenterprisesql)

            if userstoupdate:
                
                table_name = "tmpimport" + str(importlot)
                field1 ="(`user_id` int(11) ,\
                        `phone` varchar(20) DEFAULT NULL,\
                        `email` varchar(254) DEFAULT NULL,\
                        `nickname` varchar(64) DEFAULT NULL,\
                        `account_name` varchar(200) DEFAULT NULL,\
                        `role_type` int(10) unsigned NOT NULL,\
                        `age_id` int(11) DEFAULT NULL,\
                        `seniority_id` int(11) DEFAULT NULL,\
                        `gender_id` int(11) DEFAULT NULL,\
                        `marriage_id` int(11) DEFAULT NULL,\
                        `organization_id` int(11) DEFAULT NULL,\
                        `rank_id` int(11) DEFAULT NULL,\
                        `sequence_id` int(11) DEFAULT NULL,\
                        `politics_id` int(11) DEFAULT NULL,\
                        `education_id` int(11) DEFAULT NULL,\
                        `profile` varchar(4096) DEFAULT NULL,\
                        PRIMARY KEY (`user_id`) USING BTREE)"            
                self.cursor.execute('drop table if exists {}'.format(table_name))
                self.cursor.execute("create table {} {}".format(table_name, field1))
                listfield = ['phone','email','nickname','account_name','age_id','role_type','seniority_id','gender_id','marriage_id','organization_id','rank_id','sequence_id','politics_id','education_id']                

                mydf = pd.DataFrame(userstoupdate,columns=userstoupdate[0].keys())
                authuserfields = ','.join(mydf.columns.values.tolist())
                s = ','.join(['%s' for _ in range(len(mydf.columns))])
                updatefields = ','.join(['a.' + column + '=IFNULL(b.' + column + ',a.' +column + ')' for column in listfield])
                updatefields = updatefields + ',a.profile=JSON_MERGE_PATCH(a.profile,b.profile)'
                values = mydf.values.tolist()
                straddtmpusrsql = "insert into {} ({})values ({})".format(table_name,authuserfields,s)
                self.cursor.executemany(straddtmpusrsql, values)
                self.cursor.execute("update wduser_authuser a inner join {} b on a.id=b.user_id set {} ".format(table_name,updatefields))
                listfield = ['phone','email']
                updatefields = ','.join(['a.' + column + '=IFNULL(b.' + column + ',a.' +column + ')' for column in listfield])
                updatefields = updatefields + ',a.more_info=JSON_MERGE_PATCH(a.more_info,b.profile)'
                updatefields = updatefields + ',a.username=IFNULL(b.account_name,a.username)'
                self.cursor.execute("update wduser_people a inner join {} b on a.user_id=b.user_id set {} where a.is_active=True".format(table_name,updatefields))                
                self.cursor.execute('drop table if exists {}'.format(table_name))
            self.conn.commit()
        except Exception as e:
            self.errorlogs.append('数据更新错误。%s' % (e))
            self.conn.rollback()
        finally:
            self.cursor.close()
            self.conn.close()
            return len(self.errorlogs) == 0,self.errorlogs

def userimport_task(file_data, file_name, enterprise_id ):

    str_now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    filepath = write_file("users",file_data, file_name, enterprise_id,str_now)
    usecols = ['邮箱','工号','手机号','姓名','orgname','部门主管','年龄','司龄','学历','政治面貌']
    parseevalues = {'学历':pd.DataFrame({'学历':['大专及以下','本科','硕士及以上'],'education':[1,2,3]},dtype=str),
                    '部门主管':pd.DataFrame({'部门主管':['是','否'],'role_type':[200,100]},dtype=str),
                    '年龄':pd.DataFrame({'年龄':['25岁及以下','26-30岁','31-35岁','36-40岁','41-45岁','46-50岁','50岁及以上'],'age':[1,2,3,4,5,6,7]},dtype=str),
                    '政治面貌':pd.DataFrame({'政治面貌':['中共党员','中共预备党员','共青团员','其他党派','群众'],'politics':[1,2,3,4,5]},dtype=str),
                    '司龄':pd.DataFrame({'司龄':['1年及以下','1-3年','3-5年','6-10年','11-15年','16年及以上'],'seniority':[1,2,3,4,5,6]},dtype=str)}
    hostname = settings.DATABASES['default']['HOST'].encode("utf-8")
    port = int(settings.DATABASES['default']['PORT'])
    user = settings.DATABASES['default']['USER'].encode("utf-8")
    passwd = settings.DATABASES['default']['PASSWORD'].encode("utf-8")
    db = settings.DATABASES['default']['NAME'].encode("utf-8")
    importer = UserImport(hostname=hostname, port=port, user=user, passwd=passwd, db=db)
    result, errs = importer.importusers(filepath,usecols,parseevalues,enterprise_id)
    return result,errs
 

def CreateNewUser(username,account_name,nickname,pwd,phone,email,is_superuser,
                    role_type,is_staff,sequence,gender,age,rank,seniority,marriage,
                    politics,education,organization_id,enterprise_id):
    #create user object
    if not role_type:
        role_type = 100
    user = AuthUser.objects.create(
        username=username,
        account_name=account_name,
        nickname=nickname,
        password=get_mima(pwd),
        phone=phone,
        email=email,
        is_superuser=is_superuser,
        role_type=role_type,
        is_staff=is_staff,
        sequence_id=sequence,
        gender_id=gender,
        age_id=age,
        rank_id=rank,
        seniority_id=seniority,
        politics_id=politics,
        education_id=education,
        marriage_id=marriage,
        organization_id=organization_id
    )

    #create people object
    people = People.objects.create(user_id=user.id, 
                                    username=account_name, 
                                    phone=phone,
                                    email=email)
    #create enterprise-account object
    EnterpriseAccount.objects.create(user_id=user.id,
                                        people_id=people.id,
                                        account_name=account_name,
                                        enterprise_id=enterprise_id)

    return user