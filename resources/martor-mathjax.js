jQuery(function ($) {
    function renderMartorMath($content) {
        if (!$content || !$content.length) {
            return;
        }

        const katexRenderConfig = {
            delimiters: [
                {left: "$$", right: "$$", display: true},
                {left: "$", right: "$", display: false},
                {left: "\\(", right: "\\)", display: false},
                {left: "\\[", right: "\\]", display: true}
            ],
            throwOnError: false
        };

        function renderKatex(root) {
            if (!root || typeof renderMathInElement !== 'function') {
                return false;
            }

            if (root.classList && root.classList.contains('arithmatex')) {
                renderMathInElement(root, katexRenderConfig);
            }

            $(root).find('.arithmatex').each(function () {
                renderMathInElement(this, katexRenderConfig);
            });
            return true;
        }

        if (renderKatex($content[0])) {
            return;
        }

        if (typeof MathJax === 'undefined' || typeof MathJax.typesetPromise !== 'function') {
            return;
        }

        let promise = Promise.resolve();
        promise = promise.then(
            () => MathJax.typesetPromise([$content[0]])
        ).catch((err) => console.log('Typeset failed: ' + err.message));
    }

    $(document).on('martor:preview', function (e, $content) {
        renderMartorMath($content);
    });

    $(document).on('click', '.nav-link[id^="nav-preview-tab-"]', function () {
        const targetSelector = $(this).attr('data-bs-target') || $(this).attr('href');
        if (!targetSelector) {
            return;
        }

        window.setTimeout(function () {
            renderMartorMath($(targetSelector));
        }, 0);

        window.setTimeout(function () {
            renderMartorMath($(targetSelector));
        }, 180);
    })
});
