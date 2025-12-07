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
    def create_adapter(cls, *args, **kwargs) -> DataSource:
        return super().create(*args, **kwargs)

    @classmethod
    def get_registry(cls) -> dict[str, type]:
        return super().get_registry()
