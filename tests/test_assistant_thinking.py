import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile

from hunches import files
from hunches.app import HunchesApp  # noqa: F401  (import order: app first)
from hunches.screens.brief import BriefScreen
from hunches.screens.taxonomy import TaxonomyScreen
from hunches.screens.tune import TuneScreen

SCREENS = [BriefScreen, TaxonomyScreen, TuneScreen]


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_text("seeds.csv", "seed\nx\n")
    files.write_taxonomy(files.Taxonomy(mode="single", labels=[files.Label(name="a")]))
    files.write_text("prompt.md", "Classify.")


@pytest.mark.parametrize("screen", SCREENS)
def test_assistant_agent_gets_thinking_when_set(screen):
    files.write_config(
        files.Config(corpus_dir="c", embedding_model="m", assistant_thinking="medium")
    )
    assert screen().agent.model_settings == {"thinking": "medium"}


@pytest.mark.parametrize("screen", SCREENS)
def test_assistant_agent_has_no_settings_by_default(screen):
    files.write_config(files.Config(corpus_dir="c", embedding_model="m"))
    assert screen().agent.model_settings is None


async def test_thinking_reaches_the_model_request():
    files.write_config(
        files.Config(corpus_dir="c", embedding_model="m", assistant_thinking="high")
    )
    seen = []

    def model(messages, info: AgentInfo):
        seen.append(info.model_request_parameters.thinking)
        return ModelResponse(parts=[TextPart("ok")])

    agent = BriefScreen().agent
    agent.model = FunctionModel(model, profile=ModelProfile(supports_thinking=True))
    await agent.run("hi")
    assert seen == ["high"]
