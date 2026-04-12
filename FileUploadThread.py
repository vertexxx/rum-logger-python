import os
import time
import threading
import urllib.request

import requests
import urllib3

from upload_paths import ensure_uploads_dir


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_system_proxies():
    proxy_environment_variables = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
    )
    if any(os.getenv(variable_name) for variable_name in proxy_environment_variables):
        return {}

    detected_proxies = urllib.request.getproxies()
    fallback_proxy = detected_proxies.get("all")
    proxies = {}
    for scheme in ("http", "https"):
        proxy_url = detected_proxies.get(scheme, fallback_proxy)
        if proxy_url:
            proxies[scheme] = proxy_url
    return proxies

class FileUploadThread(threading.Thread):
    def __init__(self, device_name, update_status_func, directory=None, backend_url=None):
        super().__init__()
        self.update_status_func = update_status_func
        self.directory = directory or ensure_uploads_dir()
        self.device_name = device_name
        self._stop_event = threading.Event()
        self.request_timeout_seconds = 30
        self.session = requests.Session()
        self.session.verify = False
        self.session.trust_env = True

        system_proxies = get_system_proxies()
        if system_proxies:
            self.session.proxies.update(system_proxies)
            print(f"Using system proxy configuration: {system_proxies}")

        self.backend_url=backend_url
        if backend_url==None:
            url = os.getenv('RUM_BACKEND')
            print("RUM_BACKEND: "+str(url))
            if url==None:
                update_status_func("uploads",f"%RUM_BACKEND% not set","red")
            else:
                if not url.endswith('/store.php'):
                    if url.endswith('/'):
                        url = url + 'store.php'
                    else:
                        url = url + '/store.php'
                self.backend_url = url
        else:
            self.backend_url = backend_url
        self.last_checked = time.time()

    def run(self):
        if self.backend_url==None:
            self.update_status_func("uploads",f"%RUM_BACKEND% not set","red")
        else:
            while not self._stop_event.is_set():
                try:
                    self.check_and_upload_files()
                except Exception as e:
                    self.update_status_func("uploads", f"failed", "red")
                    print(f"Failed to upload files: {e}")
                if self._stop_event.wait(5):
                    break

    def check_and_upload_files(self):
        current_time = time.time()
        for filename in os.listdir(self.directory):
            if self.device_name in filename:
                filepath = os.path.join(self.directory, filename)
                if os.path.isfile(filepath) and os.path.getmtime(filepath) > self.last_checked:
                    self.upload_file(filepath)
        self.last_checked = current_time

    def upload_file(self, filepath):
        if self.backend_url is None:
            self.update_status_func("uploads", "%RUM_BACKEND% not set", "red")
            return

        with open(filepath, 'rb') as f:
            files = {'file': f}
            response = self.session.post(
                self.backend_url,
                files=files,
                timeout=self.request_timeout_seconds,
            )
            if response.status_code == 200:
                self.update_status_func("uploads", "backend connected", "green")
            else:
                self.update_status_func("uploads", f"failed ({response.status_code})", "red")
                print(f"Failed to upload {filepath}, status code: {response.status_code}")

    def stop(self):
        self._stop_event.set()
        self.session.close()

# Usage
#device_name = "your_device_name"  # Replace with your actual device name
#backend_url = os.getenv('RUM_BACKEND') + 'store.php'
#file_upload_thread = FileUploadThread('./www', device_name, backend_url)
#file_upload_thread.start()