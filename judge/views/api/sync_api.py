# Import and Export API
import orjson
from django.forms.models import model_to_dict
from ninja import ModelSchema, NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.renderers import BaseRenderer

from judge.models import Problem
from judge.views.api import api_app, api_app_v2


class ORJSONRenderer(BaseRenderer):
    media_type = "application/json"

    def render(self, request, data, *, response_status):
        return orjson.dumps(data)


api = NinjaAPI(renderer=ORJSONRenderer(), title="TMath Sync API", version="1.0.0", auth=api_app.JWTAuth())
api.add_router("/app/", api_app.router)
api.add_router("/app/v2/", api_app_v2.router)


class ErrorSchema(Schema):
    detail: str


class ProblemExportData(ModelSchema):
    class Meta:
        model = Problem
        fields = "__all__"


@api.get("/problem/{problem_code}/", response=ProblemExportData)
def export_problem(request, problem_code: str):
    try:
        problem = Problem.objects.get(code=problem_code)
    except Problem.DoesNotExist:
        raise HttpError(404, "Problem not found")
    return problem


# @api.get("/pclass-fixtures/")
# def export_problem_classes_as_fixtures(request):
#     objs = ProblemClass.objects.all()

#     data = []
#     for obj in objs:
#         data.append({
#             "model": f"{obj._meta.app_label}.{obj._meta.model_name}",
#             "pk": obj.pk,
#             "fields": model_to_dict(obj)
#         })

#     return data

# @api.get("/ptype-fixtures/")
# def export_problem_types_as_fixtures(request):
#     from judge.models.problem import ProblemType
#     objs = ProblemType.objects.all()

#     data = []
#     for obj in objs:
#         data.append({
#             "model": f"{obj._meta.app_label}.{obj._meta.model_name}",
#             "pk": obj.pk,
#             "fields": model_to_dict(obj)
#         })

#     return data

# @api.get("/pgroup-fixtures/")
# def export_problem_groups_as_fixtures(request):
#     from judge.models.problem import ProblemGroup
#     objs = ProblemGroup.objects.all()

#     data = []
#     for obj in objs:
#         data.append({
#             "model": f"{obj._meta.app_label}.{obj._meta.model_name}",
#             "pk": obj.pk,
#             "fields": model_to_dict(obj)
#         })

#     return data


@api.get("/organization-fixtures/")
def export_problem_groups_as_fixtures(request):
    from judge.models import Organization

    objs = Organization.objects.filter(is_hidden=False)

    data = []
    for obj in objs:
        fields = model_to_dict(obj)
        fields.pop("admins", None)
        fields.pop("year", None)
        fields.pop("rate", None)

        fields["creation_date"] = obj.creation_date  # <- Tự thêm vào

        data.append(
            {
                "model": f"{obj._meta.app_label}.{obj._meta.model_name}",
                "pk": obj.pk,
                "fields": fields,
            }
        )

    return data
