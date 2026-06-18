import os
import requests
from api_test_utils import make_unique_body

import pytest
BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

def test_post_system_user_profile_resetpwd_case_1():
    url = f"{BASE_URL}/system/user/profile/resetPwd"
    headers = {'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}
    payload = {}
    payload = make_unique_body(payload)
    response = requests.post(url, json=payload, headers=headers or None, timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data.get('code') == 200


# 正常基线用例：每个接口至少保留一条，日志存在多个成功样本时可扩展多条。
from api_test_utils import make_unique_body

AUTO_NORMAL_CASES = [{'id': 'normal_baseline', 'path_params': {}, 'query_params': {'oldPassword': 'demo', 'newPassword': 'demo'}, 'body': {}, 'headers': {'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}, 'actual_path': '', 'expected_status': 200, 'expected_body': {'code': 200}}]

@pytest.mark.parametrize("case", AUTO_NORMAL_CASES, ids=[c['id'] for c in AUTO_NORMAL_CASES])
def test_auto_normal_post_system_user_profile_resetpwd(case):
    url_path = '/system/user/profile/resetPwd'
    if case.get('actual_path'):
        url_path = case.get('actual_path')
    else:
        for key, value in case.get('path_params', {}).items():
            url_path = url_path.replace('{' + str(key) + '}', str(value))
    url = f'{BASE_URL}{url_path}'
    payload = make_unique_body(case.get('body') or {})
    response = requests.post(url, params=case.get('query_params') or None, json=payload, headers=case.get('headers') or None, timeout=10)
    assert response.status_code == int(case.get('expected_status') or 200)
    expected_body = case.get('expected_body') or {}
    if isinstance(expected_body, dict) and 'code' in expected_body:
        data = response.json()
        assert data.get('code') == expected_body.get('code')
