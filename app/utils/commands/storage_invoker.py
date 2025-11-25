from typing import Any

from app.utils.interfaces.icommand import Command


class StorageInvoker:
    """Invoker that executes commands and maintains history."""

    def __init__(self) -> None:
        self._history: list[Command] = []
        self._undo_stack: list[Command] = []

    def execute_command(self, command: Command) -> Any:
        """Execute a command and add it to history."""
        result = command.execute()
        self._history.append(command)
        self._undo_stack.clear()  # Clear redo stack on new command
        return result

    def undo(self) -> None:
        """Undo the last command."""
        if not self._history:
            raise RuntimeError("No commands to undo")

        command = self._history.pop()
        command.undo()
        self._undo_stack.append(command)

    def redo(self) -> None:
        """Redo the last undone command."""
        if not self._undo_stack:
            raise RuntimeError("No commands to redo")

        command = self._undo_stack.pop()
        command.execute()
        self._history.append(command)

    def get_history(self) -> list[Command]:
        """Get command history."""
        return self._history.copy()

    def clear_history(self) -> None:
        """Clear command history."""
        self._history.clear()
        self._undo_stack.clear()