"""Tool sets for each agent.

Every tool follows the same contract, which the agents' instructions rely on:

* it returns a plain ``dict`` with a ``success`` flag and **never raises**, so a
  failure is something the model reads and reacts to rather than a traceback
  that ends the turn;
* read-only and mutating tools are distinguishable in code, not only in prose -
  ``governance_tools.ACTION_RISK`` is the registry, and every mutating tool
  calls ``check_policy`` before doing anything;
* nothing here touches a GPU or a real external service. These are stubs
  standing in for the capability servers (``dataset-mcp``, ``training-mcp``,
  ``evaluation-mcp``, ``research-mcp``, ``governance-mcp``) with the tool names
  and return shapes those servers will expose.
"""

from augur_agents.tools.dataset_tools import DATASET_TOOLS
from augur_agents.tools.evaluation_tools import EVALUATION_TOOLS
from augur_agents.tools.governance_tools import GOVERNANCE_TOOLS
from augur_agents.tools.research_tools import RESEARCH_TOOLS
from augur_agents.tools.training_tools import TRAINING_TOOLS

__all__ = [
    "RESEARCH_TOOLS",
    "DATASET_TOOLS",
    "TRAINING_TOOLS",
    "EVALUATION_TOOLS",
    "GOVERNANCE_TOOLS",
]

