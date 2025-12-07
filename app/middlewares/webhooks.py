from functools import wraps
from flask import request, g, jsonify
from werkzeug.exceptions import BadRequest, HTTPException


def validate_route_param(param_name=None, transform_func=None):

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            chosen_option = request.view_args.get(param_name)

            if not chosen_option:
                raise BadRequest(f"Missing required parameter: {param_name}")

            available_options = transform_func()

            # available_platforms = PlatformFactory.get_available_platforms()

            canonical_key = chosen_option if chosen_option in available_options else None

            if not canonical_key:
                valid_platforms = ', '.join(available_options)
                raise BadRequest(
                    f"Invalid platform: '{chosen_option}'. "
                    f"Valid platforms are: {valid_platforms}"
                )

            g.platform_name = canonical_key
            kwargs[param_name] = canonical_key

            return f(*args, **kwargs)

        return wrapper

    return decorator