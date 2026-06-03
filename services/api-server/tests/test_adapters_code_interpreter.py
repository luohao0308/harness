from app.sandbox.docker_manager import SandboxCommandResult
from app.tools.adapters.code_interpreter_adapter import CodeInterpreterAdapter
from app.tools.registry import ToolRegistry


def _adapter(method: str) -> CodeInterpreterAdapter:
    return CodeInterpreterAdapter(
        slug=f"code_interpreter.{method}",
        method=method,
        description=method,
        input_schema={},
        output_schema={},
    )


def test_code_interpreter_requires_sandbox_executor() -> None:
    result = _adapter("run_python").execute(
        metadata=ToolRegistry.default().tools["code_interpreter.run_python"],
        input_json={"code": "print(1)"},
        config_json=None,
        secret_value=None,
    )

    assert result.output_json["error"] == "sandbox_not_ready"


def test_code_interpreter_blocks_dangerous_calls() -> None:
    calls = []

    def executor(command: str, cwd: str, timeout_seconds: int) -> SandboxCommandResult:
        calls.append(command)
        return SandboxCommandResult(stdout="", stderr="", exit_code=0, duration_ms=1)

    result = _adapter("run_python").execute(
        metadata=ToolRegistry.default().tools["code_interpreter.run_python"],
        input_json={"code": "import os\nos.system('echo bad')"},
        config_json=None,
        secret_value=None,
        sandbox_command_executor=executor,
    )

    assert result.output_json["error"] == "policy_denied"
    assert calls == []


def test_code_interpreter_blocks_subprocess_import_and_dynamic_lookup() -> None:
    calls = []

    def executor(command: str, cwd: str, timeout_seconds: int) -> SandboxCommandResult:
        calls.append(command)
        return SandboxCommandResult(stdout="", stderr="", exit_code=0, duration_ms=1)

    result = _adapter("run_python").execute(
        metadata=ToolRegistry.default().tools["code_interpreter.run_python"],
        input_json={"code": "import subprocess\ngetattr(__builtins__, 'eval')('1 + 1')"},
        config_json=None,
        secret_value=None,
        sandbox_command_executor=executor,
    )

    assert result.output_json["error"] == "policy_denied"
    assert "import subprocess is blocked" in result.output_json["message"]
    assert "call getattr is blocked" in result.output_json["message"]
    assert calls == []


def test_code_interpreter_executes_through_sandbox_executor() -> None:
    calls = []

    def executor(command: str, cwd: str, timeout_seconds: int) -> SandboxCommandResult:
        calls.append({"command": command, "cwd": cwd, "timeout_seconds": timeout_seconds})
        return SandboxCommandResult(
            stdout=(
                'noise\n__HARNESS_CODE_RESULT__={"stdout":"3\\n","stderr":"",'
                '"exit_code":0,"generated_files":[]}\n'
            ),
            stderr="",
            exit_code=0,
            duration_ms=7,
        )

    result = _adapter("run_python").execute(
        metadata=ToolRegistry.default().tools["code_interpreter.run_python"],
        input_json={"code": "print(1 + 2)", "timeout_seconds": 5},
        config_json=None,
        secret_value=None,
        sandbox_command_executor=executor,
    )

    assert calls[0]["cwd"] == "/workspace"
    assert calls[0]["timeout_seconds"] == 5
    assert result.output_json["stdout"] == "3\n"
    assert result.output_json["duration_ms"] == 7


def test_code_interpreter_install_package_quotes_requirement() -> None:
    calls = []

    def executor(command: str, cwd: str, timeout_seconds: int) -> SandboxCommandResult:
        calls.append(command)
        return SandboxCommandResult(stdout="ok", stderr="", exit_code=0, duration_ms=9)

    result = _adapter("install_package").execute(
        metadata=ToolRegistry.default().tools["code_interpreter.install_package"],
        input_json={"package": "pandas", "version": "2.2.0", "idempotency_key": "pip-1"},
        config_json=None,
        secret_value=None,
        sandbox_command_executor=executor,
    )

    assert "pandas==2.2.0" in calls[0]
    assert result.output_json["installed"] is True
