import requests
import json

# ==== 配置区：请将您的令牌粘贴在这里 ====
YOUR_TOKEN = ""
# =====================================

HEADERS = {
    "Authorization": f"token {YOUR_TOKEN}",
    "Accept": "application/vnd.github+json"
}

def test_token():
    print("🔐 开始测试 GitHub 个人访问令牌...")
    print("=" * 50)

    # 1. 测试基本认证和查看权限
    print("1. 验证令牌身份和基础权限...")
    try:
        user_resp = requests.get("https://api.github.com/user", headers=HEADERS, timeout=10)
        if user_resp.status_code == 200:
            user_data = user_resp.json()
            print(f"   ✅ 认证成功！用户：{user_data.get('login')} (ID: {user_data.get('id')})")
            # 获取令牌的授权范围
            scopes = user_resp.headers.get('X-OAuth-Scopes', '')
            print(f"   令牌授权范围 (Scopes)：{scopes}")
        else:
            print(f"   ❌ 认证失败。HTTP 状态码：{user_resp.status_code}")
            print(f"     返回信息：{user_resp.text[:200]}")
            return False
    except Exception as e:
        print(f"   ❌ 请求异常：{e}")
        return False

    # 2. 测试关键 API：搜索仓库（这是你采集需要的核心权限）
    print("\n2. 测试仓库搜索 API 权限...")
    try:
        search_resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=HEADERS,
            params={"q": "browser", "per_page": 1},
            timeout=10
        )
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            print(f"   ✅ 搜索 API 访问成功！总结果数：{search_data.get('total_count', 0)}")
        elif search_resp.status_code == 403:
            # 可能是频率限制，也可能是权限不足
            limit_remaining = search_resp.headers.get('X-RateLimit-Remaining')
            if limit_remaining == '0':
                print("   ⚠️  搜索权限正常，但当前 API 频率限制已用尽。")
            else:
                print(f"   ❌ 搜索 API 访问被拒绝 (403)。请确认令牌是否包含 `public_repo` 或 `repo` 权限。")
                return False
        else:
            print(f"   ❌ 搜索 API 访问失败。状态码：{search_resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ 搜索测试请求异常：{e}")
        return False

    # 3. 查看详细的速率限制
    print("\n3. 查看详细 API 速率限制...")
    try:
        rate_resp = requests.get("https://api.github.com/rate_limit", headers=HEADERS, timeout=10)
        if rate_resp.status_code == 200:
            limits = rate_resp.json()
            core = limits['resources']['core']
            search = limits['resources']['search']
            graphql = limits['resources']['graphql']
            print(f"   ⏱️  核心 API 限制：{core['remaining']}/{core['limit']} 次，重置于 {core['reset']} (UTC 时间戳)")
            print(f"   🔍 搜索 API 限制：{search['remaining']}/{search['limit']} 次，重置于 {search['reset']} (UTC 时间戳)")
            print(f"   🧩 GraphQL API 限制：{graphql['remaining']}/{graphql['limit']} 次")
        else:
            print("   ⚠️  无法获取速率限制详情。")
    except Exception as e:
        print(f"   ⚠️  获取速率限制时出错：{e}")

    print("\n" + "=" * 50)
    print("测试完成！如果前面有 '✅'，说明您的令牌状态良好，可以用于数据采集。")
    print("**重要**：请勿将此令牌共享或提交到公开代码仓库。")
    return True

if __name__ == "__main__":
    test_token()