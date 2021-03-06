from tkinter import *
import threading

import utils
import view
import httpclient


class Client(view.ClientView):

    def __init__(self, master=None):
        super(Client, self).__init__(master)
        self.test = httpclient.HttpSession()

    def send(self):
        self._send_button.configure(state="disabled", text="Sending...")
        t = threading.Thread(target=self.send_request)
        t.setDaemon(True)
        t.start()

    def send_request(self):
        url = self._url_entry.get()
        if url.find("http", 0, 7) < 0:
            self._url_entry.insert(0, "http://")
            url = "http://" + url

        request_meta, response_meta = self.test.request("get", url)

        # print('request_headers \n', request_meta['request_headers'])
        # print('request_body \n', request_meta['request_body'])
        # print('response_time \n', response_meta['response_time'])
        # print('status_code \n', response_meta['status_code'])
        # print('response_headers \n', response_meta['response_headers'])
        # print('response_content \n', response_meta['response_content'])

        result_data = utils.parse(request_meta, response_meta)
        self.result(result_data)
        self._send_button.configure(state="normal", text="Send")

    def result(self, result_data):
        self.clear_text()
        if result_data['errno'] == 0:
            pass
        elif result_data['errno'] == 801:
            self._header_text.insert(END, "错误：连接出错\n"
                                          "1.检查输入的地址是否正确\n"
                                          "2.检查输入的POST是否正确\n"
                                          "3.HEADER中不允许有中文字符\n")
        elif result_data['errno'] == 802:
            self._header_text.insert(END, "错误：解析出错\n"
                                          "1.解析json编码出错\n")
        elif result_data['errno'] == 803:
            self._header_text.insert(END, "错误：域名有误\n")
        elif result_data['errno'] == 1000:
            self._header_text.insert(END, "致命错误：程序出错\n")
        self.insert_text(result_data)

    def clear_text(self):
        self._header_text.delete("1.0", END)
        self._body_text.delete("1.0", END)

    def insert_text(self, result_data):

        self._header_text.insert(END, result_data['errmsg'])
        self._header_text.insert(END, result_data['host_info'])
        self._header_text.insert(END, result_data['request'])
        self._body_text.insert(END, result_data['status'])
        self._body_text.insert(END, result_data['rep_time'])
        self._body_text.insert(END, result_data['content_size'])
        self._body_text.insert(END, "Response Body: \n")
        self._body_text.insert(END, result_data['rep_body'])


if __name__ == '__main__':
    client = Client(Tk())
    client.start()
