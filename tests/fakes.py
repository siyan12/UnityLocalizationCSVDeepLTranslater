from types import SimpleNamespace


class FakeDeepLClient:
    def __init__(self, responder=None):
        self.responder = responder or (lambda text, kwargs: text)
        self.calls = []

    def translate_text(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return SimpleNamespace(text=self.responder(text, kwargs))
