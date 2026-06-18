import os
import requests

import pytest
BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

def test_post_system_user_authrole_insertauthrole_case_1():
    url = f"{BASE_URL}/system/user/authRole/insertAuthRole"
    headers = {'Accept': 'application/json, text/javascript, */*; q=0.01', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}
    payload = {'userId': '116', 'roleIds': '2,100'}
    response = requests.post(url, json=payload, headers=headers or None, timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data.get('code') == 0


# 以下异常用例由程序根据 DTO 校验注解和接口参数规则自动扩展。
AUTO_EXCEPTION_CASES = [{'id': 'ex_1_invalid_type_userid', 'description': '参数 userId 类型错误', 'exception_type': 'invalid_type', 'path_params': {}, 'query_params': {'userId': 'abc'}, 'body': {'userId': '116', 'roleIds': '2,100'}, 'headers': {'Accept': 'application/json, text/javascript, */*; q=0.01', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}, 'expected_status': 400, 'actual_path': '/system/user/authRole/insertAuthRole'}]

@pytest.mark.parametrize("case", AUTO_EXCEPTION_CASES, ids=[c['id'] for c in AUTO_EXCEPTION_CASES])
def test_auto_exception_post_system_user_authrole_insertauthrole(case):
    url_path = '/system/user/authRole/insertAuthRole'
    for key, value in case.get('path_params', {}).items():
        url_path = url_path.replace('{' + str(key) + '}', str(value))
    if case.get('actual_path'):
        url_path = case.get('actual_path')
    url = f'{BASE_URL}{url_path}'
    response = requests.post(url, params=case.get('query_params') or None, json=case.get('body') or {}, headers=case.get('headers') or None, timeout=10)
    # 异常用例兼容两类错误响应：HTTP 4xx/5xx，或 HTTP 200 但业务 code 非 200。
    def _is_error_response(resp):
        if resp.status_code >= 400:
            return True
        try:
            data = resp.json()
        except Exception:
            return False
        if not isinstance(data, dict) or 'code' not in data:
            return False
        code = data.get('code')
        try:
            return int(code) != 200
        except Exception:
            return str(code).strip() not in {'', '200'}
    assert _is_error_response(response), f'异常用例未进入错误响应，HTTP={response.status_code}, body={response.text[:500]}'
