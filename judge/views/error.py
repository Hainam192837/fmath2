import traceback

from django.shortcuts import render


def error(request, template_name, status, **context):
    return render(request, template_name, context=context, status=status)


def error400(request, exception=None):
    return error(request, "errors/400.html", 400)


def error404(request, exception=None):
    return error(request, "errors/404.html", 404)


def error403(request, exception=None):
    return error(request, "errors/403.html", 403)


def error500(request):
    return error(request, "errors/500.html", 500, traceback=traceback.format_exc())
