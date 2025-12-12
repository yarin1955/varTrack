from app.models.datasource import DataSource
from app.utils.interfaces.ifactory import IFactory

class DataSourceFactory(IFactory):

    @classmethod
    def register(cls):
        return super().register()

    @classmethod
    def get_available_datasources(cls):
        return super().get_registry_keys()

    @classmethod
    def create(cls, *args, **kwargs) -> DataSource:
        return super().create(*args, **kwargs)

    @classmethod
    def load_module(cls, name: str):
        # 1. Lazy Import
        from app.models import datasources

        # 2. Delegate
        cls._load_class_from_package_module(
            module_name=name,
            package_module=datasources,  # Pass the module object
            expected_base_class=DataSource
        )

    @classmethod
    def get_registry(cls) -> dict[str, type]:
        return super().get_registry()
