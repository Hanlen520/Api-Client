import logging
import re
import time
import socket

import requests
from requests import Request, Response
from requests.exceptions import (InvalidSchema, InvalidURL, MissingSchema, RequestException)

from exception import ParamsError

absolute_http_url_regexp = re.compile(r"^https?://", re.I)
host_regexp = reobj = re.compile(r"""(?xi)\A
                                [a-z][a-z0-9+\-.]*://                  # Scheme
                                ([a-z0-9\-._~%!$&'()*+,;=]+@)?         # User
                                ([a-z0-9\-._~%]+                       # Named or IPv4 host
                                |\[[a-z0-9\-._~%!$&'()*+,;=:]+\])      # IPv6 host
                                """)


class ApiResponse(Response):

    def raise_for_status(self):
        if hasattr(self, 'error') and self.error:
            raise self.error
        Response.raise_for_status(self)


class HttpSession(requests.Session):
    """
    Class for performing HTTP requests and holding (session-) cookies between requests (in order
    to be able to log in and out of websites). Each request is logged so that ApiTestEngine can
    display statistics.

    This is a slightly extended version of `python-request <http://python-requests.org>`_'s
    :py:class:`requests.Session` class and mostly this class works exactly the same. However
    the methods for making requests (get, post, delete, put, head, options, patch, request)
    can now take a *url* argument that's only the path part of the URL, in which case the host
    part of the URL will be prepended with the HttpSession.base_url which is normally inherited
    from a ApiTestEngine class' host property.
    """

    def __init__(self, base_url=None, *args, **kwargs):
        super(HttpSession, self).__init__(*args, **kwargs)

        self.base_url = base_url if base_url else ""

    def _get_host(self, path):
        match = reobj.search(path)
        if match:
            return match.group(2)
        else:
            return None

    def _build_url(self, path):
        """ prepend url with hostname unless it's already an absolute URL """
        if absolute_http_url_regexp.match(path):
            return path
        elif self.base_url:
            return "%s%s" % (self.base_url, path)
        else:
            raise ParamsError("base url missed!")

    def request(self, method, url, **kwargs):
        """
        Constructs and sends a :py:class:`requests.Request`.
        Returns :py:class:`requests.Response` object.

        :param method:
            method for the new :class:`Request` object.
        :param url:
            URL for the new :class:`Request` object.
        :param params: (optional)
            Dictionary or bytes to be sent in the query string for the :class:`Request`.
        :param data: (optional)
            Dictionary or bytes to send in the body of the :class:`Request`.
        :param headers: (optional)
            Dictionary of HTTP Headers to send with the :class:`Request`.
        :param cookies: (optional)
            Dict or CookieJar object to send with the :class:`Request`.
        :param files: (optional)
            Dictionary of ``'filename': file-like-objects`` for multipart encoding upload.
        :param auth: (optional)
            Auth tuple or callable to enable Basic/Digest/Custom HTTP Auth.
        :param timeout: (optional)
            How long to wait for the server to send data before giving up, as a float, or \
            a (`connect timeout, read timeout <user/advanced.html#timeouts>`_) tuple.
            :type timeout: float or tuple
        :param allow_redirects: (optional)
            Set to True by default.
        :type allow_redirects: bool
        :param proxies: (optional)
            Dictionary mapping protocol to the URL of the proxy.
        :param stream: (optional)
            whether to immediately download the response content. Defaults to ``False``.
        :param verify: (optional)
            if ``True``, the SSL cert will be verified. A CA_BUNDLE path can also be provided.
        :param cert: (optional)
            if String, path to ssl client cert file (.pem). If Tuple, ('cert', 'key') pair.
        """

        # prepend url with hostname unless it's already an absolute URL
        url = self._build_url(url)
        host = self._get_host(url)
        logging.info(" Start to {method} {url}".format(method=method, url=url))
        logging.debug(" kwargs: {kwargs}".format(kwargs=kwargs))
        # store meta data that is used when reporting the request to locust's statistics
        request_meta = {}
        response_meta = {}

        # set up pre_request hook for attaching meta data to the request object
        request_meta["method"] = method
        request_meta["start_time"] = time.time()

        if "HttpNtlmAuth" in kwargs:
            from requests_ntlm import HttpNtlmAuth
            auth_account = kwargs.pop("HttpNtlmAuth")
            kwargs["auth"] = HttpNtlmAuth(
                auth_account["username"], auth_account["password"])

        response = self._send_request_safe_mode(method, url, **kwargs)
        if response is None:
            return None, None
        request_meta["url"] = (response.history and response.history[0] or response).request.path_url

        # record the consumed time
        response_meta["response_time"] = int((time.time() - request_meta["start_time"]) * 1000)
        response_meta["status_code"] = response.status_code
        response_meta["response_headers"] = response.headers
        response_meta["response_content"] = response.content

        # get the length of the content, but if the argument stream is set to True, we take
        # the size from the content-length header, in order to not trigger fetching of the body
        if kwargs.get("stream", False):
            request_meta["content_size"] = int(response.headers.get("content-length") or 0)
        else:
            request_meta["content_size"] = len(response.content or "")

        request_meta["request_headers"] = response.request.headers
        request_meta["request_body"] = response.request.body
        request_meta["host"] = host
        try:
            request_meta["host-ip"] = socket.gethostbyname(host)
        except socket.gaierror:
            return None, None

        logging.debug(" response: {response}".format(response=request_meta))

        try:
            response.raise_for_status()
        except RequestException as e:
            logging.error(" Failed to {method} {url}! exception msg: {exception}".format(
                method=method, url=url, exception=str(e)))
        else:
            logging.info(
                """ status_code: {}, response_time: {} ms, response_length: {} bytes"""
                .format(response_meta["status_code"], response_meta["response_time"],
                        request_meta["content_size"]))

        return request_meta, response_meta

    def _send_request_safe_mode(self, method, url, **kwargs):
        """
        Send a HTTP request, and catch any exception that might occur due to connection problems.
        Safe mode has been removed from requests 1.x.
        """
        try:
            return requests.Session.request(self, method, url, **kwargs)
        except (MissingSchema, InvalidSchema, InvalidURL):
            # raise
            return None
        except RequestException as ex:
            resp = ApiResponse()
            resp.error = ex
            resp.status_code = 0  # with this status_code, content returns None
            resp.request = Request(method, url).prepare()
            return resp
