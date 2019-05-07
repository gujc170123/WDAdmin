# -*- coding:utf-8 -*-
from celery import shared_task
from workspace.helper import write_file,read_file,is_valid_date,convertna2none
from django.db import connection
from wduser.models import AuthUser,People,EnterpriseAccount
from utils.regular import RegularUtils
from assessment.views import get_mima
import datetime,pandas,numpy as np

def userimport_task(file_data, file_name, enterprise_id ,total,delimiter):

    str_now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    filepath = write_file("users",file_data, file_name, enterprise_id,str_now)
    if not filepath:
        return False

    targetcols = [u"邮箱",u"工号",u"手机号",u"姓名",u"出生年月",u"性别",u"所属部门",u"是否为部门主管",u"层级",u"入职时间",u"序列"]              
    mustcolsset = [u"工号",u"手机号",u"邮箱"]
    mustcols = [u"所属部门"]
    keycols = [u"工号",u"手机号",u"邮箱"]
    codedict = {u"性别":[u"男",u"女"],u"层级":[u"高级",u"中级",u"初级"],
              u"序列":[u"管理",u"职能",u"技术",u"营销",u"操作"],
              u"是否为部门主管":[u"是",u"否"]}
    typedict = {u"邮箱":np.str,u"工号":np.str,u"手机号":np.str,u"姓名":np.str,u"出生年月":np.str,u"性别":np.str,
                u"所属部门":np.str,u"是否为部门主管":np.str,u"层级":np.str,u"入职时间":np.str,u"序列":np.str} 
    res,data = read_file(filepath,targetcols,typedict,mustcolsset,mustcols,keycols,codedict)
    if not res:
        return False

    res,datatoadd = preparedata(data,enterprise_id,delimiter)

    if not res:
        return False
    importdata(datatoadd)
    return True

def preparedata(data,enterprise_id,delimiter):
    #get organization list
    dataorganizations = pandas.read_sql("Call GetOrganization(%s,%s)",connection,params=[enterprise_id,delimiter])
    orgmerge = pandas.merge(data,dataorganizations,left_on=u'所属部门',right_on='orgname',how='left')
    invalidorg = orgmerge[orgmerge['orgname'].isnull()]['indice'].tolist()
    if len(invalidorg):
        return False,[]
    #get original users info
    datausers = pandas.read_sql("select a.account_name,a.phone,a.email,b.enterprise_id from wduser_authuser a, wduser_baseorganization b \
                                where a.organization_id=b.id and a.is_active=true and b.is_active=true \
                                and b.enterprise_id=%s ",connection,params=[enterprise_id])
    duplicated = pandas.merge(data,datausers,left_on=u'工号',right_on='account_name')['indice'].tolist()
    if len(duplicated):
        return False,[]
    duplicated = pandas.merge(data,datausers,left_on=u'邮箱',right_on='email')['indice'].tolist()
    if len(duplicated):
        return False,[]
    duplicated = pandas.merge(data,datausers,left_on=u'手机号',right_on='phone')['indice'].tolist()
    if len(duplicated):
        return False,[]
    
    codedict = {u"性别":pandas.DataFrame({u"性别":[u"男",u"女"],'gender':[1,2]}),
                 u"层级":pandas.DataFrame({u"层级":[u"高级",u"中级",u"初级"],'rank':[3,2,1]}),
                 u"序列":pandas.DataFrame({u"序列":[u"管理",u"职能",u"技术",u"营销",u"操作"],'sequence':[1,2,3,4,5]}),
                 u"是否为部门主管":pandas.DataFrame({u"是否为部门主管":[u"是",u"否"],'role_type':[200,100]})}
    res = orgmerge
    for k,v in  codedict.items():
        res = pandas.merge(res,codedict[k],left_on=k,right_on=k,how='left')

    for index, row in res.iterrows():
        if not pandas.isnull(row[u"手机号"]):
            if not RegularUtils.phone_check(row[u"手机号"]):
                return False,[]
        if not pandas.isnull(row[u"邮箱"]):
            if not RegularUtils.email_check(row[u"邮箱"]):
                return False,[]
        if not pandas.isnull(row[u"出生年月"]):
            if not is_valid_date(row[u"出生年月"]):
                return False,[]
        if not pandas.isnull(row[u"入职时间"]):
            if not is_valid_date(row[u"入职时间"]):
                return False,[]
    return True,res


def importdata(data):  
    for index, row in data.iterrows():
        user = CreateNewUser(
                    username=convertna2none(row[u"姓名"]),
                    account_name=convertna2none(row[u"工号"]),
                    nickname=convertna2none(row[u"姓名"]),
                    pwd='123456',
                    phone=convertna2none(row[u"手机号"]),
                    email=convertna2none(row[u"邮箱"]),
                    is_superuser=False,
                    role_type=convertna2none(row['role_type']),
                    is_staff=True,
                    sequence=convertna2none(row['sequence']),
                    gender=convertna2none(row['gender']),
                    birthday=convertna2none(row[u"出生年月"]),
                    rank=convertna2none(row['rank']),
                    hiredate=convertna2none(row[u"入职时间"]),
                    marriage=None,
                    organization_id=row['id']
        )

def CreateNewUser(username,account_name,nickname,pwd,phone,email,is_superuser,
                    role_type,is_staff,sequence,gender,birthday,rank,hiredate,marriage,
                    organization_id):
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
        birthday=birthday,
        rank_id=rank,
        hiredate=hiredate,
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
                                        enterprise_id=organization_id)

    return user