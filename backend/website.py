import hashlib
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import urllib3
from bs4 import BeautifulSoup


def extract_website(url):
    for _ in range(4):
        parts = urlsplit(url.strip())
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
            raise ValueError('请提供不含账号信息的 HTTPS 个人网站地址')
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        ips = {row[4][0] for row in addresses}
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('网站必须使用公开互联网地址')
        # 固定已核验的公网地址连接，保留 TLS 主机校验，避免二次 DNS 解析。
        pool = urllib3.HTTPSConnectionPool(sorted(ips)[0], port=443, server_hostname=parts.hostname,
                                         assert_hostname=parts.hostname, timeout=urllib3.Timeout(connect=8, read=15))
        try:
            response = pool.urlopen('GET', parts.path + ('?' + parts.query if parts.query else '') or '/',
                                    headers={'Host': parts.hostname, 'User-Agent': 'ChanjiaoZhidui/1.0'},
                                    redirect=False, retries=False, preload_content=False)
            if response.status in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers.get('Location', ''))
                continue
            if response.status != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
                raise ValueError('网站未返回可提取的网页正文，请上传简历或网页导出文件')
            body = response.read(2 * 1024 * 1024 + 1, decode_content=True)
            if len(body) > 2 * 1024 * 1024:
                raise ValueError('网页正文过大，请上传导出文件')
        except urllib3.exceptions.HTTPError as exc:
            raise ValueError('个人网站读取失败：' + type(exc).__name__) from exc
        finally:
            pool.close()
        soup = BeautifulSoup(body, 'html.parser')
        for element in soup(['script', 'style', 'nav', 'footer']):
            element.decompose()
        text = soup.get_text('\n', strip=True)[:60000]
        if not text:
            raise ValueError('网页没有可提取文字，请上传简历')
        return {'name': soup.title.get_text()[:120] if soup.title else parts.hostname,
                'url': url, 'sha256': hashlib.sha256(body).hexdigest(), 'characters': len(text),
                'blocks': [{'location': '个人网站正文', 'text': text}]}
    raise ValueError('网站跳转次数过多')
