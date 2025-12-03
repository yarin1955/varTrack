from app.utils.class_loader import load_class_from_module

def load_module(module_name, expected_base_class):
    return load_class_from_module(
        module_name,
        package=__name__,
        expected_base_class=expected_base_class
    )