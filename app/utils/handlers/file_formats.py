import json
import yaml
import xml.etree.ElementTree as ET
# import toml
from pathlib import Path
from typing import Union, Dict, Any


class FileFormatsHandler:

    @staticmethod
    def convert_to_json(input_file: Union[str, Path], output_file: Union[str, Path] = None) -> str:
        """
        Convert YAML, XML, or TOML files to JSON format.

        Args:
            input_file: Path to the input file (YAML, XML, or TOML)
            output_file: Optional path for output JSON file. If None, returns JSON string.

        Returns:
            JSON string representation of the converted data

        Raises:
            ValueError: If file format is not supported
            FileNotFoundError: If input file doesn't exist
        """
        input_path = Path(input_file)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Determine file format from extension
        file_extension = input_path.suffix.lower()

        # Read and parse the file based on its format
        with open(input_path, 'r', encoding='utf-8') as f:
            if file_extension in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif file_extension == '.toml':
                f.seek(0)  # Reset file pointer
                data = toml.load(f)
            elif file_extension == '.xml':
                data = xml_to_dict(f.read())
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")

        # Convert to JSON string
        json_string = json.dumps(data, indent=2, ensure_ascii=False)

        # Write to output file if specified
        if output_file:
            output_path = Path(output_file)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_string)
            print(f"JSON file saved to: {output_file}")

        return json_string

    @staticmethod
    def xml_to_dict(xml_string: str) -> Dict[str, Any]:
        """
        Convert XML string to dictionary.

        Args:
            xml_string: XML content as string

        Returns:
            Dictionary representation of XML
        """

        def parse_element(element):
            result = {}

            # Add attributes if any
            if element.attrib:
                result['@attributes'] = element.attrib

            # Handle text content
            if element.text and element.text.strip():
                if len(element) == 0:  # No child elements
                    return element.text.strip()
                else:
                    result['#text'] = element.text.strip()

            # Handle child elements
            children = {}
            for child in element:
                child_data = parse_element(child)
                if child.tag in children:
                    # Multiple elements with same tag - convert to list
                    if not isinstance(children[child.tag], list):
                        children[child.tag] = [children[child.tag]]
                    children[child.tag].append(child_data)
                else:
                    children[child.tag] = child_data

            result.update(children)
            return result if len(result) > 1 or '@attributes' in result or '#text' in result else (
                result.get('#text', '') if '#text' in result else children or element.text)

        root = ET.fromstring(xml_string)
        return {root.tag: parse_element(root)}

    @staticmethod
    def convert_string_to_json(content: str):
        """
        Parses string content (JSON, YAML, XML) into a Python Dictionary/List.
        """
        content = content.strip()

        # Try JSON
        try:
            return json.loads(content)  # Return the object, not a string
        except (json.JSONDecodeError, ValueError):
            pass

        # Try XML
        if content.startswith('<'):
            try:
                return FileFormatsHandler.xml_to_dict(content)
            except Exception:
                pass

        # Try YAML
        try:
            data = yaml.safe_load(content)
            if data is not None and not isinstance(data, str):
                return data  # Return the object
        except yaml.YAMLError:
            pass

        raise ValueError("Unable to parse content as JSON, YAML, or XML")

    @staticmethod
    def convert_string_to_dict(content: str) -> dict:
        """Convert string content to Python dict"""
        content = content.strip()

        # Try JSON first
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try XML
        if content.startswith('<'):
            try:
                return FileFormatsHandler.xml_to_dict(content)
            except Exception:
                pass

        # Try YAML
        try:
            data = yaml.safe_load(content)
            if data is not None and not isinstance(data, str):
                return data
        except yaml.YAMLError:
            pass

        raise ValueError("Could not parse content as JSON, XML, YAML, or TOML")

    # @staticmethod
    # def convert_string_to_json(content: str, format_type: str) -> str:
    #     """
    #     Convert string content in YAML, XML, or TOML format to JSON.
    #
    #     Args:
    #         content: String content in the specified format
    #         format_type: Format type ('yaml', 'xml', 'toml')
    #
    #     Returns:
    #         JSON string representation
    #     """
    #     format_type = format_type.lower()
    #
    #     if format_type in ['yaml', 'yml']:
    #         data = yaml.safe_load(content)
    #     elif format_type == 'toml':
    #         data = toml.loads(content)
    #     elif format_type == 'xml':
    #         data = FileFormatsHandler.xml_to_dict(content)
    #     elif format_type == 'json':
    #         data = json.loads(content)
    #     else:
    #         raise ValueError(f"Unsupported format type: {format_type}")
    #
    #     return json.dumps(data, indent=2, ensure_ascii=False)