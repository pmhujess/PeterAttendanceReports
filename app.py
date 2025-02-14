from flask import Flask, jsonify
import os
import requests
import csv
import base64
import urllib.parse
import re
from datetime import datetime, timedelta, timezone

# Zoom API Credentials
ZOOM_ACCOUNT_ID = "bVpWBvoVTdeRlnfMBxfTJQ"
ZOOM_CLIENT_ID = "jAlEOB2cRHugcQt2bTjGAA"
ZOOM_CLIENT_SECRET = "s6VQLn3iHqgXfcUPRLikX9UIMvQgzg7N"
BASE_URL = 'https://api.zoom.us/v2'
TARGET_DAYS = [0, 1]  # Monday = 0, Tuesday = 1
TARGET_START_HOUR = 5  # 5 AM EST
TARGET_END_HOUR = 9  # 9 AM EST

app = Flask(__name__)

def get_zoom_access_token():
    url = "https://zoom.us/oauth/token"
    payload = {"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}
    headers = {"Authorization": f"Basic {get_basic_auth_token()}", "Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers)
    return response.json()["access_token"] if response.status_code == 200 else None

def get_basic_auth_token():
    credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
    return base64.b64encode(credentials.encode()).decode()

def get_zoom_user_id():
    url = f"{BASE_URL}/users/me"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    return response.json().get("id") if response.status_code == 200 else None

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
    return []

@app.route('/run-report', methods=['GET'])
def run_report():
    meeting_uuids = get_recent_meetings()
    for meeting_uuid in meeting_uuids:
        participants = get_zoom_meeting_report(meeting_uuid)
        if participants:
            filename = f"zoom_report_{meeting_uuid}.csv"
            save_report_to_csv(participants, filename)
            # You can modify this to use a real email service like SendGrid
            send_email_report("jessicaboykin@gmail.com", "Zoom Report", "Attached report", filename)
    return jsonify({"status": "Report Generated & Emailed", "meetings_processed": len(meeting_uuids)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
