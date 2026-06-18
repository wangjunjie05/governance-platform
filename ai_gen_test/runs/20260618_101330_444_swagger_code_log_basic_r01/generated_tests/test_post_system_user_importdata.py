import io
import os
import requests

import pytest
BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

def test_post_system_user_importdata_upload():
    url = f"{BASE_URL}/system/user/importData"
    headers = {'Accept': '*/*', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}
    files = {'file': ("import.xlsx", io.BytesIO(b"fake-file-content"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = requests.post(url, files=files, headers=headers or None, timeout=30)
    assert response.status_code == 200
    # 上传/导入接口返回内容依赖服务端处理，优先保证脚本可执行，不强断言中文消息。


# 以下异常用例由程序根据 DTO 校验注解和接口参数规则自动扩展。
AUTO_EXCEPTION_CASES = [{'id': 'ex_1_invalid_type_updatesupport', 'description': '参数 updateSupport 类型错误', 'exception_type': 'invalid_type', 'path_params': {}, 'query_params': {'updateSupport': 'not_boolean'}, 'body': {'_body_omitted': True, '_reason': 'multipart_form_data'}, 'headers': {'Accept': '*/*',  'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}, 'expected_status': 400, 'actual_path': '/system/user/importData'}]

@pytest.mark.parametrize("case", AUTO_EXCEPTION_CASES, ids=[c['id'] for c in AUTO_EXCEPTION_CASES])
def test_auto_exception_post_system_user_importdata(case):
    url_path = '/system/user/importData'
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
