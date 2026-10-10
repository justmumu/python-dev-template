"""Generator-only Dependabot policy for the workflows generated projects copy."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_WORKFLOWS = Path("template/.github/workflows")


def actions_updates():
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    return next(update for update in config["updates"] if update["package-ecosystem"] == "github-actions")


def test_dependabot_bumps_the_template_workflow_copies():
    # Dependabot reads .github/workflows only for "/"; any other directory is scanned itself.
    assert set(actions_updates()["directories"]) == {"/", f"/{TEMPLATE_WORKFLOWS}"}


def test_one_weekly_pull_request_bumps_every_action_in_both_directories():
    # One plain group merges every listed directory's changes into one pull request;
    # group-by: dependency-name would open one pull request per action instead.
    updates = actions_updates()
    assert updates["schedule"]["interval"] == "weekly"
    assert list(updates["groups"].values()) == [{"patterns": ["*"]}]


def test_template_workflow_copies_match_the_generator_workflows():
    # Bootstrap rejects a generator whose shared workflows differ from the emitted copies.
    copies = sorted((ROOT / TEMPLATE_WORKFLOWS).glob("*.yml"))
    assert copies, "Plain template workflows are Dependabot's input."
    for copy in copies:
        assert copy.read_bytes() == (ROOT / ".github/workflows" / copy.name).read_bytes(), copy.name
