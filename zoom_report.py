import requests
import csv
import smtplib
import base64
import urllib.parse
import re
import os
from flask import Flask, request, jsonify
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta, timezone

# Initialize Flask app
app = Flask(__name__)

@app.route("/")
def home():
    return "Zoom Report Bot is running successfully!"

# Zoom API Credentials
ZOOM_ACCOUNT_ID = "bVpWBvoVTdeRlnfMBxfTJQ"
ZOOM_CLIENT_ID = "jAlEOB2cRHugcQt2bTjGAA"
ZOOM_CLIENT_SECRET = "s6VQLn3iHqgXfcUPRLikX9UIMvQgzg7N"
BASE_URL = 'https://api.zoom.us/v2'
TARGET_DAYS = [0, 1]  # Monday = 0, Tuesday = 1
TARGET_START_HOUR = 5  # 5 AM EST
TARGET_END_HOUR = 9  # 9 AM EST
SLACK_VERIFICATION_TOKEN = "your_slack_verification_token"


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

def sanitize_filename(filename):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', filename)

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
        filtered_meetings = []
        
        for meeting in meetings:
            start_time_str = meeting.get("start_time", "")
            if not start_time_str:
                continue
            
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            est_time = start_time.astimezone(timezone(timedelta(hours=-5)))  # Convert UTC to EST
            
            if est_time.weekday() in TARGET_DAYS and TARGET_START_HOUR <= est_time.hour < TARGET_END_HOUR:
                filtered_meetings.append(meeting["uuid"])
        
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

@app.route("/slack", methods=["POST"])
def slack_command():
    data = request.form
    if data.get("token") != SLACK_VERIFICATION_TOKEN:
        return jsonify({"error": "Invalid request"}), 403
    
    meeting_uuids = get_recent_meetings()
    for meeting_uuid in meeting_uuids:
        participants = get_zoom_meeting_report(meeting_uuid)

        if participants:
            sanitized_uuid = sanitize_filename(meeting_uuid)
            report_filename = f"zoom_report_{sanitized_uuid}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
            save_report_to_csv(participants, report_filename)
            
            return jsonify({"text": f"Report for meeting {sanitized_uuid} generated successfully!"})
    
    return jsonify({"text": "No meetings found in the specified timeframe."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
