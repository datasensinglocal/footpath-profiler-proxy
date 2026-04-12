"""
Footpath Profiler — Drive Upload Proxy
"""

import os, json, base64, tempfile, logging
from flask import Flask, request, jsonify, make_response
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

SCOPES    = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '1TJ3DiFYcMVRyX58CAh0LN5ZlEhyvXQXX')


def drive_service():
    raw = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not raw:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON not set')
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)


def cors_response(data, status=200):
    resp = make_response(jsonify(data), status)
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = '*'
    return resp


# Handle preflight OPTIONS for every route
@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        resp = make_response('', 204)
        resp.headers['Access-Control-Allow-Origin']  = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = '*'
        return resp


@app.route('/ping', methods=['GET', 'POST'])
def ping():
    return cors_response({'ok': True, 'message': 'Footpath Profiler proxy running'})


@app.route('/upload', methods=['POST'])
def upload():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        name    = payload.get('name', 'image.jpg')
        data    = payload.get('data')
        folder  = payload.get('folderId', FOLDER_ID)

        if not data:
            return cors_response({'ok': False, 'error': 'No image data'}, 400)

        image_bytes = base64.b64decode(data)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            svc  = drive_service()
            meta = {'name': name, 'parents': [folder]}
            media = MediaFileUpload(tmp_path, mimetype='image/jpeg', resumable=False)
            f = svc.files().create(body=meta, media_body=media, fields='id,webViewLink').execute()
            svc.permissions().create(
                fileId=f['id'],
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()
            logging.info(f"Uploaded {name} -> {f['id']}")
            return cors_response({'ok': True, 'id': f['id'], 'url': f.get('webViewLink',''), 'name': name})
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        logging.error(f"Upload error: {e}")
        return cors_response({'ok': False, 'error': str(e)}, 500)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
