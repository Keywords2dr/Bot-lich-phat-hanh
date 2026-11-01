import sys
import mimetypes
from pathlib import Path
from drive import get_service, get_or_create_folder, upload

publisher, month, path = sys.argv[1], sys.argv[2], Path(sys.argv[3])
mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"

service = get_service()
root = get_or_create_folder(service, "Lich phat hanh")
pub = get_or_create_folder(service, publisher, root)
folder = get_or_create_folder(service, month, pub)
result = upload(service, folder, path.name, path.read_bytes(), mime)
print("OK:", result["webViewLink"])