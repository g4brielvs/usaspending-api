from copy import deepcopy
from django.conf import settings

from usaspending_api.awards.models import Award
from usaspending_api.awards.v2.filters.location_filter_geocode import location_error_handling
from usaspending_api.awards.v2.lookups.lookups import (
    award_type_mapping,
    contract_type_mapping,
    idv_type_mapping,
    assistance_type_mapping,
    all_subaward_types,
)
from usaspending_api.common.exceptions import InvalidParameterException
from usaspending_api.common.validator.award_filter import AWARD_FILTER
from usaspending_api.common.validator.tinyshield import TinyShield
from usaspending_api.common.validator.utils import get_model_by_name
from usaspending_api.download.helpers import check_types_and_assign_defaults, parse_limit, validate_time_periods
from usaspending_api.download.lookups import (
    VALUE_MAPPINGS,
    SHARED_AWARD_FILTER_DEFAULTS,
    YEAR_CONSTRAINT_FILTER_DEFAULTS,
    ROW_CONSTRAINT_FILTER_DEFAULTS,
    ACCOUNT_FILTER_DEFAULTS,
    FILE_FORMATS,
    VALID_ACCOUNT_SUBMISSION_TYPES,
)


def validate_award_request(request_data: dict):
    """Analyze request and raise any formatting errors as Exceptions"""

    _validate_required_parameters(request_data, ["filters"])
    filters = _validate_filters(request_data)
    award_levels = _validate_award_levels(request_data)

    json_request = {"download_types": award_levels, "filters": {}}

    # Set defaults of non-required parameters
    json_request["agency"] = request_data["filters"]["agency"] if request_data["filters"].get("agency") else "all"
    json_request["columns"] = request_data.get("columns", [])
    json_request["file_format"] = str(request_data.get("file_format", "csv")).lower()

    check_types_and_assign_defaults(filters, json_request["filters"], SHARED_AWARD_FILTER_DEFAULTS)

    # Award type validation depends on the
    if filters.get("prime_and_sub_award_types") is not None:
        json_request["filters"]["prime_and_sub_award_types"] = _validate_award_and_subaward_types(filters)
    else:
        json_request["filters"]["award_type_codes"] = _validate_award_type_codes(filters)

    _validate_and_update_locations(filters, json_request)
    _validate_location_scope(filters, json_request)
    _validate_tas_codes(filters, json_request)
    _validate_file_format(json_request)

    # Overriding all other filters if the keyword filter is provided in year-constraint download
    # Make sure this is after checking the award_levels
    constraint_type = request_data.get("constraint_type")
    if constraint_type == "year" and "elasticsearch_keyword" in filters:
        json_request["filters"] = {
            "elasticsearch_keyword": filters["elasticsearch_keyword"],
            "award_type_codes": list(award_type_mapping.keys()),
        }
        json_request["limit"] = settings.MAX_DOWNLOAD_LIMIT
        return json_request

    # Validate time periods
    total_range_count = validate_time_periods(filters, json_request)

    if constraint_type == "row_count":
        # Validate limit exists and is below MAX_DOWNLOAD_LIMIT
        json_request["limit"] = parse_limit(request_data)

        # Validate row_count-constrained filter types and assign defaults
        check_types_and_assign_defaults(filters, json_request["filters"], ROW_CONSTRAINT_FILTER_DEFAULTS)
    elif constraint_type == "year":
        # Validate combined total dates within one year (allow for leap years)
        if total_range_count > 366:
            raise InvalidParameterException("Invalid Parameter: time_period total days must be within a year")

        # Validate year-constrained filter types and assign defaults
        check_types_and_assign_defaults(filters, json_request["filters"], YEAR_CONSTRAINT_FILTER_DEFAULTS)
    else:
        raise InvalidParameterException('Invalid parameter: constraint_type must be "row_count" or "year"')

    return json_request


def validate_idv_request(request_data):
    _validate_required_parameters(request_data, ["award_id"])
    award_id, piid, _, _, _ = _validate_award_id(request_data)

    request_data["file_format"] = str(request_data.get("file_format", "csv")).lower()
    _validate_file_format(request_data)

    return {
        "account_level": "treasury_account",
        "download_types": ["idv_orders", "idv_transaction_history", "idv_federal_account_funding"],
        "file_format": request_data["file_format"],
        "include_file_description": {"source": settings.IDV_DOWNLOAD_README_FILE_PATH, "destination": "readme.txt"},
        "piid": piid,
        "is_for_idv": True,
        "filters": {
            "idv_award_id": award_id,
            "award_type_codes": tuple(set(contract_type_mapping) | set(idv_type_mapping)),
        },
        "limit": parse_limit(request_data),
        "include_data_dictionary": True,
        "columns": request_data.get("columns", []),
    }


def validate_contract_request(request_data):
    _validate_required_parameters(request_data, ["award_id"])
    award_id, piid, _, _, _ = _validate_award_id(request_data)

    request_data["file_format"] = str(request_data.get("file_format", "csv")).lower()
    _validate_file_format(request_data)

    return {
        "account_level": "treasury_account",
        "download_types": ["sub_contracts", "contract_transactions", "contract_federal_account_funding"],
        "file_format": request_data["file_format"],
        "include_file_description": {
            "source": settings.CONTRACT_DOWNLOAD_README_FILE_PATH,
            "destination": "ContractAwardSummary_download_readme.txt",
        },
        "award_id": award_id,
        "piid": piid,
        "is_for_idv": False,
        "is_for_contract": True,
        "is_for_assistance": False,
        "filters": {"award_id": award_id, "award_type_codes": tuple(set(contract_type_mapping))},
        "limit": parse_limit(request_data),
        "include_data_dictionary": True,
        "columns": request_data.get("columns", []),
    }


def validate_assistance_request(request_data):
    _validate_required_parameters(request_data, ["award_id"])
    award_id, _, fain, uri, generated_unique_award_id = _validate_award_id(request_data)

    request_data["file_format"] = str(request_data.get("file_format", "csv")).lower()
    _validate_file_format(request_data)

    award = fain
    if "AGG" in generated_unique_award_id:
        award = uri
    return {
        "account_level": "treasury_account",
        "download_types": ["assistance_transactions", "sub_grants", "assistance_federal_account_funding"],
        "file_format": request_data["file_format"],
        "include_file_description": {
            "source": settings.ASSISTANCE_DOWNLOAD_README_FILE_PATH,
            "destination": "AssistanceAwardSummary_download_readme.txt",
        },
        "award_id": award_id,
        "assistance_id": award,
        "is_for_idv": False,
        "is_for_contract": False,
        "is_for_assistance": True,
        "filters": {"award_id": award_id, "award_type_codes": tuple(set(assistance_type_mapping))},
        "limit": parse_limit(request_data),
        "include_data_dictionary": True,
        "columns": request_data.get("columns", []),
    }


def validate_account_request(request_data):
    json_request = {"columns": request_data.get("columns", []), "filters": {}}

    _validate_required_parameters(request_data, ["account_level", "filters"])
    json_request["account_level"] = _validate_account_level(request_data, ["federal_account", "treasury_account"])

    filters = _validate_filters(request_data)

    json_request["file_format"] = str(request_data.get("file_format", "csv")).lower()
    _validate_file_format(json_request)

    # Validate required filters
    for required_filter in ["fy", "quarter"]:
        if required_filter not in filters:
            raise InvalidParameterException("Missing one or more required filters: {}".format(required_filter))
        else:
            try:
                filters[required_filter] = int(filters[required_filter])
            except (TypeError, ValueError):
                raise InvalidParameterException("{} filter not provided as an integer".format(required_filter))
        json_request["filters"][required_filter] = filters[required_filter]

    # Validate fiscal_quarter
    if json_request["filters"]["quarter"] not in [1, 2, 3, 4]:
        raise InvalidParameterException("quarter filter must be a valid fiscal quarter (1, 2, 3, or 4)")

    _validate_submission_type(filters)

    json_request["download_types"] = request_data["filters"]["submission_types"]
    json_request["agency"] = request_data["filters"]["agency"] if request_data["filters"].get("agency") else "all"

    # Validate the rest of the filters
    check_types_and_assign_defaults(filters, json_request["filters"], ACCOUNT_FILTER_DEFAULTS)

    return json_request


def _validate_award_id(request_data):
    """
    Validate that we were provided a valid award_id and, in the process, convert
    generated_unique_award_id to an internal, surrogate, integer award id.

    Returns the surrogate award id and piid.
    """
    award_id = request_data.get("award_id")
    if award_id is None:
        raise InvalidParameterException("Award id must be provided and may not be null")
    award_id_type = type(award_id)
    if award_id_type not in (str, int):
        raise InvalidParameterException("Award id must be either a string or an integer")
    if award_id_type is int or award_id.isdigit():
        filters = {"id": int(award_id)}
    else:
        filters = {"generated_unique_award_id": award_id}

    award = (
        Award.objects.filter(**filters).values_list("id", "piid", "fain", "uri", "generated_unique_award_id").first()
    )
    if not award:
        raise InvalidParameterException("Unable to find award matching the provided award id")
    return award


def _validate_account_level(request_data, valid_account_levels):
    account_level = request_data.get("account_level")
    if account_level not in valid_account_levels:
        raise InvalidParameterException("Invalid Parameter: account_level must be {}".format(valid_account_levels))
    return account_level


def _validate_award_levels(request_data):
    award_levels = request_data.get("award_levels")
    if not isinstance(award_levels, list):
        raise InvalidParameterException("Award levels parameter not provided as a list")
    elif len(award_levels) == 0:
        raise InvalidParameterException("At least one award level is required.")
    for award_level in award_levels:
        if award_level not in VALUE_MAPPINGS:
            raise InvalidParameterException("Invalid award_level: {}".format(award_level))
    return award_levels


def _validate_award_type_codes(filters):
    award_type_codes = filters.get("award_type_codes")
    if not award_type_codes or len(award_type_codes) < 1:
        award_type_codes = list(award_type_mapping)
    for award_type_code in award_type_codes:
        if award_type_code not in award_type_mapping:
            raise InvalidParameterException(f"Invalid award_type: {award_type_code}")
    return award_type_codes


def _validate_award_and_subaward_types(filters):
    prime_and_sub_award_types = filters.get("prime_and_sub_award_types", {})
    prime_award_types = prime_and_sub_award_types.get("prime_awards", [])
    sub_award_types = prime_and_sub_award_types.get("sub_awards", [])

    if len(prime_award_types) == 0 and len(sub_award_types) == 0:
        raise InvalidParameterException(
            "Missing one or more required body parameters: prime_award_types or sub_award_types"
        )

    for award_type in prime_award_types:
        if award_type not in award_type_mapping:
            raise InvalidParameterException(f"Invalid award_type: {award_type}")

    for award_type in sub_award_types:
        if award_type not in all_subaward_types:
            raise InvalidParameterException(f"Invalid subaward_type: {award_type}")

    return {"prime_awards": prime_award_types, "sub_awards": sub_award_types}


def _validate_filters(request_data):
    filters = request_data.get("filters")
    if not isinstance(filters, dict):
        raise InvalidParameterException("Filters parameter not provided as a dict")
    elif len(filters) == 0:
        raise InvalidParameterException("At least one filter is required.")
    return filters


def _validate_and_update_locations(filters, json_request):
    if "filters" not in json_request:
        json_request["filters"] = {}
    for location_filter in ["place_of_performance_locations", "recipient_locations"]:
        if filters.get(location_filter):
            for location_dict in filters[location_filter]:
                if not isinstance(location_dict, dict):
                    raise InvalidParameterException("Location is not a dictionary: {}".format(location_dict))
                location_error_handling(location_dict.keys())
            json_request["filters"][location_filter] = filters[location_filter]


def _validate_location_scope(filters: dict, json_request: dict) -> None:
    if "filters" not in json_request:
        json_request["filters"] = {}
    for location_scope_filter in ["place_of_performance_scope", "recipient_scope"]:
        if filters.get(location_scope_filter):
            if filters[location_scope_filter] not in ["domestic", "foreign"]:
                raise InvalidParameterException(
                    f"Invalid value for {location_scope_filter}: {filters[location_scope_filter]}. Only allows 'domestic' and 'foreign'."
                )
            json_request["filters"][location_scope_filter] = filters[location_scope_filter]


def _validate_tas_codes(filters, json_request):
    if "tas_codes" in filters:
        tas_codes = {"filters": {"tas_codes": filters["tas_codes"]}}
        models = [deepcopy(get_model_by_name(AWARD_FILTER, "tas_codes"))]
        tas_codes = TinyShield(models).block(tas_codes)
        if tas_codes:
            json_request["filters"]["tas_codes"] = tas_codes["filters"]["tas_codes"]


def _validate_required_parameters(request_data, required_parameters):
    for required_param in required_parameters:
        if required_param not in request_data:
            raise InvalidParameterException("Missing one or more required body parameters: {}".format(required_param))


def _validate_file_format(json_request: dict) -> None:
    val = json_request["file_format"]
    if val not in FILE_FORMATS:
        msg = f"'{val}' is not an acceptable value for 'file_format'. Valid options: {tuple(FILE_FORMATS.keys())}"
        raise InvalidParameterException(msg)


def _validate_submission_type(filters: dict) -> None:
    """Validate submission_type/submission_types parameter

    In February 2020 submission_type became the legacy filter, replaced by submission_types
    submission_type was left in-place for backward compatibility but hidden in API Contract and error messages
    """
    legacy_submission_type = filters.get("submission_type", ...)
    submission_types = filters.get("submission_types", ...)

    if submission_types == ... and legacy_submission_type == ...:
        raise InvalidParameterException("Missing required filter: submission_types")

    elif submission_types == ... and legacy_submission_type != ...:
        del filters["submission_type"]
        if isinstance(legacy_submission_type, list):
            raise InvalidParameterException("Use filter `submission_types` to request multiple submission types")
        else:
            submission_types = [legacy_submission_type]
    else:
        if not isinstance(submission_types, list):
            submission_types = [submission_types]

    if len(submission_types) == 0:
        msg = f"Provide at least one value in submission_types: {' '.join(VALID_ACCOUNT_SUBMISSION_TYPES)}"
        raise InvalidParameterException(msg)

    if any(True for submission_type in submission_types if submission_type not in VALID_ACCOUNT_SUBMISSION_TYPES):
        msg = f"Invalid value in submission_types. Options: [{', '.join(VALID_ACCOUNT_SUBMISSION_TYPES)}]"
        raise InvalidParameterException(msg)

    filters["submission_types"] = list(set(submission_types))
