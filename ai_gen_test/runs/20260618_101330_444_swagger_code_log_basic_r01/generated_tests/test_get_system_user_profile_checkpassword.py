import pytest
import requests
from io import BytesIO

import os
BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

@pytest.mark.parametrize(
    "password, expected_status_code, response_body",
    [
        ("wrong_password", 403, {"code": 1001, "message": "密码错误"}),
        ("correct_password", 200, {"code": 0, "message": "OK"})
    ]
)
def test_checkPassword(password, expected_status_code, response_body):
    url = f"{BASE_URL}/system/user/profile/checkPassword"
    headers = {
        "Cookie": "JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc"
    }
    
    response = requests.get(url, params={"password": password}, headers=headers)
    response_json = response.json()
    
    assert response.status_code == expected_status_code
    assert response_json["code"] == response_body["code"]
    if "message" in response_body:
        assert response_json["message"] == response_body["message"]

def test_checkPassword_invalid_password():
    url = f"{BASE_URL}/system/user/profile/checkPassword"
    headers = {
        "Cookie": "JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc"
    }
    
    response = requests.get(url, params={"password": "invalid_password"}, headers=headers)
    assert response.status_code == 403
