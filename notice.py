from email import message
from http import client
import boto3
from botocore.exceptions import ClientError
import datetime
import json

AWS_REGION = 'us-east-1'

iam_client = boto3.client('iam')
ses_client = boto3.client('ses',region_name=AWS_REGION)

def list_access_key(user, days_filter, status_filter):
    keydetails = iam_client.list_access_keys(UserName = user)
    user_iam_details = []
    
    # Some user may have 2 access keys.
    for keys in keydetails['AccessKeyMetadata']:
        key_info = {}
        if (days:=time_diff(keys['CreateDate'])) >= days_filter and keys['Status'] == status_filter:
            key_info['UserName'] = keys['UserName']
            key_info['AccessKeyId'] = keys['AccessKeyId']
            key_info['days'] = days
            key_info['status'] = keys['Status']
            user_iam_details.append(key_info)
    
    return user_iam_details

def time_diff(keycreatedtime):
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = now-keycreatedtime
    return diff.days

def create_key(username):
    access_key_metadata = iam_client.create_access_key(UserName=username)
    access_key = access_key_metadata['AccessKey']['AccessKeyId']
    secret_key = access_key_metadata['AccessKey']['SecretAccessKey']

def disable_key(access_key, username):
    try:
        iam_client.update_access_key(UserName=username, AccessKeyId=access_key, Status='Inactive')
        print(access_key + ' has been disabled.')
    except ClientError as e:
        print('The access key with id %s cannot be found' % access_key)

def delete_key(access_key, username):
    try:
        iam_client.delete_access_key(UserName=username, AccessKeyId=access_key)
        print (access_key + ' has been deleted.')
    except ClientError as e:
        print('The access key with id %s cannot be found' % access_key)

def send_email(username, subject, message):
    SENDER = ''
    RECIPIENT = username + 'email.com'
    SUBJECT = subject

    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = (message)
                         
    CHARSET = "UTF-8"

    try:
        #Provide the contents of the email.
        response = ses_client.send_email(
            Destination={
                'ToAddresses': [
                    RECIPIENT,
                ],
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': CHARSET,
                        'Data': BODY_TEXT,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': SUBJECT,
                },
            },
            Source=SENDER,
            
        )
    # Display an error if something goes wrong. 
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])

def sanitize_users(user_list, group_name, trial):
    for user in user_list:
        userGroups = iam_client.list_groups_for_user(UserName=user)
        for groupName in userGroups['Groups']:
            if groupName['GroupName'] == group_name:
                print(user + ' [ServiceAccount user]')
                user_list.remove(user) 
            else:
                continue 
    print('============================================')
    print( trial + ': ' + str(len(user_list)) + ' users sanitized!')
    print('============================================')
    return(user_list)    

def get_users():
    user_list=[]
    for userlist in iam_client.list_users(MaxItems=250)['Users']:
        user_list.append(userlist['UserName'])
    # Sanitizing users to remove service account users
    first_try = sanitize_users(user_list, "NonProductionCrossAccountServiceAccounts", "First Try")
    # Repeat sanitizing process to ensure no service account user is included
    second_try = sanitize_users(first_try, "NonProductionCrossAccountServiceAccounts", "Second Try")
    user_list = second_try
    return user_list

def reminder(days_used, days_left):
    for user in get_users():
        user_iam_details = list_access_key(user = user, days_filter = days_used, status_filter = 'Active')
        for _ in user_iam_details:
            username = _['UserName']
            subject = "Update Your Access keys Test"
            message = ('Dear '+ username  + '\r\n\n'
                        'Please be informed your current IAM Access Key with be disabled and delete in ' + days_left  + ' days, based  on  the 90 days key rotation policy \r\n\n'
                        'To avoid  disconnection from AWS, kindly login to console and  create a new access key \r\n\n'
                        'Thanks')
            send_email(username, subject, message)          
            
    return {
        'statusCode': 200
    }

def lambda_handler():
    for user in get_users():
        user_iam_details = list_access_key(user = user, days_filter = 90, status_filter = 'Active')
        for _ in user_iam_details:
            disable_key(access_key=_['AccessKeyId'], username=_['UserName'])
            delete_key(access_key=_['AccessKeyId'], username=_['UserName'])
            username = _['UserName']
            subject = 'Update Your AWS Access key'
            message = ('Dear '+ username  + '\r\n\n'
                        'Please be informed your current IAM Access Key has been disabled and deleted, based  on  the 90 days key rotation policy \r\n\n'
                        'kindly login to console and  create a new access key \r\n\n'
                        'Thanks')
            send_email(username, subject, message)
            
            
    return {
        'statusCode': 200
    }

def main():
    reminder(80, '10')
    reminder(85, '5')
    lambda_handler()

if __name__ == "__main__":
    main()