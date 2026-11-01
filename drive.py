import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_service():
    creds = Credentials(
        None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_or_create_folder(service, name, parent="root"):
    q = (
        f"name='{name}' and '{parent}' in parents "
        "and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id)").execute()
    if res["files"]:
        return res["files"][0]["id"]
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent],
    }
    return service.files().create(body=meta, fields="id").execute()["id"]


def upload(service, folder_id, filename, data, mime):
    media = MediaInMemoryUpload(data, mimetype=mime)
    meta = {"name": filename, "parents": [folder_id]}
    return service.files().create(
        body=meta, media_body=media, fields="id,webViewLink"
    ).execute()