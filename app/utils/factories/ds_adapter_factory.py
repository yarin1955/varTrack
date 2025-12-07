from app.models.ds_adapter import DataSourceAdapter
from app.models.git_platform import GitPlatform
from app.utils.interfaces.ifactory import IFactory


class DSAdapterFactory(IFactory):

    @classmethod
    def register(cls):
        return super().register()

    @classmethod
    def get_registry(cls) -> dict[str, type]:
        return super().get_registry()

    # @classmethod
    # def create(cls, *args, **kwargs) -> DataSourceAdapter:
    #     return super().create(*args, **kwargs)

    @classmethod
    def create(cls, config, *args, **kwargs) -> DataSourceAdapter:
        name = config.name

        if name not in cls._registry:
            raise ValueError(f"No data source registered as '{name}'")

        return cls._registry[name](config, *args, **kwargs)

    @classmethod
    def get_available_platforms(cls):
        return super().get_registry_keys()

    # @classmethod
    # def get_union_type(cls):
    #     return super().get_union_type()


    # @classmethod
    # def aaa(self):
    #     builder: Platform = xx.auth()
    #     if students.schemas.platform == raw.name:
    #         builder = builder.git_clone(students.schemas)
    #     builder = builder.create_webhooks().closed()

