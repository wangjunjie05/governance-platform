import os
import requests
from api_test_utils import make_unique_body

BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

def test_post_system_user_add_case_1():
    url = f"{BASE_URL}/system/user/add"
    headers = {'Accept': 'application/json, text/javascript, */*; q=0.01', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}
    payload = {'deptId': '', 'userName': '创维11', 'deptName': '', 'phonenumber': '', 'email': '', 'loginName': '创维11', 'password': '***', 'sex': '0', 'remark': '', 'status': '0', 'roleIds': '', 'postIds': ''}
    payload = make_unique_body(payload)
    response = requests.post(url, json=payload, headers=headers or None, timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data.get('code') == 0
