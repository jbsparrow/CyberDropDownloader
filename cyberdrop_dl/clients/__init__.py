import logging

from cyberdrop_dl import signature
from cyberdrop_dl.constants import HttpMethod as HttpMethod
from cyberdrop_dl.logs import LOG_HTTP_TRAFFIC


class TrafficLogger(logging.LoggerAdapter[logging.Logger]):
    @signature.copy(logging.LoggerAdapter.info)
    def traffic(self, msg, *args, **kwargs) -> None:
        if LOG_HTTP_TRAFFIC.get():
            self.log(logging.INFO, msg, *args, **kwargs)


def get_logger(name: str) -> TrafficLogger:
    return TrafficLogger(logging.getLogger(name))
