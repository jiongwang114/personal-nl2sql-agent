"""Keep prompt_toolkit rendering tests independent of a Windows console handle."""

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.output import DummyOutput


@pytest.fixture(autouse=True)
def headless_prompt_toolkit_output():
    with create_app_session(output=DummyOutput()):
        yield
