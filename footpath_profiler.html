"""
Footpath Profiler — Drive Upload Proxy
=======================================
Receives base64 images from the browser app and uploads them to Google Drive
using a service account. No OAuth needed for field surveyors.

Environment variables required (set in Render dashboard):
  GOOGLE_SERVICE_ACCOUNT_JSON   Full JSON content of your service account key file
  DRIVE_FOLDER_ID               Google Drive folder ID to upload images into
  ALLOWED_ORIGIN                Your app's origin, e.g. * or https://yoursite.com
"""

import os, json, base64, tempfile, logging
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

SCOPES        = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID     = os.environ.get('DRIVE_FOLDER_ID', '1TJ3DiFYcMVRyX58CAh0LN5ZlEhyvXQXX')
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')


def get_drive_service():
    raw = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not raw:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set')
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)


def cors(response):
    response.headers['Access-Control-Allow-Origin']  = ALLOWED_ORIGIN
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.after_request
def add_cors(response):
    return cors(response)


@app.route('/ping', methods=['GET', 'OPTIONS'])
def ping():
    return jsonify({'ok': True, 'message': 'Footpath Profiler image proxy running'})


@app.route('/upload', methods=['OPTIONS'])
def upload_preflight():
    return cors(jsonify({'ok': True}))


@app.route('/upload', methods=['POST'])
def upload():
    try:
        payload = request.get_json(force=True)
        name    = payload.get('name', 'image.jpg')
        data    = payload.get('data')          # base64 string (no data: prefix)
        folder  = payload.get('folderId', FOLDER_ID)

        if not data:
            return jsonify({'ok': False, 'error': 'No image data provided'}), 400

        # Decode base64 → temp file
        image_bytes = base64.b64decode(data)
        suffix = '.jpg' if name.endswith('.jpg') else '.png'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            service = get_drive_service()
            file_metadata = {
                'name': name,
                'parents': [folder]
            }
            media = MediaFileUpload(tmp_path, mimetype='image/jpeg', resumable=False)
            uploaded = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            # Make file viewable by anyone with the link
            service.permissions().create(
                fileId=uploaded['id'],
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()

            logging.info(f"Uploaded {name} → {uploaded['id']}")
            return jsonify({
                'ok':   True,
                'id':   uploaded['id'],
                'url':  uploaded.get('webViewLink', ''),
                'name': name
            })

        finally:
            os.unlink(tmp_path)

    except Exception as e:
        logging.error(f"Upload error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
