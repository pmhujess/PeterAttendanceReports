import requests
import csv
import smtplib
import base64
import urllib.parse
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta, timezone

# Zoom API Credentials
ZOOM_ACCOUNT_ID = "bVpWBvoVTdeRlnfMBxfTJQ"
ZOOM_CLIENT_ID = "jAlEOB2cRHugcQt2bTjGAA"
ZOOM_CLIENT_SECRET = "s6VQLn3iHqgXfcUPRLikX9UIMvQgzg7N"
BASE_URL = 'https://api.zoom.us/v2'
TARGET_DAYS = [0, 1]  # Monday = 0, Tuesday = 1
TARGET_START_HOUR = 5  # 5 AM EST
TARGET_END_HOUR = 9  # 9 AM EST

def get_zoom_access_token():
    url = "https://zoom.us/oauth/token"
    payload = {
        "grant_type": "account_credentials",
        "account_id": ZOOM_ACCOUNT_ID
    }
    headers = {
        "Authorization": f"Basic {get_basic_auth_token()}" ,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get access token: {response.status_code}, {response.text}")

def get_basic_auth_token():
    credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
    return base64.b64encode(credentials.encode()).decode()

def get_zoom_user_id():
    url = f"{BASE_URL}/users/me"
    headers = {
        "Authorization": f"Bearer {get_zoom_access_token()}" ,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("id")
    else:
        raise Exception(f"Failed to fetch user ID: {response.status_code}, {response.text}")

def sanitize_filename(filename):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', filename)

def get_recent_meetings():
    zoom_user_id = get_zoom_user_id()
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    url = f"{BASE_URL}/report/users/{zoom_user_id}/meetings?from={one_week_ago}&to={today}"
    headers = {
        "Authorization": f"Bearer {get_zoom_access_token()}" ,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        meetings = response.json().get("meetings", [])
        print(f"Total meetings retrieved: {len(meetings)}")  # Debugging
        
        # Print full meeting details for debugging
        for meeting in meetings:
            print(f"Raw Meeting Data: {meeting}")  # Debugging
        
        filtered_meetings = []
        
        for meeting in meetings:
            start_time_str = meeting.get("start_time", "")
            if not start_time_str:
                print(f"Skipping meeting {meeting['uuid']} due to missing start_time")
                continue
            
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            est_time = start_time.astimezone(timezone(timedelta(hours=-5)))  # Convert UTC to EST
            print(f"Meeting UUID: {meeting['uuid']}, Start Time EST: {est_time}")  # Debugging
            
            if est_time.weekday() in TARGET_DAYS and TARGET_START_HOUR <= est_time.hour < TARGET_END_HOUR:
                print(f"Meeting {meeting['uuid']} falls within target range.")  # Debugging
                filtered_meetings.append(meeting["uuid"])
        
        print(f"Filtered meetings count: {len(filtered_meetings)}")  # Debugging
        return filtered_meetings
    else:
        raise Exception(f"Failed to fetch meetings: {response.status_code}, {response.text}")

def get_zoom_meeting_report(meeting_uuid):
    encoded_uuid = urllib.parse.quote(meeting_uuid, safe='')
    url = f"{BASE_URL}/report/meetings/{encoded_uuid}/participants"
    headers = {
        "Authorization": f"Bearer {get_zoom_access_token()}" ,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()['participants']
    else:
        raise Exception(f"Failed to fetch report: {response.status_code}, {response.text}")

def save_report_to_csv(participants, filename):
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Name', 'Email', 'Join Time', 'Leave Time', 'Duration (mins)'])
        for p in participants:
            writer.writerow([p['name'], p['user_email'], p['join_time'], p['leave_time'], p['duration']])

def send_email_report(to_email, subject, body, attachment_path):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "jessica@pmhu.org"
    sender_password = "zeaj jskj lfsf rvld"

    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = to_email
    message['Subject'] = subject

    message.attach(MIMEText(body, "plain"))

    with open(attachment_path, "rb") as attachment:
        part = MIMEApplication(attachment.read(), Name=attachment_path)
    part['Content-Disposition'] = f'attachment; filename="{attachment_path}"'
    message.attach(part)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, message.as_string())

if __name__ == "__main__":
    meeting_uuids = get_recent_meetings()
    for meeting_uuid in meeting_uuids:
        participants = get_zoom_meeting_report(meeting_uuid)

        if participants:
            sanitized_uuid = sanitize_filename(meeting_uuid)
            report_filename = f"zoom_report_{sanitized_uuid}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
            save_report_to_csv(participants, report_filename)

            recipient_email = "jessicaboykin@gmail.com"
            email_subject = f"Zoom Meeting Usage Report - Meeting {sanitized_uuid}"
            email_body = f"Please find attached the usage report for Zoom meeting {sanitized_uuid}."

            send_email_report(recipient_email, email_subject, email_body, report_filename)

            print(f"Report for Meeting {sanitized_uuid} emailed successfully!")