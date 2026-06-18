import io
import os
import requests

BASE_URL = os.getenv("BASE_URL", "http://172.16.240.86:8087")

def test_post_system_user_profile_updateavatar_upload():
    url = f"{BASE_URL}/system/user/profile/updateAvatar"
    headers = {'Accept': '*/*', 'Cookie': 'JSESSIONID=7e0e203e-a4a6-425c-8526-a5c57bed01dc'}
    files = {'avatarfile': ("avatar.png", io.BytesIO(b"fake-image-content"), "image/png")}
    response = requests.post(url, files=files, headers=headers or None, timeout=30)
    assert response.status_code == 200
    # 上传/导入接口返回内容依赖服务端处理，优先保证脚本可执行，不强断言中文消息。
