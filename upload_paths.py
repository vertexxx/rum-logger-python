import os


def get_uploads_dir():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "uploads")


def ensure_uploads_dir():
    uploads_dir = get_uploads_dir()
    os.makedirs(uploads_dir, exist_ok=True)
    return uploads_dir
