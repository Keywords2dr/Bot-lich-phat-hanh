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


FOLDER_MIME = "application/vnd.google-apps.folder"


def escape_q(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def find_folder(service, name, parent="root"):
    q = (
        f"name='{escape_q(name)}' and '{parent}' in parents "
        f"and mimeType='{FOLDER_MIME}' and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id)").execute()
    return res["files"][0]["id"] if res["files"] else None


def create_folder(service, name, parent="root"):
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}
    return service.files().create(body=meta, fields="id").execute()["id"]


def get_or_create_folder(service, name, parent="root"):
    return find_folder(service, name, parent) or create_folder(service, name, parent)


def find_file(service, folder_id, names):
    cond = " or ".join(f"name='{escape_q(n)}'" for n in names)
    q = f"'{folder_id}' in parents and trashed=false and ({cond})"
    res = service.files().list(q=q, fields="files(id)").execute()
    return res["files"][0]["id"] if res["files"] else None


def upload(service, folder_id, filename, data, mime):
    media = MediaInMemoryUpload(data, mimetype=mime)
    meta = {"name": filename, "parents": [folder_id]}
    return service.files().create(
        body=meta, media_body=media, fields="id,webViewLink"
    ).execute()