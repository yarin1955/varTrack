from typing import Dict, Any, Optional
from app.pipeline.core import Transform
from app.utils.handlers.file_formats import FileFormatsHandler

class ContentParser(Transform):
    """
    Parses raw file content (JSON/YAML/XML) into a Dictionary.
    """
    def process(self, raw_content: Optional[str]) -> Dict[str, Any]:
        if not raw_content:
            return {}
        try:
            # Relies on your existing utility that handles format detection
            return FileFormatsHandler.convert_string_to_json(raw_content)
        except Exception:
            # If parsing fails, treat as empty (or handle error strategy)
            return {}