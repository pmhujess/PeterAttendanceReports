import os
import requests
import base64
import urllib.parse
import re
import smtplib
import csv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify
import pandas as pd  # Ensure Pandas is imported

# Flask app setup
app = Flask(__name__)

# Zoom API Credentials (Replace with actual credentials)
ZOOM_ACCOUNT_ID = "bVpWBvoVTdeRlnfMBxfTJQ"
ZOOM_CLIENT_ID = "jAlEOB2cRHugcQt2bTjGAA"
ZOOM_CLIENT_SECRET = "s6VQLn3iHqgXfcUPRLikX9UIMvQgzg7N"
BASE_URL = 'https://api.zoom.us/v2'
TARGET_DAYS = [0, 1]  # Monday = 0, Tuesday = 1
TARGET_START_HOUR = 5  # 5 AM EST
TARGET_END_HOUR = 9  # 9 AM EST

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "jessica@pmhu.org"  # 🔹 Change this
SENDER_PASSWORD = "zeaj jskj lfsf rvld"  # 🔹 Change this (Use App Password)
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "jessica@pmhu.org")  # Uses default if not set # 🔹 Change this

# 🔹 Function: Get Zoom API Access Token
def get_zoom_access_token():
    url = "https://zoom.us/oauth/token"
    payload = {"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}
    headers = {"Authorization": f"Basic {get_basic_auth_token()}", "Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get access token: {response.text}")

# 🔹 Function: Encode API Credentials
def get_basic_auth_token():
    credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
    return base64.b64encode(credentials.encode()).decode()

# 🔹 Function: Get Zoom User ID
def get_zoom_user_id():
    url = f"{BASE_URL}/users/me"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("id")
    else:
        raise Exception(f"Failed to fetch user ID: {response.text}")

# 🔹 Function: Get Zoom Meetings from the Past Week
def get_recent_meetings():
    zoom_user_id = get_zoom_user_id()
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    url = f"{BASE_URL}/report/users/{zoom_user_id}/meetings?from={one_week_ago}&to={today}"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        meetings = response.json().get("meetings", [])
        filtered_meetings = []
        
        for meeting in meetings:
            start_time_str = meeting.get("start_time", "")
            if start_time_str:
                start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                est_time = start_time.astimezone(timezone(timedelta(hours=-5)))  # Convert UTC to EST
                if est_time.weekday() in TARGET_DAYS and TARGET_START_HOUR <= est_time.hour < TARGET_END_HOUR:
                    filtered_meetings.append(meeting["uuid"])
        
        return filtered_meetings
    else:
        raise Exception(f"Failed to fetch meetings: {response.text}")

# 🔹 Function: Get Participants of a Meeting
def get_zoom_meeting_report(meeting_uuid):
    encoded_uuid = urllib.parse.quote(meeting_uuid, safe='')
    url = f"{BASE_URL}/report/meetings/{encoded_uuid}/participants"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get('participants', [])
    else:
        raise Exception(f"Failed to fetch report: {response.text}")

# 🔹 Function: Sanitize Filename (Remove Special Characters)
def sanitize_filename(filename):
    return re.sub(r'[\/:*?"<>|]', '_', filename)  # Replaces invalid characters with `_`

# 🔹 Function: Save Report to CSV with Corrected Duration
# Modified save_report_to_csv function
def save_report_to_csv(participants, filename):
    """
    Processes Zoom participant data to match the official Zoom report format:
    - Keeps original names
    - Calculates total duration in minutes
    - Handles cases where the same person joins multiple times
    """
    # Convert raw participant data to a DataFrame
    df = pd.DataFrame(participants)
    
    if df.empty:
        print("No participants found.")
        return

    # Ensure correct data types for time calculations
    df['join_time'] = pd.to_datetime(df['join_time'])
    df['leave_time'] = pd.to_datetime(df['leave_time'])
    
    # Calculate duration in minutes for each session
    df['duration'] = (df['leave_time'] - df['join_time']).dt.total_seconds() / 60
    
    # Group by name (not email) to match Zoom's format
    # Use the original name as provided by Zoom
    grouped_df = df.groupby('name', as_index=False).agg({
        'duration': 'sum',  # Sum up all time in the meeting
        'user_email': 'first'  # Keep the email if available
    })
    
    # Rename columns to match Zoom format
    grouped_df = grouped_df.rename(columns={
        'name': 'Name (original name)',
        'duration': 'Total duration (minutes)',
        'user_email': 'Email'
    })
    
    # Round duration to whole numbers
    grouped_df['Total duration (minutes)'] = grouped_df['Total duration (minutes)'].round(0).astype(int)
    
    # Reorder columns to match Zoom format
    columns = ['Name (original name)', 'Email', 'Total duration (minutes)']
    grouped_df = grouped_df[columns]
    
    # Save to CSV without index
    grouped_df.to_csv(filename, index=False)
    print(f"Report saved successfully: {filename}")

# 🔹 Function: Send Email Report
def send_email_report(to_email, subject, body, attachment_path):
    message = MIMEMultipart()
    message['From'] = SENDER_EMAIL
    message['To'] = to_email
    message['Subject'] = subject
    message.attach(MIMEText(body, "plain"))

    # Attach CSV Report
    with open(attachment_path, "rb") as attachment:
        part = MIMEApplication(attachment.read(), Name=attachment_path)
        part['Content-Disposition'] = f'attachment; filename="{attachment_path}"'
        message.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, message.as_string())

# 🔹 Function: Home Page Route
@app.route('/')
def home():
    return "Flask App is Running! Try /run-report"

# 🔹 Function: Run Zoom Report & Email
@app.route('/run-report', methods=['GET'])
def run_report():
    try:
        meeting_uuids = get_recent_meetings()
        if not meeting_uuids:
            return jsonify({"status": "No meetings found in target range."})

        for meeting_uuid in meeting_uuids:
            sanitized_uuid = sanitize_filename(meeting_uuid)  # 🔹 Sanitize filename
            report_filename = f"zoom_report_{sanitized_uuid}.csv"

            participants = get_zoom_meeting_report(meeting_uuid)
            if participants:
                save_report_to_csv(participants, report_filename)
                send_email_report(RECIPIENT_EMAIL, f"Zoom Report - {meeting_uuid}", "Attached is the Zoom meeting report.", report_filename)

        return jsonify({"status": "Report Generated & Emailed!", "meetings_processed": len(meeting_uuids)})

    except Exception as e:
        return jsonify({"error": str(e)})
