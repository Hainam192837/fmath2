from xml.etree import ElementTree

import markdown
from django.contrib.auth import get_user_model
from markdown.inlinepatterns import InlineProcessor
from markdown.util import AtomicString

from ..settings import MARTOR_ENABLE_CONFIGS, MARTOR_MARKDOWN_BASE_MENTION_URL

"""
>>> import markdown
>>> md = markdown.Markdown(extensions=['martor.utils.extensions.mention'])
>>> md.convert('@[summonagus]')
'<p><a class="direct-mention-link"
href="https://example.com/profile/summonagus/">summonagus</a></p>'
>>>
>>> md.convert('hello @[summonagus], i mentioned you!')
'<p>hello <a class="direct-mention-link"
href="https://example.com/profile/summonagus/">summonagus</a>,
i mentioned you!</p>'
>>>
"""

MENTION_RE = r"(?<!\!)\@\[([^\]]+)\]"


class MentionPattern(InlineProcessor):
    def handleMatch(self, m, data):
        username = self.unescape(m.group(1))
        users = get_user_model().objects.filter(
            username=username, is_active=True
        )  # noqa: E501

        """Makesure `username` is registered and actived."""
        if MARTOR_ENABLE_CONFIGS["mention"] == "true":
            if users.exists():
                url = "{0}{1}/".format(
                    MARTOR_MARKDOWN_BASE_MENTION_URL, username
                )  # noqa: E501
                el = ElementTree.Element("a")
                el.set("href", url)
                el.set("class", "direct-mention-link")
                el.text = AtomicString("@" + username)
                return el, m.start(0), m.end(0)

        return m.group(0), m.start(0), m.end(0)


class MentionExtension(markdown.Extension):
    def extendMarkdown(self, md, *args, **kwargs):
        """Setup `mention_link` with MentionPattern"""
        md.inlinePatterns.register(
            MentionPattern(MENTION_RE, md), "mention_link", 175
        )


def makeExtension(*args, **kwargs):
    return MentionExtension(*args, **kwargs)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
