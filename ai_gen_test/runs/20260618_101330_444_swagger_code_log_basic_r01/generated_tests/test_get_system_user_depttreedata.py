import os
import requests

import pytest
BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

def test_get_system_user_depttreedata_case_1():
    url = f"{BASE_URL}/system/user/deptTreeData"
    headers = {'Accept': '*/*', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}
    response = requests.get(url, headers=headers or None, timeout=10)
    assert response.status_code == 200


# 正常基线用例：每个接口至少保留一条，日志存在多个成功样本时可扩展多条。
AUTO_NORMAL_CASES = [{'id': 'normal_1', 'path_params': {}, 'query_params': {}, 'body': {}, 'headers': {'Accept': '*/*', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}, 'actual_path': '/system/user/deptTreeData', 'expected_status': 200, 'expected_body': [{'checked': False, 'id': 100, 'name': '若依科技', 'nocheck': False, 'open': False, 'pId': 0, 'title': '若依科技'}, {'checked': False, 'id': 101, 'name': '深圳总公司', 'nocheck': False, 'open': False, 'pId': 100, 'title': '深圳总公司'}, {'checked': False, 'id': 102, 'name': '长沙分公司', 'nocheck': False, 'open': False, 'pId': 100, 'title': '长沙分公司'}, {'checked': False, 'id': 103, 'name': '研发部门', 'nocheck': False, 'open': False, 'pId': 101, 'title': '研发部门'}, {'checked': False, 'id': 104, 'name': '市场部门', 'nocheck': False, 'open': False, 'pId': 101, 'title': '市场部门'}, {'checked': False, 'id': 105, 'name': '测试部门', 'nocheck': False, 'open': False, 'pId': 101, 'title': '测试部门'}, {'checked': False, 'id': 106, 'name': '财务部门', 'nocheck': False, 'open': False, 'pId': 101, 'title': '财务部门'}, {'checked': False, 'id': 107, 'name': '运维部门', 'nocheck': False, 'open': False, 'pId': 101, 'title': '运维部门'}, {'checked': False, 'id': 108, 'name': '市场部门', 'nocheck': False, 'open': False, 'pId': 102, 'title': '市场部门'}, {'checked': False, 'id': 109, 'name': '财务部门', 'nocheck': False, 'open': False, 'pId': 102, 'title': '财务部门'}]}]

@pytest.mark.parametrize("case", AUTO_NORMAL_CASES, ids=[c['id'] for c in AUTO_NORMAL_CASES])
def test_auto_normal_get_system_user_depttreedata(case):
    url_path = '/system/user/deptTreeData'
    if case.get('actual_path'):
        url_path = case.get('actual_path')
    else:
        for key, value in case.get('path_params', {}).items():
            url_path = url_path.replace('{' + str(key) + '}', str(value))
    url = f'{BASE_URL}{url_path}'
    response = requests.get(url, params=case.get('query_params') or None, headers=case.get('headers') or None, timeout=10)
    assert response.status_code == int(case.get('expected_status') or 200)
    expected_body = case.get('expected_body') or {}
    if isinstance(expected_body, dict) and 'code' in expected_body:
        data = response.json()
        assert data.get('code') == expected_body.get('code')
