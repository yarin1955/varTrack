import json
import yaml
import os
from pathlib import Path
from typing import Dict, Optional, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from xml.etree import ElementTree as ET

try:
    import jsonschema
    from jsonschema import Draft7Validator, validate, ValidationError
except ImportError:
    print("Warning: jsonschema not installed. Install with: pip install jsonschema")
    jsonschema = None

try:
    from lxml import etree
except ImportError:
    print("Warning: lxml not installed. Install with: pip install lxml")
    etree = None


class SchemaSource(Enum):
    """Source of schema discovery"""
    VARXAR_EXACT = "varxar (exact)"
    VARXAR_PATTERN = "varxar (pattern)"
    DOCUMENT = "document"
    NOT_FOUND = "not found"


class DocumentFormat(Enum):
    """Document format types"""
    JSON = "json"
    XML = "xml"
    YAML = "yaml"


@dataclass
class ValidationResult:
    """Result of document validation"""
    success: bool
    file_path: str
    doc_format: DocumentFormat
    schema_name: Optional[str] = None
    schema_source: SchemaSource = SchemaSource.NOT_FOUND
    message: str = ""
    errors: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        filename = Path(self.file_path).name
        parts = [
            status,
            filename,
            f"[{self.doc_format.value.upper()}]"
        ]

        if self.schema_name:
            parts.append(f"→ {self.schema_name}")
            parts.append(f"({self.schema_source.value})")

        base = " ".join(parts)

        if self.message:
            base += f": {self.message}"

        return base


class DocumentValidator:
    """Validates JSON, XML, and YAML documents against schemas."""

    def __init__(self, schemas_dir: str = "schemas", varxar_file: str = "varxar.json"):
        """
        Initialize validator.

        Args:
            schemas_dir: Directory containing schema files
            varxar_file: Name of the mapping configuration file (inside schemas_dir)
        """
        self.schemas_dir = Path(schemas_dir).resolve()
        self.varxar_file = varxar_file
        self.varxar_config: Optional[Dict[str, str]] = None
        self._schema_cache: Dict[str, Any] = {}

        if not self.schemas_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {self.schemas_dir}")

        self.varxar_config = self._load_varxar()

    def _find_file_case_insensitive(self, directory: Path, filename: str) -> Optional[Path]:
        """Find a file with case-insensitive matching."""
        if not directory.exists():
            return None

        filename_lower = filename.lower()
        for item in directory.iterdir():
            if item.name.lower() == filename_lower:
                return item

        return None

    def _load_varxar(self) -> Optional[Dict[str, str]]:
        """Load the varxar configuration file from schemas directory."""
        varxar_path = self._find_file_case_insensitive(self.schemas_dir, self.varxar_file)

        if not varxar_path:
            print(f"Info: {self.varxar_file} not found in {self.schemas_dir}. Using document declarations only.")
            return None

        try:
            with open(varxar_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)

            if not isinstance(mapping, dict):
                raise ValueError(f"{self.varxar_file} must contain a JSON object")

            return mapping

        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in {self.varxar_file}: {e}")
            return None
        except Exception as e:
            print(f"Warning: Failed to load {self.varxar_file}: {e}")
            return None

    def _simple_pattern_match(self, pattern: str, text: str) -> bool:
        """
        Simple pattern matching without regex.
        Supports: * (any chars), ? (single char), [0-9] (digit)
        """
        p_idx = 0
        t_idx = 0
        star_idx = -1
        match_idx = -1

        while t_idx < len(text):
            # Check for [0-9] pattern
            if p_idx < len(pattern) - 4 and pattern[p_idx:p_idx + 5] == '[0-9]':
                if text[t_idx].isdigit():
                    p_idx += 5
                    t_idx += 1
                    continue
                elif star_idx != -1:
                    p_idx = star_idx + 1
                    match_idx += 1
                    t_idx = match_idx
                    continue
                else:
                    return False

            # Match current character or ?
            if p_idx < len(pattern) and (pattern[p_idx] == text[t_idx] or pattern[p_idx] == '?'):
                p_idx += 1
                t_idx += 1
            # Found *
            elif p_idx < len(pattern) and pattern[p_idx] == '*':
                star_idx = p_idx
                match_idx = t_idx
                p_idx += 1
            # No match, backtrack to last *
            elif star_idx != -1:
                p_idx = star_idx + 1
                match_idx += 1
                t_idx = match_idx
            else:
                return False

        # Handle remaining * in pattern
        while p_idx < len(pattern) and pattern[p_idx] == '*':
            p_idx += 1

        return p_idx == len(pattern)

    def _find_schema_from_varxar(self, filename: str) -> Tuple[Optional[str], SchemaSource]:
        """Find schema using varxar mapping."""
        if not self.varxar_config:
            return None, SchemaSource.NOT_FOUND

        # Exact match
        if filename in self.varxar_config:
            return self.varxar_config[filename], SchemaSource.VARXAR_EXACT

        # Pattern match
        for pattern, schema_name in self.varxar_config.items():
            if self._simple_pattern_match(pattern, filename):
                return schema_name, SchemaSource.VARXAR_PATTERN

        return None, SchemaSource.NOT_FOUND

    def _detect_format(self, content: str) -> Optional[DocumentFormat]:
        """Detect document format."""
        content = content.strip()

        if not content:
            return None

        if content.startswith('<'):
            return DocumentFormat.XML

        if content.startswith('{') or content.startswith('['):
            return DocumentFormat.JSON

        # Try YAML
        try:
            yaml.safe_load(content)
            return DocumentFormat.YAML
        except:
            return None

    def _extract_schema_from_json(self, data: dict) -> Optional[str]:
        """Extract schema from JSON data."""
        return data.get('$schema') or data.get('schema')

    def _extract_schema_from_yaml(self, data: dict) -> Optional[str]:
        """Extract schema from YAML data."""
        return data.get('$schema') or data.get('schema')

    def _extract_schema_from_xml(self, root: ET.Element) -> Optional[str]:
        """Extract schema from XML root element."""
        xsi_ns = '{http://www.w3.org/2001/XMLSchema-instance}'

        # Try xsi:schemaLocation
        schema_loc = root.get(f'{xsi_ns}schemaLocation')
        if schema_loc:
            parts = schema_loc.split()
            if len(parts) >= 2:
                return parts[1].split('/')[-1]

        # Try xsi:noNamespaceSchemaLocation
        no_ns_loc = root.get(f'{xsi_ns}noNamespaceSchemaLocation')
        if no_ns_loc:
            return no_ns_loc.split('/')[-1]

        return None

    def _load_schema(self, schema_name: str) -> Tuple[Optional[Any], Optional[str]]:
        """Load schema from file with caching."""
        # Check cache
        if schema_name in self._schema_cache:
            return self._schema_cache[schema_name], None

        schema_path = self.schemas_dir / schema_name

        if not schema_path.exists():
            return None, f"Schema not found: {schema_name}"

        try:
            # JSON Schema
            if schema_name.endswith('.json'):
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = json.load(f)

                if jsonschema:
                    Draft7Validator.check_schema(schema)

                self._schema_cache[schema_name] = schema
                return schema, None

            # XML Schema
            elif schema_name.endswith('.xsd'):
                if not etree:
                    return None, "lxml not installed"

                schema = etree.XMLSchema(file=str(schema_path))
                self._schema_cache[schema_name] = schema
                return schema, None

            # YAML Schema
            elif schema_name.endswith(('.yaml', '.yml')):
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = yaml.safe_load(f)

                if jsonschema and isinstance(schema, dict):
                    Draft7Validator.check_schema(schema)

                self._schema_cache[schema_name] = schema
                return schema, None

            else:
                return None, f"Unsupported schema format: {schema_name}"

        except json.JSONDecodeError as e:
            return None, f"Invalid JSON in {schema_name}: {e}"
        except jsonschema.SchemaError as e:
            return None, f"Invalid schema: {e.message}"
        except Exception as e:
            return None, f"Error loading schema: {e}"

    def validate(self, doc_path: str) -> ValidationResult:
        """
        Validate a document against its schema.

        Discovery strategy:
        1. Parse document and detect format
        2. Look for in-document schema declaration
        3. If not found, check varxar.json mapping
        4. Validate using discovered schema

        Args:
            doc_path: Path to document

        Returns:
            ValidationResult
        """
        doc_path = str(Path(doc_path).resolve())
        filename = Path(doc_path).name

        # Read file
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return ValidationResult(
                success=False,
                file_path=doc_path,
                doc_format=DocumentFormat.JSON,  # placeholder
                message=f"Failed to read file: {e}"
            )

        # Detect format
        doc_format = self._detect_format(content)
        if not doc_format:
            return ValidationResult(
                success=False,
                file_path=doc_path,
                doc_format=DocumentFormat.JSON,  # placeholder
                message="Unknown document format"
            )

        # Parse and extract schema
        parsed_data = None
        schema_from_doc = None

        try:
            if doc_format == DocumentFormat.JSON:
                parsed_data = json.loads(content)
                schema_from_doc = self._extract_schema_from_json(parsed_data)

            elif doc_format == DocumentFormat.YAML:
                parsed_data = yaml.safe_load(content)
                schema_from_doc = self._extract_schema_from_yaml(parsed_data)

            elif doc_format == DocumentFormat.XML:
                root = ET.fromstring(content)
                schema_from_doc = self._extract_schema_from_xml(root)
                parsed_data = root

        except Exception as e:
            return ValidationResult(
                success=False,
                file_path=doc_path,
                doc_format=doc_format,
                message=f"Parse error: {e}"
            )

        # Determine schema
        schema_name = None
        source = SchemaSource.NOT_FOUND

        if schema_from_doc:
            schema_name = schema_from_doc
            source = SchemaSource.DOCUMENT
        else:
            schema_name, source = self._find_schema_from_varxar(filename)

        if not schema_name:
            return ValidationResult(
                success=False,
                file_path=doc_path,
                doc_format=doc_format,
                message="No schema found"
            )

        # Load schema
        schema, error = self._load_schema(schema_name)
        if error:
            return ValidationResult(
                success=False,
                file_path=doc_path,
                doc_format=doc_format,
                schema_name=schema_name,
                schema_source=source,
                message=error
            )

        # Validate
        try:
            if doc_format in (DocumentFormat.JSON, DocumentFormat.YAML):
                if not jsonschema:
                    return ValidationResult(
                        success=False,
                        file_path=doc_path,
                        doc_format=doc_format,
                        schema_name=schema_name,
                        schema_source=source,
                        message="jsonschema not installed"
                    )

                validate(instance=parsed_data, schema=schema)

            elif doc_format == DocumentFormat.XML:
                if not etree:
                    return ValidationResult(
                        success=False,
                        file_path=doc_path,
                        doc_format=doc_format,
                        schema_name=schema_name,
                        schema_source=source,
                        message="lxml not installed"
                    )

                doc_tree = etree.fromstring(content.encode('utf-8'))
                schema.assertValid(doc_tree)

            return ValidationResult(
                success=True,
                file_path=doc_path,
                doc_format=doc_format,
                schema_name=schema_name,
                schema_source=source,
                message="Valid"
            )

        except ValidationError as e:
            path = " → ".join(str(p) for p in e.path) if e.path else "root"
            return ValidationResult(
                success=False,
                file_path=doc_path,
                doc_format=doc_format,
                schema_name=schema_name,
                schema_source=source,
                message=f"Invalid at {path}",
                errors=[e.message]
            )

        except Exception as e:
            return ValidationResult(
                success=False,
                file_path=doc_path,
                doc_format=doc_format,
                schema_name=schema_name,
                schema_source=source,
                message="Validation failed",
                errors=[str(e)]
            )

    def validate_many(self, doc_paths: List[str]) -> List[ValidationResult]:
        """Validate multiple documents."""
        return [self.validate(path) for path in doc_paths]

    def validate_directory(self, directory: str, pattern: str = "*.*") -> List[ValidationResult]:
        """Validate all files matching pattern in directory."""
        dir_path = Path(directory)

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        files = [str(f) for f in dir_path.glob(pattern) if f.is_file()]
        return self.validate_many(files)

    def print_results(self, results: List[ValidationResult], verbose: bool = False):
        """Print validation results."""
        print(f"\n{'=' * 80}")
        print("VALIDATION RESULTS")
        print(f"{'=' * 80}")

        for result in results:
            print(result)
            if verbose and result.errors:
                for error in result.errors:
                    print(f"  └─ {error}")

        stats = self._calculate_stats(results)

        print(f"\n{'-' * 80}")
        print(f"Total: {stats['total']} | "
              f"Passed: {stats['passed']} | "
              f"Failed: {stats['failed']}")
        print(f"Sources: document={stats['document']}, "
              f"varxar={stats['varxar']}, "
              f"none={stats['none']}")
        print(f"{'=' * 80}\n")

    def _calculate_stats(self, results: List[ValidationResult]) -> Dict[str, int]:
        """Calculate statistics from results."""
        return {
            'total': len(results),
            'passed': sum(1 for r in results if r.success),
            'failed': sum(1 for r in results if not r.success),
            'document': sum(1 for r in results if r.schema_source == SchemaSource.DOCUMENT),
            'varxar': sum(1 for r in results if r.schema_source in
                          (SchemaSource.VARXAR_EXACT, SchemaSource.VARXAR_PATTERN)),
            'none': sum(1 for r in results if r.schema_source == SchemaSource.NOT_FOUND)
        }