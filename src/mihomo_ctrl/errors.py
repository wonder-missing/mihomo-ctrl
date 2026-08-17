class MihomoError(Exception):
    """需要告诉用户的控制失败。"""


class MihomoAPIError(MihomoError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


class MihomoConnectionError(MihomoError):
    def __init__(self, url: str, detail: str) -> None:
        self.url = url
        super().__init__(f"Cannot connect to Mihomo API ({url}): {detail}")
