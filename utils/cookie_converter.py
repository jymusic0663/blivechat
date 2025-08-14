import os
import aiohttp
import yarl
from urllib.parse import unquote

# 文本 Cookie 字符串（替换为你的实际 Cookie）
text_cookie = ""

# 创建 CookieJar 对象
cookie_jar = aiohttp.CookieJar()

# 解析并添加 Cookie
domain = ".bilibili.com"  # 根据实际网站设置
path = "/"  # Cookie 路径，通常为根路径\path = "/"

for cookie_str in text_cookie.split('; '):
    if '=' not in cookie_str:
        continue
    name, value = cookie_str.split('=', 1)
    # 解码 URL 编码的 value
    value = unquote(value)
    # 直接添加 Cookie 到 CookieJar
    cookie_jar.update_cookies({name: value}, response_url=yarl.URL(f"https://{domain}{path}"))

# 保存为 pickle 文件
cookie_jar_path = os.path.join("./data", "cookie_jar.pickle")  # 替换为实际路径
cookie_jar.save(cookie_jar_path)
print(f"Cookie 已保存到: {cookie_jar_path}")