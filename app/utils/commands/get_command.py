class GetCommand(Command):
    """Command to retrieve data using a storage strategy."""

    def __init__(self, strategy: StorageStrategy, *args: Any) -> None:
        self.strategy = strategy
        self.args = args
        self._result = None

    def execute(self) -> Any:
        """Execute get operation and return result."""
        self._result = self.strategy.get(*self.args)
        return self._result

    def get_result(self) -> Any:
        """Return the result of the last execution."""
        return self._result