import requests
import csv
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime

# Zoom API Credentials
ZOOM_ACCOUNT_ID = "bVpWBvoVTdeRlnfMBxfTJQ"
ZOOM_CLIENT_ID = "jAlEOB2cRHugcQt2bTjGAA"
ZOOM_CLIENT_SECRET = "s6VQLn3iHqgXfcUPRLikX9UIMvQgzg7N"
BASE_URL = 'https://api.zoom.us/v2'

def get_zoom_access_token():
    url = "https://zoom.us/oauth/token"
    payload = {
        "grant_type": "account_credentials",
        "account_id": ZOOM_ACCOUNT_ID
    }
    headers = {
        "Authorization": f"Basic {get_basic_auth_token()}",
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

def get_zoom_meeting_report(meeting_id):
    url = f"{BASE_URL}/report/meetings/{meeting_id}/participants"
    headers = {
        "Authorization": f"Bearer {get_zoom_access_token()}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()['participants']
    else:
        raise Exception(f"Failed to fetch report: {response.status_code}, {response.text}")

def save_report_to_csv(participants, filename="zoom_report.csv"):
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
        part = MIMEApplication(attachment.read(), Name="zoom_report.csv")
    part['Content-Disposition'] = f'attachment; filename="zoom_report.csv"'
    message.attach(part)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, message.as_string())

if __name__ == "__main__":
    meeting_id = "2834539727"
    participants = get_zoom_meeting_report(meeting_id)

    report_filename = f"zoom_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    save_report_to_csv(participants, report_filename)

    recipient_email = "jessicaboykin@gmail.com"
    email_subject = "Zoom Meeting Usage Report"
    email_body = "Please find attached the usage report for the recent Zoom meeting."

    send_email_report(recipient_email, email_subject, email_body, report_filename)

    print("Report emailed successfully!")
