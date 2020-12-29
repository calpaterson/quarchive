import commonmark as wrapped_lib

parser = wrapped_lib.Parser()

renderer = wrapped_lib.HtmlRenderer(options={"safe": True})


def convert_commonmark(markdown: str) -> str:
    return renderer.render(parser.parse(markdown))
