from typing import Any

from app.utils.interfaces.icommand import ICommand


class StorageInvoker:
    """Invoker that executes commands and maintains history."""

    def __init__(self) -> None:
        self._history: list[ICommand] = []
        self._undo_stack: list[ICommand] = []

    def execute_command(self, command: ICommand) -> Any:
        """Execute a command and add it to history."""
        result = command.execute()
        self._history.append(command)
        self._undo_stack.clear()  # Clear redo stack on new command
        return result

    def redo(self) -> None:
        """Redo the last undone command."""
        if not self._undo_stack:
            raise RuntimeError("No commands to redo")

        command = self._undo_stack.pop()
        command.execute()
        self._history.append(command)

    def get_history(self) -> list[ICommand]:
        """Get command history."""
        return self._history.copy()

    def clear_history(self) -> None:
        """Clear command history."""
        self._history.clear()
        self._undo_stack.clear()