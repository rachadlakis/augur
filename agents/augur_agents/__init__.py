"""Augur Tensors agent layer.

Five ADK agents, four of them served over A2A as independent processes:

    orchestrator  owns the lifecycle state machine and drives every stage.
                  It calls the workers as *tools* and keeps control — it never
                  hands the conversation off to one.
    research      advisory literature agent (read-only, never gates a stage)
    data          dataset inspect / validate / materialize / manifest
    training      plan / estimate / launch / monitor a training job
    evaluation    benchmark suites, reports, threshold comparison

Nothing here runs GPU work: the training agent hands a validated plan to a job
manager and reports durable job state (today a stub; later `training-mcp`).
"""

__version__ = "0.1.0"

