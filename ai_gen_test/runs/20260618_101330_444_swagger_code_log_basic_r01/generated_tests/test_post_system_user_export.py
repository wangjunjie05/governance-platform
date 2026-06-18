import os
import requests

BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

def test_post_system_user_export_download():
    url = f"{BASE_URL}/system/user/export"
    headers = {'Accept': '*/*', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}
    response = requests.post(url, headers=headers or None, timeout=30)
    assert response.status_code == 200
    assert response.content is not None
