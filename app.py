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
from flask import Flask, jsonify, render_template, request
import pandas as pd
import pytz

# Flask app setup
app = Flask(__name__)

# Zoom API Credentials
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
SENDER_EMAIL = "jessica@pmhu.org"
SENDER_PASSWORD = "zeaj jskj lfsf rvld"
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "jessica@pmhu.org")

def get_zoom_access_token():
    url = "https://zoom.us/oauth/token"
    payload = {"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}
    headers = {"Authorization": f"Basic {get_basic_auth_token()}", "Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get access token: {response.text}")

def get_basic_auth_token():
    credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
    return base64.b64encode(credentials.encode()).decode()

def get_zoom_user_id():
    url = f"{BASE_URL}/users/me"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("id")
    else:
        raise Exception(f"Failed to fetch user ID: {response.text}")

def get_recent_meetings(start_date=None, end_date=None):
    zoom_user_id = get_zoom_user_id()
    
    # If no dates provided, use default 7-day range
    if not start_date:
        start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    url = f"{BASE_URL}/report/users/{zoom_user_id}/meetings?from={start_date}&to={end_date}"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        meetings = response.json().get("meetings", [])
        filtered_meetings = []
        
        for meeting in meetings:
            start_time_str = meeting.get("start_time", "")
            if start_time_str:
                start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                est_time = start_time.astimezone(pytz.timezone('US/Eastern'))
                if est_time.weekday() in TARGET_DAYS and TARGET_START_HOUR <= est_time.hour < TARGET_END_HOUR:
                    filtered_meetings.append((meeting["uuid"], est_time))
        
        return filtered_meetings
    else:
        raise Exception(f"Failed to fetch meetings: {response.text}")

def get_zoom_meeting_report(meeting_uuid):
    encoded_uuid = urllib.parse.quote(meeting_uuid, safe='')
    url = f"{BASE_URL}/report/meetings/{encoded_uuid}/participants"
    headers = {"Authorization": f"Bearer {get_zoom_access_token()}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get('participants', [])
    else:
        raise Exception(f"Failed to fetch report: {response.text}")

def sanitize_filename(filename):
    return re.sub(r'[\/:*?"<>|]', '_', filename)

def save_report_to_csv(participants, filename):
    df = pd.DataFrame(participants)
    
    if df.empty:
        print("No participants found.")
        return None, None, 0

    # Ensure correct data types for time calculations
    df['join_time'] = pd.to_datetime(df['join_time'])
    df['leave_time'] = pd.to_datetime(df['leave_time'])
    
    # Calculate duration in minutes for each session
    df['duration'] = (df['leave_time'] - df['join_time']).dt.total_seconds() / 60
    
    # Group by name with required aggregations
    grouped_df = df.groupby('name', as_index=False).agg({
        'duration': 'sum',
        'user_email': 'first',
        'join_time': 'min'
    })
    
    # Handle timezone conversion
    grouped_df['join_time'] = pd.to_datetime(grouped_df['join_time']).dt.tz_convert('US/Eastern')
    grouped_df['First Join Time (EST)'] = grouped_df['join_time'].dt.strftime('%Y-%m-%d %I:%M %p')
    
    # Sort by join time
    grouped_df = grouped_df.sort_values('join_time')
    
    # Get meeting date and earliest join time for email subject
    meeting_date = grouped_df['join_time'].iloc[0].strftime('%Y-%m-%d')
    earliest_join = grouped_df['join_time'].iloc[0].strftime('%I:%M %p')
    participant_count = len(grouped_df)
    
    # Rename columns to match Zoom format
    grouped_df = grouped_df.rename(columns={
        'name': 'Name (original name)',
        'duration': 'Total duration (minutes)',
        'user_email': 'Email'
    })
    
    # Round duration to whole numbers
    grouped_df['Total duration (minutes)'] = grouped_df['Total duration (minutes)'].round(0).astype(int)
    
    # Reorder columns
    columns = ['Name (original name)', 'Email', 'Total duration (minutes)', 'First Join Time (EST)']
    grouped_df = grouped_df[columns]
    
    # Save to CSV without index
    grouped_df.to_csv(filename, index=False)
    print(f"Report saved successfully: {filename}")
    
    return meeting_date, earliest_join, participant_count

def send_email_report(to_email, meeting_date, earliest_join, participant_count, body, attachment_path):
    message = MIMEMultipart()
    message['From'] = SENDER_EMAIL
    message['To'] = to_email
    message['Subject'] = f"Zoom Report - {meeting_date} {earliest_join} - {participant_count} Participants"
    message.attach(MIMEText(body, "plain"))

    with open(attachment_path, "rb") as attachment:
        part = MIMEApplication(attachment.read(), Name=attachment_path)
        part['Content-Disposition'] = f'attachment; filename="{attachment_path}"'
        message.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, message.as_string())

@app.route('/')
def home():
    return render_template('run_report.html')

@app.route('/run-report', methods=['GET', 'POST'])
def run_report():
    if request.method == 'GET':
        # Default date range
        end_date = datetime.now(pytz.timezone('US/Eastern'))
        start_date = end_date - timedelta(days=7)
        return render_template('run_report.html', 
                             start_date=start_date.strftime('%Y-%m-%d'),
                             end_date=end_date.strftime('%Y-%m-%d'),
                             default_email=RECIPIENT_EMAIL)

    try:
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        action = request.form.get('action', 'generate')  # 'generate' or 'send'
        
        if action == 'generate':
            # First step: Generate reports and return their info
            meetings = get_recent_meetings(start_date, end_date)
            if not meetings:
                return jsonify({"status": "No meetings found in target range."})

            reports_info = []
            for meeting_uuid, _ in meetings:
                sanitized_uuid = sanitize_filename(meeting_uuid)
                report_filename = f"zoom_report_{sanitized_uuid}.csv"

                participants = get_zoom_meeting_report(meeting_uuid)
                if participants:
                    meeting_date, earliest_join, participant_count = save_report_to_csv(participants, report_filename)
                    if meeting_date:
                        reports_info.append({
                            "filename": report_filename,
                            "subject": f"Zoom Report - {meeting_date} {earliest_join} - {participant_count} Participants",
                            "date": meeting_date,
                            "earliest_join": earliest_join,
                            "participants": participant_count
                        })

            return jsonify({
                "status": "Success!",
                "reports": reports_info
            })

        elif action == 'send':
            recipient_email = request.form.get('recipient_email')
            selected_reports = request.form.getlist('selected_reports[]')
    
            if not recipient_email:
                return jsonify({"error": "Recipient email is required"}), 400
            if not selected_reports:
                return jsonify({"error": "No reports selected"}), 400

            for report in selected_reports:
                try:
                    # Use json.loads instead of eval for safety
                    import json
                    report_data = json.loads(report)
                    
                    send_email_report(
                        recipient_email,
                        report_data['date'],
                        report_data['earliest_join'],
                        report_data['participants'],
                        "Attached is the Zoom meeting report.",
                        report_data['filename']
                    )
                except Exception as e:
                    print(f"Error sending report: {str(e)}")

            return jsonify({
                "status": "Success!",
                "message": f"Sent {len(selected_reports)} selected reports to {recipient_email}"
            })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    app.run(debug=True)