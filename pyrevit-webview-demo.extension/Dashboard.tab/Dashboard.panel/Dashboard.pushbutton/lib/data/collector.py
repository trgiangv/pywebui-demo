# -*- coding: utf-8 -*-
from __future__ import division, print_function

import traceback

from Autodesk.Revit import DB
from pywebui.adapter.revit import REVIT_CONTEXT

from lib.constants import (
    EXTRA_PARAMETERS,
    MISSING_CATEGORY,
    MISSING_FAMILY,
    MISSING_LEVEL,
    MISSING_PHASE,
    MISSING_TYPE,
    MISSING_WORKSET,
)
from lib.data.categories import get_model_categories
from lib.log import get_logger

log = get_logger()


def collect_model_info(doc):
    # type: (DB.Document) -> dict[str, str | int]
    file_name = doc.Title or "Untitled"
    file_path = doc.PathName or ""

    current_view = ""
    active_view = REVIT_CONTEXT.uidoc.ActiveView  # type: DB.View
    if active_view is not None:
        current_view = active_view.Name or ""

    total_views = 0
    view_collector = (
        DB.FilteredElementCollector(doc).OfClass(DB.View).WhereElementIsNotElementType()
    )
    for view in view_collector:
        view_element = view  # type: DB.View
        if not view_element.IsTemplate and view_element.ViewType != DB.ViewType.Internal:
            total_views += 1

    sheet_collector = (
        DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).WhereElementIsNotElementType()
    )
    total_sheets = int(sheet_collector.GetElementCount())

    return {
        "file_name": file_name,
        "file_path": file_path,
        "current_view": current_view,
        "total_views": total_views,
        "total_sheets": total_sheets,
    }


def collect_model_elements(doc, categories=None, extra_parameters=None):
    # type: (DB.Document, list[DB.BuiltInCategory] | None, list[str] | None) -> list[dict[str, str | bool]]
    if categories is None:
        categories = get_model_categories()

    if extra_parameters is None:
        extra_parameters = EXTRA_PARAMETERS

    levels = _collect_levels(doc)
    phases = _collect_phases(doc)

    rows = []
    counts = []  # type: list[tuple[DB.BuiltInCategory, int]]
    types = {}
    for category in categories:
        found = _collect_category(doc, category, levels, phases, extra_parameters, types)
        if found:
            counts.append((category, len(found)))
            rows.extend(found)

    if counts:
        summary = ", ".join("{}={}".format(category, count) for category, count in counts)
        log.info(
            "{} elements in {} categories: {}".format(len(rows), len(counts), summary)
        )
    else:
        log.info("no elements in the registered categories")

    if extra_parameters:
        log.info("collected {} extra parameters per element".format(len(extra_parameters)))

    return rows


def _collect_category(doc, category, levels, phases, extra_parameters, types):
    # type: (DB.Document, DB.BuiltInCategory, dict[str, str], dict[str, str], list[str], dict[str, DB.ElementType | None]) -> list[dict[str, str | bool]]
    try:
        collector = (
            DB.FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType()
        )
    except Exception as ex:
        log.warning("skip category {}: {}".format(category, ex))
        return []

    rows = []
    failed = 0
    for element in collector:
        try:
            rows.append(_to_row(doc, element, levels, phases, extra_parameters, types))
        except Exception:
            failed += 1
            if failed <= 3:  # the first few tell the cause; the rest repeat it
                log.warning(
                    "skip element {} in {}:\n{}".format(
                        element.Id.ToString(), category, traceback.format_exc()
                    )
                )
    if failed:
        log.warning("category {}: {} rows, {} skipped".format(category, len(rows), failed))
    else:
        log.debug("category {}: {} rows".format(category, len(rows)))
    return rows


def _collect_levels(doc):
    # type: (DB.Document) -> dict[str, str]
    result = {}
    for level in (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_Levels)
        .WhereElementIsNotElementType()
    ):
        level_element = level  # type: DB.Level
        result[level_element.Id.ToString()] = level_element.Name or MISSING_LEVEL.label
    return result


def _collect_phases(doc):
    # type: (DB.Document) -> dict[str, str]
    result = {}
    for phase in doc.Phases:
        phase_element = phase  # type: DB.Phase
        result[phase_element.Id.ToString()] = phase_element.Name or MISSING_PHASE.label
    return result


def _to_row(doc, element, levels, phases, extra_params, types):
    # type: (DB.Document, DB.Element, dict[str, str], dict[str, str], list[str], dict[str, DB.ElementType | None]) -> dict[str, str | bool]
    element_type = _cached_type(doc, element, types)
    row = {
        "element_id": element.Id.ToString(),
        "unique_id": element.UniqueId or "",
        "name": _revit_name(element) or "Unnamed",
        "class_name": element.GetType().Name,
        "category": _get_category(element),
        "family": _family_name(element_type),
        "type": _type_name(element_type),
        "level": _get_level(element, levels),
        "phase": _get_phase(element, phases),
        "workset": _get_workset(doc, element),
        "is_view_specific": element.ViewSpecific,
        "is_pinned": element.Pinned,
        "has_material_quantities": _has_material_quantities(element),
    }

    if extra_params:
        row.update(_collect_extra_params(element, extra_params))

    return row


def _get_category(element):
    # type: (DB.Element) -> str
    category = element.Category  # type: DB.Category
    if category is None:
        return MISSING_CATEGORY.label
    return category.Name or MISSING_CATEGORY.label


def _has_material_quantities(element):
    # type: (DB.Element) -> bool
    category = element.Category  # type: DB.Category
    if category is None:
        return False
    return category.HasMaterialQuantities


def _revit_name(element):
    # type: (DB.Element) -> str
    """Read ``Element.Name``.

    IronPython 2.7 raises ``AttributeError`` when a subclass hides that
    property (``ElementType``, ``SpatialElement``). ``DB.Element.Name`` is then
    a plain Python descriptor on the base class, so its ``__get__`` returns the
    name. CPython and IronPython 3 take the first branch.
    """
    try:
        name = element.Name
    except AttributeError:
        name = DB.Element.Name.__get__(element, DB.Element)
    return name or ""


def _cached_type(doc, element, types):
    # type: (DB.Document, DB.Element, dict[str, DB.ElementType | None]) -> DB.ElementType | None
    type_id = element.GetTypeId()
    if type_id.Equals(DB.ElementId.InvalidElementId):
        return None
    key = type_id.ToString()
    if key in types:
        return types[key]
    found = doc.GetElement(type_id)  # type: DB.Element
    element_type = found if isinstance(found, DB.ElementType) else None
    types[key] = element_type
    return element_type


def _family_name(element_type):
    # type: (DB.ElementType | None) -> str
    if element_type is None:
        return MISSING_FAMILY.label
    return element_type.FamilyName or MISSING_FAMILY.label


def _type_name(element_type):
    # type: (DB.ElementType | None) -> str
    if element_type is None:
        return MISSING_TYPE.label
    return _revit_name(element_type) or MISSING_TYPE.label


def _named_id(names, element_id):
    # type: (dict[str, str], DB.ElementId) -> str
    if element_id.Equals(DB.ElementId.InvalidElementId):
        return ""
    return names.get(element_id.ToString(), "")


def _get_level(element, levels):
    # type: (DB.Element, dict[str, str]) -> str
    level_param = element.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM)  # type: DB.Parameter
    if level_param is not None and level_param.HasValue:
        name = _named_id(levels, level_param.AsElementId())
        if name:
            return name
    name = _named_id(levels, element.LevelId)
    if name:
        return name
    return MISSING_LEVEL.label


def _get_phase(element, phases):
    # type: (DB.Element, dict[str, str]) -> str
    created_param = element.get_Parameter(DB.BuiltInParameter.PHASE_CREATED)  # type: DB.Parameter
    if created_param is not None and created_param.HasValue:
        name = _named_id(phases, created_param.AsElementId())
        if name:
            return name
    return MISSING_PHASE.label


def _get_workset(doc, element):
    # type: (DB.Document, DB.Element) -> str
    if not doc.IsWorkshared:
        return MISSING_WORKSET.label
    workset_id = element.WorksetId  # type: DB.WorksetId
    if workset_id.Equals(DB.WorksetId.InvalidWorksetId):
        return MISSING_WORKSET.label
    workset = doc.GetWorksetTable().GetWorkset(workset_id)  # type: DB.Workset
    return workset.Name or MISSING_WORKSET.label


def _param_value_as_string(param):
    # type: (DB.Parameter) -> str
    return param.AsValueString() or ""


def _collect_extra_params(element, param_names):
    # type: (DB.Element, list[str]) -> dict[str, str]
    result = {}
    for name in param_names:
        param = element.LookupParameter(name)  # type: DB.Parameter
        if param is not None and param.HasValue:
            result[name] = _param_value_as_string(param)
        else:
            result[name] = ""
    return result


def collect_all_parameters(element):
    # type: (DB.Element) -> dict[str, str]
    result = {}
    for param in element.Parameters:
        parameter = param  # type: DB.Parameter
        name = parameter.Definition.Name
        if not name:
            continue
        if parameter.HasValue:
            result[name] = _param_value_as_string(parameter)
        else:
            result[name] = ""
    return result
