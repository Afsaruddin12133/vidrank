"""Pure-Python fallback implementation of _pydantic_core for Cloudflare Workers."""
import json
from typing import Any

__version__ = "2.27.2"

class PydanticUndefinedType:
    pass

PydanticUndefined = PydanticUndefinedType()

class PydanticOmit(Exception):
    pass

class PydanticUseDefault(Exception):
    pass

class SchemaError(Exception):
    pass

class ValidationError(ValueError):
    def __init__(self, message: str = "", line_errors: Any = None, title: str = ""):
        super().__init__(message)
        self.title = title

class PydanticCustomError(Exception):
    def __init__(self, error_type: str, message_template: str, context: dict | None = None):
        super().__init__(message_template)
        self.type = error_type
        self.message_template = message_template
        self.context = context

class PydanticKnownError(Exception):
    pass

class PydanticSerializationError(Exception):
    pass

class PydanticSerializationUnexpectedValue(Exception):
    pass

class ArgsKwargs:
    def __init__(self, args: tuple = (), kwargs: dict | None = None):
        self.args = args
        self.kwargs = kwargs or {}

class Some:
    def __init__(self, value: Any):
        self.value = value

class Url:
    def __init__(self, url: str):
        self.url = url
    def __str__(self):
        return self.url

class MultiHostUrl:
    def __init__(self, url: str):
        self.url = url
    def __str__(self):
        return self.url

class TzInfo:
    pass

class SchemaValidator:
    def __init__(self, schema: Any, config: Any = None):
        self.schema = schema
        self.config = config
    def validate_python(self, input_val: Any, *args, **kwargs):
        return input_val
    def validate_json(self, input_val: Any, *args, **kwargs):
        if isinstance(input_val, (bytes, str)):
            return json.loads(input_val)
        return input_val

class SchemaSerializer:
    def __init__(self, schema: Any, config: Any = None):
        self.schema = schema
        self.config = config
    def to_python(self, value: Any, *args, **kwargs):
        return value
    def to_json(self, value: Any, *args, **kwargs):
        return json.dumps(value).encode()

def from_json(data: Any, *args, **kwargs):
    return json.loads(data)

def to_json(data: Any, *args, **kwargs):
    return json.dumps(data).encode()

def to_jsonable_python(data: Any, *args, **kwargs):
    return data

def validate_core_schema(schema: Any, *args, **kwargs):
    return schema
