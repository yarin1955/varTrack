import importlib
import importlib.util
import inspect
def config_model_for(kind: str):
    # "github" -> yourapp.platforms.github.config:GitHubConfig
    module = importlib.import_module(f"git_platforms.{kind}")
    cls_name = f"{kind.capitalize()}Config"
    return getattr(module, cls_name)

def import_from_string(module_path: str):
    mod = importlib.import_module(module_path)
    classes = [
        obj for obj in mod.__dict__.values()
        if inspect.isclass(obj) and obj.__module__ == mod.__name__
    ]

    if len(classes) != 1:
        raise ValueError(
            f"Expected exactly one class in module '{module_path}', found {len(classes)}"
        )

    return classes[0]

    # spec = importlib.util.spec_from_file_location("github", "git_platforms/github.py")
    # module = importlib.util.module_from_spec(spec)
    # spec.loader.exec_module(module)
    #
    # # Just get the first class, don't filter by __module__
    # name, obj = next((name, obj) for name, obj in inspect.getmembers(module, inspect.isclass))
    #
    # return name