from types import SimpleNamespace


class FakeDeepLClient:
    def __init__(self, responder=None):
        self.responder = responder or (lambda text, kwargs: text)
        self.calls = []

    def translate_text(self, text, **kwargs):
        self.calls.append((text, kwargs))
        if isinstance(text, list):
            return [
                SimpleNamespace(text=self.responder(item, kwargs))
                for item in text
            ]
        return SimpleNamespace(text=self.responder(text, kwargs))
