#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import logging
from datetime import datetime, timedelta
from twisted.web._newclient import ResponseNeverReceived
from twisted.internet.error import *
from twisted.internet import defer
from twisted.web._newclient import ResponseFailed
import get_new_proxy

logger = logging.getLogger(__name__)


class AutoChangeProxy(object):
    # 遇到这些类型的错误直接当做代理不可用处理掉, 不再传给retrymiddleware
    DONT_RETRY_ERRORS = (TimeoutError, DNSLookupError, defer.TimeoutError,
                         ConnectionClosed, ConnectionLost, ConnectionDone,
                         ConnectError, ConnectionRefusedError,
                         ResponseNeverReceived, ValueError, ResponseFailed)

    def __init__(self, settings):
        # 当有效代理小于这个数时(包括直连), 从网上抓取新的代理
        self.extend_proxy_threshold = 6
        # 初始化代理列表
        self.proxyes = [{"proxy": None}]
        # 初始时使用0号代理(即无代理)
        self.proxy_index = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def url_in_proxyes(self, url):
        """
        返回一个代理url是否在代理列表中
        """
        for p in self.proxyes:
            if url == p["proxy"]:
                return True
        return False

    def fetch_new_proxyes(self):
        """
        从网上抓取新的代理添加到代理列表中
        """
        logger.info("使用 get_new_proxy 模块扩展代理池")
        new_proxyes = get_new_proxy.update()
        logger.info("此次获得的可用 ip 数: %s" % len(new_proxyes))

        for np in new_proxyes:
            if self.url_in_proxyes("http://" + np):
                continue
            else:
                self.proxyes.append({"proxy": "http://" + np})

    def len_valid_proxy(self):
        """
        返回proxy列表中有效的代理数量
        """
        count = 0
        for p in self.proxyes:
            count += 1
        return count

    def inc_proxy_index(self):
        """
        将代理列表的索引移到下一个有效代理的位置
        如果还发现已经距离上次抓代理过了指定时间, 则抓取新的代理
        """
        self.proxy_index = (self.proxy_index + 1) % len(self.proxyes)

        # 代理数量不足, 抓取新的代理
        if self.len_valid_proxy() < self.extend_proxy_threshold:
            logger.info("代理池中可用代理不足")
            logger.info("valid proxy < threshold: %d/%d" %
                        (self.len_valid_proxy(), self.extend_proxy_threshold))
            self.fetch_new_proxyes()
        logger.info("当前代理池中可用代理数: {}".format(self.len_valid_proxy()))

    def set_proxy(self, request):
        """
        将request设置使用为当前的或下一个有效代理
        """
        self.inc_proxy_index()
        proxy = self.proxyes[self.proxy_index]

        if proxy["proxy"]:
            request.meta["proxy"] = proxy["proxy"]
        elif "proxy" in request.meta.keys():
            del request.meta["proxy"]
        else:
            request.meta["proxy"] = None

        request.meta["proxy_index"] = self.proxy_index

    def del_proxy(self, trash_proxy):
        '''
        传入的是 http://...:...
        '''
        logger.info("删除垃圾 ip: {}".format(trash_proxy))
        # 将 index 从可选列表中删除
        try:
            self.proxyes.remove({'proxy': trash_proxy})
        except:
            pass

    def process_request(self, request, spider):
        """
        将request设置为使用代理
        """
        # spider发现parse error, 要求更换代理
        if "change_proxy" in request.meta.keys() and request.meta["change_proxy"]:
            self.del_proxy(request.meta['proxy'])
            logger.info("spider 请求更换代理: %s" % request)
            self.del_proxy(request.meta["proxy"])
            request.meta["change_proxy"] = False
        request.meta['dont_redirect'] = True
        self.set_proxy(request)

    def process_response(self, request, response, spider):
        """
        检查response.status, 根据status是否在允许的状态码中决定是否切换到下一个proxy, 或者禁用proxy
        """
        if "proxy" in request.meta.keys():
            logger.debug("%s %s %s" % (request.meta["proxy"], response.status, request.url))
        else:
            logger.debug("None %s %s" % (response.status, request.url))

        # status不是正常的200而且不在spider声明的正常爬取过程中可能出现的
        # status列表中, 则认为代理无效, 切换代理
        if response.status != 200 and (response.status not in spider.website_possible_httpstatus_list):
            logger.info("{1} 状态码 {0},不在白名单中".format(response.status, response.url))
            # 将当前返回 error 的 proxy 删除
            try:
                self.del_proxy(request.meta["proxy"])
            except:
                pass
            new_request = request.copy()
            new_request.dont_filter = True
            return new_request
        else:
            return response

    def process_exception(self, request, exception, spider):
        """
        处理由于使用代理导致的连接异常
        """
        request_proxy_index = request.meta["proxy_index"]
        request_proxy = request.meta['proxy']

        if isinstance(exception, self.DONT_RETRY_ERRORS):
            try:
                self.del_proxy(request_proxy)
            except:
                pass
            new_request = request.copy()
            new_request.dont_filter = True
            self.inc_proxy_index()
            return new_request
        else:
            logger.warning('丢失的连接: {}'.format(request.url))
            logger.warning('异常信息: {}'.format(exception))
            logger.warning('异常类型: {}'.format(type(exception)))


