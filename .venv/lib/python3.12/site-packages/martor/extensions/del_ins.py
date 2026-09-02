#! /usr/bin/env python

"""
Del/Ins Extension for Python-Markdown
=====================================
Wraps the inline content with ins/del tags.

Usage
-----
    >>> import markdown
    >>> src = '''This is ++added content + + and this is ~~deleted content~~'''
    >>> html = markdown.markdown(src, ['del_ins'])
    >>> print(html)
    <p>This is <ins>added content</ins> and this is <del>deleted content</del>
    </p>

Dependencies
------------
* [Markdown 2.0+](http://www.freewisdom.org/projects/python-markdown/)

Copyright
---------
2011, 2012 [The active archives contributors](http://activearchives.org/)
All rights reserved.
This software is released under the modified BSD License.
See LICENSE.md for details.
"""


import markdown
from markdown.inlinepatterns import SimpleTagInlineProcessor


DEL_RE = r"(\~\~)(.+?)(\~\~)"
INS_RE = r"(\+\+)(.+?)(\+\+)"


class DelInsExtension(markdown.extensions.Extension):
    """Adds del_ins extension to Markdown class."""

    def extendMarkdown(self, md, *args, **kwargs):
        del_tag = SimpleTagInlineProcessor(DEL_RE, "del")
        ins_tag = SimpleTagInlineProcessor(INS_RE, "ins")
        md.inlinePatterns.register(del_tag, "del", 175)
        md.inlinePatterns.register(ins_tag, "ins", 175)


def makeExtension(*args, **kwargs):
    return DelInsExtension(*args, **kwargs)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
