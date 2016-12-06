# -*- coding: utf-8 -*-
import urllib2
import threading
import logging
import re


'''
本模块是为了从代理服务商 API 中获取端口
不过一般是付费的, 好气哦~
'''

valid_proxyes = []

# 这里写你的获取 API 地址
# 返回的格式应为 ip:port
API = ''


class check_ip_valid(threading.Thread):
    def __init__(self, proxy, append_proxy):
        threading.Thread.__init__(self)
        self.proxy = proxy

    def run(self):
        if self.check(self.proxy):
            append_proxy(self.proxy)

    def check(self, proxy):
        '''
        检查该代理是否可用
        通过获取 百毒 的脚本文件,并检测有没有关键字
        '''
        import urllib2
        url = "http://www.baidu.com/js/bdsug.js?v=1.0.3.0"
        proxy_handler = urllib2.ProxyHandler({'http': "http://" + proxy})
        opener = urllib2.build_opener(proxy_handler, urllib2.HTTPHandler)
        try:
            response = opener.open(url, timeout=3)
            return response.code == 200 and\
                re.findall(r'domain=www.baidu.com', response.read())
        except Exception:
            return False


def append_proxy(proxy):
    valid_proxyes.append(proxy)


def get_html(url):
    request = urllib2.Request(url)
    request.add_header("User-Agent", "Mozilla/5.0 Chrome/45.0.2454.99")
    html = urllib2.urlopen(request)
    return html.read()


def get_ips_from_api():
    '''
    从代理提供商那里取得 ip
    '''
    proxyes = []

    content = get_html(API)
    urls = content.split()
    for u in urls:
        proxyes.append(u)
    return proxyes


def update():
    '''
    多线程处理验证流程。
    加快效率
    '''
    global valid_proxyes
    valid_proxyes = []
    proxyes = get_ips_from_api()
    threades = []
    for proxy in proxyes:
        threades.append(check_ip_valid(proxy, append_proxy))

    for th in threades:
        th.start()

    for th in threades:
        th.join()

    return valid_proxyes

if __name__ == '__main__':
    proxyes = update()
    for i in proxyes:
        logging.warning('当前可用 ip: {}'.format(i))
