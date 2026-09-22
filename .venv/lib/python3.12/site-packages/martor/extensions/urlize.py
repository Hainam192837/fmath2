"""
Source: https://github.com/r0wb0t/markdown-urlize

A more liberal autolinker
Inspired by Django's urlize function.

Positive examples:

>>> import markdown
>>> md = markdown.Markdown(extensions=['urlize'])

>>> md.convert('http://example.com/')
u'<p><a href="http://example.com/">http://example.com/</a></p>'

>>> md.convert('go to http://example.com')
u'<p>go to <a href="http://example.com">http://example.com</a></p>'

>>> md.convert('example.com')
u'<p><a href="http://example.com">example.com</a></p>'

>>> md.convert('example.net')
u'<p><a href="http://example.net">example.net</a></p>'

>>> md.convert('www.example.us')
u'<p><a href="http://www.example.us">www.example.us</a></p>'

>>> md.convert('(www.example.us/path/?name=val)')
u'<p>(<a href="http://www.example.us/path/?name=val">www.example.us/path/?name=val</a>)</p>'

>>> md.convert('go to <http://example.com> now!')
u'<p>go to <a href="http://example.com">http://example.com</a> now!</p>'

Negative examples:

>>> md.convert('del.icio.us')
u'<p>del.icio.us</p>'

"""

import markdown
from markdown.inlinepatterns import InlineProcessor
from markdown.util import AtomicString
from xml.etree import ElementTree

# Global Vars
URLIZE_RE = "(%s)" % "|".join(
    [
        r"<(?:f|ht)tps?://[^>]*>",
        r"\b(?:f|ht)tps?://[^)<>\s]+[^.,)<>\s]",
        r"\bwww\.[^)<>\s]+[^.,)<>\s]",
        r"[^(<\s]+\.(?:com|net|org)\b",
    ]
)


class UrlizePattern(InlineProcessor):
    """Return a link Element given an autolink (`http://example/com`)."""

    def handleMatch(self, m, data):
        url = m.group(1)

        if url.startswith("<"):
            url = url[1:-1]

        text = url

        if not url.split("://")[0] in ("http", "https", "ftp"):
            if "@" in url and "/" not in url:
                url = "mailto:" + url
            else:
                url = "http://" + url

        el = ElementTree.Element("a")
        el.set("href", url)
        el.text = AtomicString(text)
        return el, m.start(0), m.end(0)


class UrlizeExtension(markdown.Extension):
    """Urlize Extension for Python-Markdown."""

    def extendMarkdown(self, md, *args, **kwargs):
        """Replace autolink with UrlizePattern"""
        md.inlinePatterns.register(UrlizePattern(URLIZE_RE, md), "autolink", 175)


def makeExtension(*args, **kwargs):
    return UrlizeExtension(*args, **kwargs)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
