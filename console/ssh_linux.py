# -*- coding:utf-8 -*-

# from impala.dbapi import connect
#
#
# def conn():
#     # 连接hive
#     con = connect(host="47.99.72.229", port=10000, database='default', auth_mechanism="PLAIN")
#     cur = con.cursor()
#     return cur
#
#
# def run_hql(sql):
#     # 执行HQL语句 对hql进行连续处理
#     sql_list = sql[:-1].split(";")
#     cur = conn()
#     for s in sql_list:
#         cur.execute(s)
#     result = cur.fetchall()
#     return result
#
#
# if __name__ == "__main__":
#     sql = "show databases;use default;show tables;"
#     print run_hql(sql)
# import paramiko
# from datetime import datetime
#
#
# def con_linux(people_survey_info, people_info,assess_survey_info,organization):
#     s = paramiko.SSHClient()
#     # 取消安全认证
#     s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#     # 连接linux
#     # s.connect(hostname=hostname, username=username, password=password)
#     s.connect(hostname='47.99.72.229', username='wd', password='wdGl@@01*')
#     # 执行命令
#     stdin, stdout, stderr = s.exec_command('ls')
#     # 读取执行结果
#     result = stdout.read().split('\n')
#     print(result)
#
#     for i in result:
#         if 'txt' in i:
#             s.exec_command('rm -f  %s' % i)
#
#     # 写入信息
#     t = datetime.now().strftime('%Y-%m-%d')
#     for i in people_survey_info:
#         s.exec_command('echo %s >> people_survey_info.txt' % (str(i)[1:-1]))
#     command = "load data local inpath %s INTO TABLE weidudb.people_survey_info PARTITION (statis_date=%s);" % ('people_survey_info.txt', t)
#     s.exec_command(command)
#
#     for i in people_info:
#         s.exec_command('echo %s >> people_info.txt' % (str(i)[1:-1]))
#     command = "load data local inpath %s INTO TABLE weidudb.people_info PARTITION (statis_date=%s);" % ('people_info', t)
#     s.exec_command(command)
#
#     for i in assess_survey_info:
#         s.exec_command('echo %s >> assess_survey_info.txt' % (str(i)[1:-1]))
#     command = "load data local inpath %s INTO TABLE weidudb.assess_survey_info PARTITION (statis_date=%s);" % ('assess_survey_info', t)
#     s.exec_command(command)
#
#     for i in organization:
#         s.exec_command('echo %s >> organization.txt' % (str(i)[1:-1]))
#     command = "load data local inpath %s INTO TABLE weidudb.organization PARTITION (statis_date=%s);" % ('organization', t)
#     s.exec_command(command)
#
#     # 关闭linux连接
#     s.close()
#     # 返回执行结果
#     return result
#
#
# # 调用模块，传入liunx的ip/用户名/密码，并打印返回结果
# # con_linux(hostname='47.98.34.126', username='wd', password='wdGl@@01*')
# # content = [99,00,88,99]
# # con_linux(content)
#
