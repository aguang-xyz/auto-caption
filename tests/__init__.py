from unittest import TestCase

from auto_caption import auto_caption


class AutoCaptionTest(TestCase):
    def test_auto_caption(self):
        auto_caption("./samples/en/1.webm", "./samples/en/1.srt")
