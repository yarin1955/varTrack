from app.models.git_platform import GitPlatform
from app.utils.interfaces.ifactory import IFactory
class PlatformFactory(IFactory):

    @classmethod
    def register(cls):
        return super().register()

    @classmethod
    def get_registry(cls) -> dict[str, type]:
        return super().get_registry()

    @classmethod
    def create(cls, *args, **kwargs) -> GitPlatform:
        return super().create(*args, **kwargs)

    @classmethod
    def get_available_platforms(cls):
        return super().get_registry_keys()

    @classmethod
    def load_module(cls, name: str):
        # 1. Lazy Import: Only import the package when we actually need to load a plugin
        from app.models import git_platforms

        # 2. Delegate: Use the helper inherited from IFactory
        cls._load_class_from_package_module(
            module_name=name,
            package_module=git_platforms,  # Pass the module object
            expected_base_class=GitPlatform
        )

