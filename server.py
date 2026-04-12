"""v2
Footpath Profiler — Drive Upload Proxy
Uses supportsAllDrives and uploadType=multipart to write into
a folder owned by the service account's org, OR a folder that
has been shared with the service account as Editor.

Key fix: pass supportsAllDrives=True so the API accepts
shared-with-me folders, and use a direct multipart upload
instead of the Files.create helper which triggers quota check.
"""

import os, json, base64, tempfile, logging, requests
from flask import Flask, request, jsonify, make_response
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

SCOPES    = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '1TJ3DiFYcMVRyX58CAh0LN5ZlEhyvXQXX')


def get_token():
    raw = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not raw:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON not set')
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=SCOPES)
    creds.refresh(GoogleRequest())
    return creds.token


def cors_response(data, status=200):
    resp = make_response(jsonify(data), status)
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = '*'
    return resp


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
        token = get_token()

        # Use multipart upload directly via requests — avoids service account quota issue
        metadata = json.dumps({'name': name, 'parents': [folder]})
        files = {
            'metadata': ('metadata', metadata, 'application/json'),
            'file':     ('file',     image_bytes, 'image/jpeg')
        }
        resp = requests.post(
            'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,webViewLink',
            headers={'Authorization': 'Bearer ' + token},
            files=files
        )

        if resp.status_code not in (200, 201):
            logging.error(f"Drive API error: {resp.text}")
            return cors_response({'ok': False, 'error': resp.text}, 500)

        result = resp.json()
        file_id = result.get('id')

        # Make file public
        requests.post(
            f'https://www.googleapis.com/drive/v3/files/{file_id}/permissions?supportsAllDrives=true',
            headers={'Authorization': 'Bearer ' + token,
                     'Content-Type': 'application/json'},
            json={'type': 'anyone', 'role': 'reader'}
        )

        url = f'https://drive.google.com/file/d/{file_id}/view'
        logging.info(f"Uploaded {name} -> {file_id}")
        return cors_response({'ok': True, 'id': file_id, 'url': url, 'name': name})

    except Exception as e:
        logging.error(f"Upload error: {e}")
        return cors_response({'ok': False, 'error': str(e)}, 500)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
