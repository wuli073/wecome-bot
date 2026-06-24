import io

from langbot import __main__ as main_module


class StrictEncodedStream(io.StringIO):
    encoding = "gbk"

    def write(self, value: str) -> int:
        value.encode(self.encoding, errors="strict")
        return super().write(value)


def test_print_text_safe_falls_back_for_gbk_console() -> None:
    stream = StrictEncodedStream()

    main_module.print_text_safe(main_module.asciiart, stream=stream)

    output = stream.getvalue()
    assert "Open Source" in output
    assert "Documentation" in output
    assert "?" in output
