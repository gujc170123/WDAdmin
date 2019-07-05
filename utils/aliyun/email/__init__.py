# -*- coding:utf-8 -*-
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email.header import Header
from WeiDuAdmin import settings
from utils.logger import err_c_logger, info_c_logger

username = 'system@iwedoing.com'
password = 'gl1234567'
replyto = ''

class EmailUtils(object):

    def __init__(self):
        pass

    def __send_email(self, subject, nickname, content, receive_emails, is_text=True):
        info_c_logger.info("mail client start")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header(subject).encode()
        msg['From'] = '%s <%s>' % (Header(nickname).encode(), username)
        msg['To'] = receive_emails
        msg['Reply-to'] = replyto
        msg['Message-id'] = email.utils.make_msgid()
        msg['Date'] = email.utils.formatdate()
        if is_text:
            textplain = MIMEText(content, _subtype='plain', _charset='UTF-8')
            msg.attach(textplain)
        else:
            texthtml = MIMEText(content, _subtype='html', _charset='UTF-8')
            msg.attach(texthtml)
        try:
            client = smtplib.SMTP('mail.iwedoing.com',587)
            client.starttls()
            client.login(username, password)
            client.sendmail(username, receive_emails, msg.as_string())
            client.close()
            info_c_logger.info("mail sent")
        except smtplib.SMTPConnectError, e:
            err_c_logger.error("邮件发送失败，连接失败:%s,%s" % (e.smtp_code, e.smtp_error))
        except smtplib.SMTPAuthenticationError, e:
            err_c_logger.error("邮件发送失败，认证错误:%s,%s" % (e.smtp_code, e.smtp_error))
        except smtplib.SMTPSenderRefused, e:
            err_c_logger.error("邮件发送失败，发件人被拒绝:%s,%s" % (e.smtp_code, e.smtp_error))
        except smtplib.SMTPRecipientsRefused, e:
            err_c_logger.error("邮件发送失败，收件人被拒绝:%s" % (e.recipients))
        except smtplib.SMTPDataError, e:
            err_c_logger.error("邮件发送失败，数据接收拒绝:%s,%s" % (e.smtp_code, e.smtp_error))
        except smtplib.SMTPException, e:
            err_c_logger.error("邮件发送失败:%s" % (e.message))
        except Exception, e:
            err_c_logger.error(e)

    def send_active_code(self, code, receive_email):
        subject = u"格略维度平台激活码"
        context = u'''
<p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
    您好，
</p>
<p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
    感谢您使用格略维度平台，您的激活码是: %s.
    测评平台地址是：%s/#/login/loginCode
</p> 
''' % (code, settings.CLIENT_HOST)
        self.__send_email(subject, u"维度平台", context, receive_email, False)

    def send_general_code(self, code, receive_email):
        subject = u"格略维度平台验证码"
        context = u'''
<p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
    您好，
</p>
<p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
    感谢您使用格略维度平台，您的验证码是: %s.
</p> 
''' % code
        self.__send_email(subject, u"维度平台", context, receive_email, False)

    def send_general_survey_notice(self, survey_name, receive_email):
        subject = u"格略维度平台测验通知"
        context = u'''
<p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
    您好，
</p>
<p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
    您收到一份测验问卷：%s
</p> 
''' % survey_name
        self.__send_email(subject, u"维度平台", context, receive_email, False)

    def send_oss_report_path(self, path, receive_email):
            subject = u"格略维度平台报告"
            context = u'''
    <p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
        您好，
    </p>
    <p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
        感谢您使用格略维度平台, 报告下载已完成
        报告下载链接是 %s
    </p> 
    ''' % path
            self.__send_email(subject, u"维度平台", context, receive_email, False)

    def send_oss_people_list(self, path, receive_email):
            subject = u"格略维度平台名单"
            context = u'''
    <p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
        您好，
    </p>
    <p data-spm-anchor-id="5176.2020520150.112.i5.5a237528qmyTsk">
        感谢您使用格略维度平台, 名单下载已完成
        名单下载链接是 %s
    </p> 
    ''' % path
            self.__send_email(subject, u"维度平台", context, receive_email, False)